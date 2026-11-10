import asyncio
import unittest
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from qdrant_client import models

from engine import catalog
from engine import constants
from engine import errors
from engine import imports
from engine.embeddings import spec
from engine.stores import semantic
from engine.tests.test_semantic_store import VECTOR, collection


def movie(wikidata_number=500):
    return {'id': imports.WIKIDATA_ID_BASE + wikidata_number, 'wikidata_id': 'Q' + str(wikidata_number),
            'title': 'Новый фильм', 'original_title': 'New Movie', 'year': 2025,
            'description': 'Описание', 'description_language': 'ru', 'genres': ['Драма'],
            'alternative_titles': ['Alternative'], 'source': 'wikidata',
            'translations': {'en': {'title': 'New Movie', 'description': 'Description', 'genres': ['Drama']}}}


class ImportStoreTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client, self.embeddings = AsyncMock(), AsyncMock()
        self.embeddings.spec = spec.SPEC
        self.embeddings.encode_documents.return_value = [VECTOR]
        self.client.get_collection.return_value = collection()
        self.records = {}
        async def retrieve(**kwargs):
            return [self.records[i] for i in kwargs['ids'] if i in self.records]
        async def upsert(**kwargs):
            for point in kwargs['points']:
                self.records.setdefault(point.id, models.Record(id=point.id, payload=point.payload))
        self.client.retrieve.side_effect = retrieve
        self.client.upsert.side_effect = upsert
        self.store = semantic.SemanticMovieStore('http://test', client=self.client, embeddings=self.embeddings)

    async def test_count_tracks_empty_collection_import_and_repeat(self):
        self.client.count.side_effect = lambda **kwargs: NS(count=len(self.records))
        self.assertEqual(await self.store.count_movies(), 0)
        await self.store.import_movie(movie(), [])
        self.assertEqual(await self.store.count_movies(), 1)
        await self.store.import_movie(movie(), [])
        self.assertEqual(await self.store.count_movies(), 1)
        self.client.count.assert_awaited_with(collection_name=self.store.collection_name, exact=True)

    async def test_repeat_and_parallel_import_are_one_record(self):
        results = await asyncio.gather(*(self.store.import_movie(movie(), []) for _ in range(8)))
        self.assertEqual(sum(r['created'] for r in results), 1)
        self.assertEqual(len(self.records), 1)
        self.embeddings.encode_documents.assert_awaited_once()
        self.client.upsert.assert_awaited_once()
        self.assertEqual(self.client.upsert.call_args.kwargs['update_mode'], models.UpdateMode.INSERT_ONLY)
        self.assertFalse((await self.store.import_movie(movie(), []))['created'])

    async def test_legacy_record_dedup_preserves_metadata_and_vector(self):
        imported = {**movie(), 'tmdb_id': 42}
        legacy = {**movie(), 'id': imports.TMDB_ID_BASE + 42, 'source': 'tmdb', 'tmdb_id': 42,
                  'description': 'Existing full description'}
        del legacy['wikidata_id']
        self.records[legacy['id']] = models.Record(id=legacy['id'], payload=legacy)
        result = await self.store.import_movie(imported, [])
        self.assertEqual(result, {'movie': legacy, 'created': False})
        self.assertEqual(list(self.records), [legacy['id']])
        self.embeddings.encode_documents.assert_not_awaited()
        self.client.upsert.assert_not_awaited()
        self.assertIs(imports.validate_movie(legacy), legacy)

    async def test_foreign_legacy_id_prevents_duplicate_import(self):
        imported = {**movie(), 'tmdb_id': 42}
        legacy_id = imports.TMDB_ID_BASE + 42
        self.records[legacy_id] = models.Record(id=legacy_id, payload={'id': legacy_id, 'title': 'Foreign'})
        with self.assertRaises(errors.IndexStateError):
            await self.store.import_movie(imported, [])
        self.embeddings.encode_documents.assert_not_awaited()
        self.client.upsert.assert_not_awaited()

    async def test_wikidata_identity_validation(self):
        for changes in ({'wikidata_id': 'Q0'}, {'wikidata_id': 'Q01'}, {'wikidata_id': 'Q1000000000000'},
                        {'id': imports.TMDB_ID_BASE + 500}, {'id': True}, {'tmdb_id': True}):
            with self.subTest(changes=changes), self.assertRaises(errors.InputValidationError):
                await self.store.import_movie({**movie(), **changes}, [])
        self.assertEqual(self.client.mock_calls, [])

    async def test_foreign_id_conflict_before_generation(self):
        item = movie()
        for payload in ({'id': item['id']}, {**item, 'source': 'other'}, {**item, 'wikidata_id': True}):
            self.records[item['id']] = models.Record(id=item['id'], payload=payload)
            with self.assertRaises(errors.IndexStateError) as raised:
                await self.store.import_movie(item, [])
            self.assertEqual(raised.exception._localization[0], 'import_conflict')
        self.embeddings.encode_documents.assert_not_awaited()
        self.client.upsert.assert_not_awaited()

    async def test_concurrent_foreign_insert_never_overwritten(self):
        original_upsert = self.client.upsert.side_effect
        async def foreign_wins(**kwargs):
            point = kwargs['points'][0]
            self.records[point.id] = models.Record(id=point.id, payload={'title': 'Foreign'})
            await original_upsert(**kwargs)
        self.client.upsert.side_effect = foreign_wins
        with self.assertRaises(errors.IndexStateError):
            await self.store.import_movie(movie(), [])
        self.assertEqual(self.records[movie()['id']].payload, {'title': 'Foreign'})

    async def test_other_process_same_movie_wins(self):
        async def other_process(**kwargs):
            point = kwargs['points'][0]
            self.records[point.id] = models.Record(id=point.id,
                payload={**point.payload, '_import_operation': 'another-process'})
        self.client.upsert.side_effect = other_process
        self.assertFalse((await self.store.import_movie(movie(), []))['created'])

    async def test_base_catalog_match_precedes_network(self):
        item = movie()
        original = {**item, 'id': 3, 'title': 'Other title', 'alternative_titles': ['New Movie']}
        result = await self.store.import_movie(item, [original])
        self.assertEqual(result, {'movie': original, 'created': False})
        self.assertEqual(self.client.mock_calls, [])

    async def test_bad_metadata_schema_and_vector_prevent_writes(self):
        for change in ({'wikidata_id': True}, {'year': '2025'}, {'description_language': 'de'},
                       {'translations': {'en': {'title': 'X', 'genres': ['Drama'], 'description': ''}}}):
            with self.assertRaises(errors.InputValidationError):
                await self.store.import_movie({**movie(), **change}, [])
        self.assertEqual(self.client.mock_calls, [])
        self.client.get_collection.return_value = collection(metadata={})
        with self.assertRaises(errors.SemanticSchemaError):
            await self.store.import_movie(movie(), [])
        self.embeddings.encode_documents.assert_not_awaited()
        self.client.get_collection.return_value = collection()
        for vector in ([0] * 384, [1] * 383, [float('nan')] * 384):
            self.embeddings.encode_documents.return_value = [vector]
            with self.assertRaises(errors.EmbeddingResponseError):
                await self.store.import_movie(movie(), [])
        self.client.upsert.assert_not_awaited()

    async def test_stored_search_pages_aliases_and_year(self):
        first, second = movie(), movie(501)
        second['year'] = 2024
        self.client.scroll.side_effect = [([models.Record(id=first['id'], payload=first)], 5),
            ([models.Record(id=second['id'], payload=second)], None)]
        result = await self.store.find_movies('  ALTERNATIVE ', 2025)
        self.assertEqual([m['id'] for m in result], [first['id']])
        self.assertEqual(self.client.scroll.call_args.kwargs['offset'], 5)

    async def test_repeated_loader_preserves_imported_records(self):
        original_movies = catalog.read_movies(constants.DEFAULT_DATA_PATH)
        imported = movie()
        legacy = {**movie(), 'id': imports.TMDB_ID_BASE + 42, 'source': 'tmdb', 'tmdb_id': 42}
        del legacy['wikidata_id']
        self.records[imported['id']] = models.Record(id=imported['id'], payload=imported)
        self.records[legacy['id']] = models.Record(id=legacy['id'], payload=legacy)
        async def upsert(**kwargs):
            for point in kwargs['points']:
                self.records[point.id] = models.Record(id=point.id, payload=point.payload)
        self.client.upsert.side_effect = upsert
        self.client.get_collections.return_value = NS(collections=[NS(name=self.store.collection_name)])
        self.client.count.side_effect = lambda **kwargs: NS(count=len(self.records))
        self.embeddings.encode_documents.side_effect = lambda movies: [VECTOR for _ in movies]
        with tempfile.TemporaryDirectory() as directory:
            self.store.cache = semantic.embedding_cache.EmbeddingCache(directory, self.store.spec)
            for _ in range(2):
                self.assertEqual(await self.store.load(constants.DEFAULT_DATA_PATH), {'loaded': 250, 'count': 252})
        self.assertEqual(self.records[imported['id']].payload, imported)
        self.assertEqual(self.records[legacy['id']].payload, legacy)
        self.assertTrue({m['id'] for m in original_movies} <= self.records.keys())

    async def test_loader_rejects_missing_original_even_with_extra_records(self):
        self.client.get_collections.return_value = NS(collections=[NS(name=self.store.collection_name)])
        self.client.count.return_value = NS(count=251)
        self.client.upsert.side_effect = None
        self.embeddings.encode_documents.side_effect = lambda movies: [VECTOR for _ in movies]
        with tempfile.TemporaryDirectory() as directory:
            self.store.cache = semantic.embedding_cache.EmbeddingCache(directory, self.store.spec)
            with self.assertRaises(errors.CollectionCountError):
                await self.store.load(constants.DEFAULT_DATA_PATH)

    async def test_recommend_excludes_every_source(self):
        item = movie()
        self.records[item['id']] = models.Record(id=item['id'], payload=item)
        self.client.query_points.return_value = NS(points=[])
        await self.store.recommend(item['id'], exclude_ids=[3, 4])
        self.assertEqual(self.client.query_points.call_args.kwargs['query_filter'].must_not[0].has_id,
                         [3, 4, item['id']])
