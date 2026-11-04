from engine import catalog as movie_catalog, store as movie_store
from engine.errors import DemoError
import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import AsyncMock

import httpx
from qdrant_client import models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from engine import DEFAULT_DATA_PATH, services, validators


def collection(vectors):
    return NS(config=NS(params=NS(vectors=vectors)))


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        self.store = movie_store.QdrantMovieStore('http://test:6333', client=self.client)
        self.catalog = movie_catalog.read_movies(DEFAULT_DATA_PATH)
        self.client.get_collections.return_value = NS(collections=[NS(name='movies')])
        self.client.get_collection.return_value = collection(models.VectorParams(size=10, distance='Cosine'))
        self.client.count.return_value = NS(count=250)
        self.client.retrieve.return_value = [models.Record(id=1, payload=self.catalog[0])]
        self.client.query_points.return_value = NS(points=[])

    async def test_load(self):
        self.assertEqual(await self.store.load(DEFAULT_DATA_PATH), {'loaded': 250, 'count': 250})
        self.client.upsert.assert_called_once()
        args = self.client.upsert.call_args.kwargs
        self.assertTrue(args['wait'])
        self.assertEqual(len(args['points']), 250)
        self.assertEqual(args['points'][0].payload['translations'], self.catalog[0]['translations'])
        self.client.count.assert_called_once_with(collection_name='movies', exact=True)
        await self.store.close()
        self.client.close.assert_not_called()

    async def test_create(self):
        self.client.get_collections.return_value = NS(collections=[])
        await self.store.load(DEFAULT_DATA_PATH)
        self.client.create_collection.assert_called_once_with(collection_name='movies', vectors_config=models.VectorParams(size=10, distance='Cosine'))

    async def test_schema_rejected_before_writes(self):
        for vectors in (models.VectorParams(size=3, distance='Cosine'), models.VectorParams(size=10, distance='Dot'),
                        {'named': models.VectorParams(size=10, distance='Cosine')},
                        models.VectorParams(size=10, distance='Cosine', multivector_config=models.MultiVectorConfig(comparator='max_sim'))):
            self.client.get_collection.return_value = collection(vectors)
            with self.assertRaisesRegex(DemoError, 'Incompatible'):
                await self.store.load(DEFAULT_DATA_PATH)
            self.client.upsert.assert_not_called()
            self.client.create_collection.assert_not_called()

    async def test_invalid_catalog_before_network(self):
        mutations = [lambda d: d.pop(), lambda d: d[0].update(vector=[0]*10),
                     lambda d: d[0].update(vector=[float('nan')]*10), lambda d: d[0].update(vector=[1.1]*10),
                     lambda d: d[0].update(vector=[1]*9), lambda d: d[1].update(id=1),
                     lambda d: d[0].pop('translations'), lambda d: d[0].update(year='1999'),
                     lambda d: d[0].update(title=''), lambda d: d[0]['translations']['en'].update(genres=[])]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'movies.json'
            for mutate in mutations:
                data = copy.deepcopy(self.catalog)
                mutate(data)
                path.write_text(json.dumps(data))
                with self.assertRaises(DemoError):
                    await self.store.load(path)
                self.assertEqual(self.client.mock_calls, [])

    async def test_catalog_validation_without_file_io(self):
        self.assertIs(validators.validate_catalog(self.catalog), self.catalog)
        for value, key in ((None, 'size'), ([None] * 250, 'object')):
            with self.subTest(key=key), self.assertRaises(DemoError) as raised:
                validators.validate_catalog(value)
            self.assertEqual(raised.exception.key, key)
        self.assertEqual(self.client.mock_calls, [])

    async def test_invalid_search_limit_precedes_resolution_and_network(self):
        with self.assertRaises(DemoError) as raised:
            await services.search(self.store, '', self.catalog, limit=0)
        self.assertEqual(raised.exception.key, 'limit')
        self.assertEqual(self.client.mock_calls, [])

    async def test_search_and_limits(self):
        for limit in (1, 5, 10, 20, 50, 249):
            await services.search(self.store, 'The Matrix', self.catalog, limit)
            args = self.client.query_points.call_args.kwargs
            self.assertEqual(args['query'], 1)
            self.assertEqual(args['limit'], limit)
            self.assertTrue(args['search_params'].exact)
            self.assertEqual(args['query_filter'].must_not[0].has_id, [1])
        for limit in (0, 250, True, 5.0, '5', None):
            with self.assertRaises(DemoError):
                await self.store.recommend(1, limit)
        for value in (-1, 2**64, True, '1'):
            with self.assertRaises(DemoError):
                await self.store.recommend(value)

    async def test_unknown_id(self):
        self.client.retrieve.return_value = []
        with self.assertRaisesRegex(DemoError, 'Unknown movie ID'):
            await self.store.recommend(999)
        self.client.query_points.assert_not_called()

    async def test_sdk_errors(self):
        for exc, key in ((httpx.ReadTimeout('timeout'), 'connection'),
                         (ResponseHandlingException(httpx.ConnectError('offline')), 'connection'),
                         (ResponseHandlingException(ValueError('invalid JSON')), 'response'),
                         (UnexpectedResponse(503, 'unavailable', b'unavailable', {}), 'http')):
            self.client.retrieve.side_effect = exc
            with self.assertRaises(DemoError) as raised:
                await self.store.recommend(1)
            self.assertEqual(raised.exception.key, key)

    async def test_extra_records(self):
        self.client.count.return_value = NS(count=251)
        with self.assertRaisesRegex(DemoError, 'additional records'):
            await self.store.load(DEFAULT_DATA_PATH)

    async def test_resolve(self):
        for query in ('1', 'Матрица', ' мАтРиЦа ', 'матри', 'The Matrix'):
            self.assertEqual(movie_catalog.resolve_movie(query, self.catalog)['id'], 1)
        self.assertEqual(movie_catalog.resolve_movie('1917', self.catalog)['id'], 77)
        for query in ('', '999', '-1', str(2**64), 'absent title'):
            with self.assertRaises(DemoError):
                movie_catalog.resolve_movie(query, self.catalog)

    async def test_owned_client_configuration_and_close(self):
        from unittest.mock import patch
        with patch.object(movie_store, 'AsyncQdrantClient', return_value=self.client) as factory:
            store = movie_store.QdrantMovieStore('http://test:6333')
            factory.assert_called_once_with(url='http://test:6333', prefer_grpc=False,
                                            timeout=15, check_compatibility=False)
            await store.close()
            self.client.close.assert_awaited_once()
