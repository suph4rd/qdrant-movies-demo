import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import AsyncMock

from qdrant_client import models

from engine import catalog as movie_catalog
from engine import constants
from engine import errors
from engine import services
from engine.embeddings import cache as embedding_cache
from engine.embeddings import spec as embedding_spec
from engine.embeddings import texts as embedding_texts
from engine.stores import factory
from engine.stores import semantic
from engine.tests import helpers


VECTOR = [-0.1, 0.2] * 192


def collection(vectors=None, metadata=None):
    return NS(config=NS(params=NS(vectors=vectors if vectors is not None else {
        'semantic': models.VectorParams(size=384, distance='Cosine')}, sparse_vectors=None),
        metadata=metadata if metadata is not None else {'embedding': embedding_spec.SPEC.metadata()}))


class SemanticLoaderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.client = AsyncMock()
        self.embeddings = AsyncMock()
        self.embeddings.spec = embedding_spec.SPEC
        async def encode(movies):
            return [VECTOR[:] for _ in movies]
        self.embeddings.encode_documents.side_effect = encode
        self.store = semantic.SemanticMovieStore('http://qdrant', client=self.client,
                                       embeddings=self.embeddings, cache_path=self.directory)
        self.client.get_collections.return_value = NS(collections=[NS(name=self.store.collection_name)])
        self.client.get_collection.return_value = collection()
        self.client.count.return_value = NS(count=250)
        self.movies = movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)
        self.client.retrieve.return_value = [models.Record(id=m['id']) for m in self.movies]

    async def test_batches_payload_and_repeated_load(self):
        for _ in range(2):
            self.assertEqual(await self.store.load(constants.DEFAULT_DATA_PATH), {'loaded': 250, 'count': 250})
        self.assertEqual([len(c.args[0]) for c in self.embeddings.encode_documents.call_args_list],
                         [32]*7 + [26])
        self.assertEqual(self.client.upsert.await_count, 2)
        args = self.client.upsert.call_args.kwargs
        self.assertEqual(args['collection_name'], 'movies_semantic_v1')
        self.assertEqual(len(args['points']), 250)
        self.assertEqual(args['points'][0].vector, {'semantic': VECTOR})
        self.assertEqual(args['points'][0].payload['translations'], self.movies[0]['translations'])
        self.assertEqual(args['points'][0].payload['_embedding']['model'], embedding_spec.SPEC.model)
        await self.store.close()
        self.client.close.assert_not_awaited()
        self.embeddings.close.assert_not_awaited()

    async def test_create_only_after_successful_generation(self):
        self.client.get_collections.return_value = NS(collections=[])
        self.embeddings.encode_documents.side_effect = [ [VECTOR]*32, errors.IndexStateError('embedding_unavailable',url='test') ]
        with helpers.expected_error(self):
            await self.store.load(constants.DEFAULT_DATA_PATH)
        self.client.upsert.assert_not_awaited()
        self.client.create_collection.assert_not_awaited()
        self.embeddings.encode_documents.side_effect = lambda movies: [VECTOR]*len(movies)
        await self.store.load(constants.DEFAULT_DATA_PATH)
        self.client.create_collection.assert_awaited_once()
        self.assertEqual(self.client.create_collection.call_args.kwargs['metadata'],
                         {'embedding': embedding_spec.SPEC.metadata()})

    async def test_incompatible_index_precedes_generation_and_writes(self):
        for info in (collection({'wrong': models.VectorParams(size=384,distance='Cosine')}),
                     collection({'semantic': models.VectorParams(size=10,distance='Cosine')}),
                     collection({'semantic': models.VectorParams(size=384,distance='Dot')}),
                     collection(metadata={}),
                     *[collection(metadata={'embedding': {**embedding_spec.SPEC.metadata(), key:'wrong'}})
                       for key in ('model','revision','text_version')]):
            self.client.get_collection.return_value = info
            with helpers.expected_error(self) as raised:
                await self.store.load(constants.DEFAULT_DATA_PATH)
            self.assertEqual(raised.exception._localization[0], 'semantic_schema')
        self.embeddings.encode_documents.assert_not_awaited()
        self.client.upsert.assert_not_awaited()
        self.client.create_collection.assert_not_awaited()

    async def test_invalid_catalog_precedes_network(self):
        path = Path(self.directory)/'bad.json'
        path.write_text('[]')
        with helpers.expected_error(self):
            await self.store.load(path)
        self.assertEqual(self.client.mock_calls, [])

    async def test_changed_document_and_corrupt_cache(self):
        await self.store.load(constants.DEFAULT_DATA_PATH)
        self.embeddings.encode_documents.reset_mock()
        data=copy.deepcopy(self.movies)
        data[0]['translations']['en']['description'] += ' Changed.'
        path=Path(self.directory)/'movies.json'
        path.write_text(json.dumps(data))
        text=embedding_texts.document_text(data[1])
        cached=Path(self.directory)/(self.store.cache.key(text)+'.json')
        cached.write_text(json.dumps({'key':self.store.cache.key(text),'vector':[0]*384}))
        await self.store.load(path)
        self.assertEqual([m['id'] for m in self.embeddings.encode_documents.call_args.args[0]], [1,2])
        self.assertNotEqual(self.store.cache.key(text),
                            embedding_cache.EmbeddingCache(self.directory, replace(embedding_spec.SPEC,revision='other')).key(text))
        self.assertNotEqual(self.store.cache.key(text),
                            embedding_cache.EmbeddingCache(self.directory, replace(embedding_spec.SPEC,text_version='v2')).key(text))

    async def test_reject_injected_invalid_vectors_before_writes(self):
        for vector in ([0]*384, [1]*383, [float('nan')]*384):
            self.embeddings.encode_documents.side_effect = lambda movies: [vector]*len(movies)
            with helpers.expected_error(self):
                await self.store.load(constants.DEFAULT_DATA_PATH)
        self.client.upsert.assert_not_awaited()


class SemanticSearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.embeddings = AsyncMock()
        self.embeddings.spec = embedding_spec.SPEC
        self.embeddings.encode_query.return_value = VECTOR
        self.store = semantic.SemanticMovieStore('http://test', client=self.client, embeddings=self.embeddings)
        self.client.get_collection.return_value = collection()
        self.client.retrieve.return_value = [models.Record(id=1, payload={'title':'The Matrix'})]
        self.client.query_points.return_value = NS(points=[NS(id=2,score=.9,payload={})])

    async def test_both_scenarios_and_limits(self):
        data=movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)
        for limit in (1,5,10,20,50,249):
            result=await services.search(self.store, 'The Matrix', data, limit)
            self.assertEqual(result['source']['title'], 'The Matrix')
            args=self.client.query_points.call_args.kwargs
            self.assertEqual(args['query'], 1)
            self.assertEqual(args['using'], 'semantic')
            self.assertEqual(args['collection_name'], 'movies_semantic_v1')
            self.assertEqual(args['query_filter'].must_not[0].has_id,[1])
            self.embeddings.encode_query.assert_not_awaited()
            result=await services.semantic_search(self.store,'космос',limit)
            self.assertIsNone(result['source'])
            args=self.client.query_points.call_args.kwargs
            self.assertEqual(args['query'], VECTOR)
            self.assertEqual(args['limit'],limit)
            self.assertTrue(args['search_params'].exact)
            self.assertNotIn('query_filter',args)
            self.embeddings.encode_query.reset_mock()

    async def test_validation_before_io(self):
        for limit in (0,250,True,'5',5.0):
            with helpers.expected_error(self):
                await services.semantic_search(self.store, 'test', limit)
            with helpers.expected_error(self):
                await self.store.recommend(1, limit)
        for query in ('','  ',None):
            with helpers.expected_error(self):
                await services.semantic_search(self.store,query)
        self.assertEqual(self.client.mock_calls,[])
        self.embeddings.encode_query.assert_not_awaited()

    async def test_unknown_id_and_incompatible_index(self):
        self.client.retrieve.return_value=[]
        with helpers.expected_error(self) as raised:
            await self.store.recommend(999)
        self.assertEqual(raised.exception._localization[0],'unknown_id')
        self.client.query_points.assert_not_awaited()
        self.client.get_collection.return_value=collection(metadata={})
        for operation in (self.store.recommend(1), self.store.semantic_search('test')):
            with helpers.expected_error(self) as raised:
                await operation
            self.assertEqual(raised.exception._localization[0],'semantic_schema')
        self.embeddings.encode_query.assert_not_awaited()
        self.client.query_points.assert_not_awaited()

    async def test_owned_clients_close_even_when_embedding_close_fails(self):
        from unittest.mock import patch
        owned_embedding = AsyncMock()
        owned_embedding.spec = embedding_spec.SPEC
        owned_embedding.close.side_effect = RuntimeError('close failed')
        owned_qdrant = AsyncMock()
        with patch('engine.stores.semantic.embedding_client.EmbeddingClient',return_value=owned_embedding), patch(
                'engine.stores.semantic.AsyncQdrantClient',return_value=owned_qdrant):
            store = semantic.SemanticMovieStore('http://test')
            with self.assertRaisesRegex(RuntimeError,'close failed'):
                await store.close()
        owned_embedding.close.assert_awaited_once()
        owned_qdrant.close.assert_awaited_once()


class StoreContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_rejects_legacy_collection_before_client_creation(self):
        from unittest.mock import patch
        with patch('engine.stores.semantic.AsyncQdrantClient') as client:
            with helpers.expected_error(self) as raised:
                factory.create_store('http://test', collection_name='movies')
            self.assertEqual(raised.exception._localization[0], 'semantic_schema')
            client.assert_not_called()

    async def test_request_translates_sdk_failures(self):
        import httpx
        from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
        client = AsyncMock()
        embeddings = AsyncMock(spec=[])
        embeddings.spec = embedding_spec.SPEC
        store = semantic.SemanticMovieStore('http://test', client=client, embeddings=embeddings)
        for failure, key in (
            (UnexpectedResponse(503, 'Unavailable', b'busy', {}), 'http'),
            (ResponseHandlingException(json.JSONDecodeError('invalid response', '', 0)), 'response'),
            (ResponseHandlingException(OSError('offline')), 'connection'),
            (httpx.ConnectError('offline'), 'connection'),
        ):
            with self.subTest(failure=type(failure).__name__):
                client.get_collections.side_effect = failure
                with helpers.expected_error(self) as raised:
                    await store.request('get_collections')
                self.assertEqual(raised.exception._localization[0], key)


class ProgrammingFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_sdk_errors_propagate(self):
        client, embeddings = AsyncMock(), AsyncMock()
        embeddings.spec = embedding_spec.SPEC
        store = semantic.SemanticMovieStore('http://test', client=client, embeddings=embeddings)
        for error in (ValueError('bug'), TypeError('bug'), KeyError('bug'), AttributeError('bug')):
            client.get_collections.side_effect = error
            with self.assertRaises(type(error)) as raised:
                await store.request('get_collections')
            self.assertIs(raised.exception, error)
