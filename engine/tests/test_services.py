import copy
import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from qdrant_client import models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from engine import catalog as movie_catalog
from engine import constants
from engine import errors
from engine import services
from engine import validators
from engine.embeddings import spec as embedding_spec
from engine.stores import semantic
from engine.tests import helpers


def collection(vectors):
    return NS(config=NS(params=NS(vectors=vectors)))


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncMock()
        embeddings = AsyncMock()
        embeddings.spec = embedding_spec.SPEC
        self.store = semantic.SemanticMovieStore('http://test:6333', client=self.client, embeddings=embeddings)
        self.catalog = movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)
        self.client.get_collections.return_value = NS(collections=[NS(name='movies')])
        self.client.get_collection.return_value = NS(config=NS(params=NS(vectors={'semantic': models.VectorParams(size=embedding_spec.SPEC.dimensions, distance='Cosine')}, sparse_vectors=None), metadata={'embedding': embedding_spec.SPEC.metadata()}))
        self.client.count.return_value = NS(count=250)
        self.client.retrieve.return_value = [models.Record(id=1, payload=self.catalog[0])]
        self.client.query_points.return_value = NS(points=[])

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
                with helpers.expected_error(self):
                    await self.store.load(path)
                self.assertEqual(self.client.mock_calls, [])

    async def test_catalog_validation_without_file_io(self):
        self.assertIs(validators.validate_catalog(self.catalog), self.catalog)
        for value, key in ((None, 'size'), ([None] * 250, 'object')):
            with self.subTest(key=key), helpers.expected_error(self) as raised:
                validators.validate_catalog(value)
            self.assertEqual(raised.exception._localization[0], key)
        self.assertEqual(self.client.mock_calls, [])

    async def test_invalid_search_limit_precedes_resolution_and_network(self):
        with helpers.expected_error(self) as raised:
            await services.search(self.store, '', self.catalog, limit=0)
        self.assertEqual(raised.exception._localization[0], 'limit')
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
            with helpers.expected_error(self):
                await self.store.recommend(1, limit)
        for value in (-1, 2**64, True, '1'):
            with helpers.expected_error(self):
                await self.store.recommend(value)

    async def test_unknown_id(self):
        self.client.retrieve.return_value = []
        with self.assertRaises(errors.MovieNotFoundError):
            await self.store.recommend(999)
        self.client.query_points.assert_not_called()

    async def test_sdk_errors(self):
        for exc, key in ((httpx.ReadTimeout('timeout'), 'connection'),
                         (ResponseHandlingException(httpx.ConnectError('offline')), 'connection'),
                         (ResponseHandlingException(json.JSONDecodeError('invalid JSON', '', 0)), 'response'),
                         (UnexpectedResponse(503, 'unavailable', b'unavailable', {}), 'http')):
            self.client.retrieve.side_effect = exc
            with helpers.expected_error(self) as raised:
                await self.store.recommend(1)
            self.assertEqual(raised.exception._localization[0], key)

    async def test_resolve(self):
        for query in ('1', 'Матрица', ' мАтРиЦа ', 'матри', 'The Matrix'):
            self.assertEqual(movie_catalog.resolve_movie(query, self.catalog)['id'], 1)
        self.assertEqual(movie_catalog.resolve_movie('1917', self.catalog)['id'], 77)
        for query in ('', '999', '-1', str(2**64), 'absent title'):
            with helpers.expected_error(self):
                movie_catalog.resolve_movie(query, self.catalog)
