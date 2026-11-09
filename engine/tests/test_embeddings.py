import unittest
from unittest.mock import AsyncMock, patch

import httpx

from engine import catalog as movie_catalog
from engine import constants
from engine.embeddings import cache as embedding_cache
from engine.embeddings import client as embedding_client
from engine.embeddings import spec as embedding_spec
from engine.embeddings import texts as embedding_texts
from engine.stores import factory
from engine.tests import helpers


INFO = {'model_id': embedding_spec.SPEC.model, 'model_sha': embedding_spec.SPEC.revision,
        'model_dtype': embedding_spec.SPEC.dtype, 'model_type': {'embedding': {'pooling': 'mean'}}}
VECTOR = [-0.1, 0.2] * 192


class EmbeddingTests(unittest.IsolatedAsyncioTestCase):
    async def make_client(self, answer, info=INFO):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=info if request.url.path == '/info' else answer)
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        return embedding_client.EmbeddingClient('http://tei', client=http), requests

    async def test_batch_and_query_text(self):
        client, requests = await self.make_client([VECTOR, VECTOR])
        movies = movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)[:2]
        self.assertEqual(await client.encode_documents(movies), [VECTOR, VECTOR])
        import json
        self.assertEqual(json.loads(requests[1].content)['inputs'], [embedding_texts.document_text(m) for m in movies])
        self.assertEqual(embedding_texts.document_text(movies[0]),
                         'passage: Title: The Matrix\nGenres: science fiction, action\n'
                         'Description: A hacker discovers that the familiar world is a computer simulation.')
        client, requests = await self.make_client([VECTOR])
        self.assertEqual(await client.encode_query('  космос  '), VECTOR)
        self.assertEqual(json.loads(requests[-1].content)['inputs'], ['query: космос'])
        self.assertEqual(requests[-1].extensions['timeout']['read'], 15)

    async def test_bad_vectors(self):
        for answer in ([], [VECTOR, VECTOR], [[1]*383], [[0]*384],
                       [[float('nan')]*384], [[float('inf')]*384], [[True]*384],
                       [[1e308]*384], {'vector': VECTOR}, ['bad']):
            with self.subTest(answer=str(answer)[:30]):
                http = AsyncMock()
                response = unittest.mock.Mock()
                response.json.side_effect = [INFO, answer]
                http.request.return_value = response
                client = embedding_client.EmbeddingClient(client=http)
                with helpers.expected_error(self) as raised:
                    await client.encode_query('test')
                self.assertEqual(raised.exception._localization[0], 'embedding_response')

    async def test_identity_and_empty_input(self):
        client, requests = await self.make_client([VECTOR], info={**INFO, 'model_sha': 'different'})
        with helpers.expected_error(self) as raised:
            await client.encode_query('test')
        self.assertEqual(raised.exception._localization[0], 'embedding_model')
        self.assertEqual(len(requests), 1)
        for query in ('', '  ', None):
            with helpers.expected_error(self) as raised:
                await client.encode_query(query)
            self.assertEqual(raised.exception._localization[0], 'semantic_empty')
        self.assertEqual(len(requests), 1)

    async def test_failures_and_ownership(self):
        for error in (httpx.ReadTimeout('timeout'), httpx.ConnectError('offline')):
            http = AsyncMock()
            http.request.side_effect = error
            client = embedding_client.EmbeddingClient(client=http)
            with helpers.expected_error(self) as raised:
                await client.encode_query('test')
            self.assertEqual(raised.exception._localization[0], 'embedding_unavailable')
            await client.close()
            http.aclose.assert_not_awaited()
        for status, body, key in ((503, 'offline', 'embedding_unavailable'),
                                   (200, 'not json', 'embedding_response')):
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, text=body))) as http:
                with helpers.expected_error(self) as raised:
                    await embedding_client.EmbeddingClient(client=http).encode_query('test')
                self.assertEqual(raised.exception._localization[0], key)
        http = AsyncMock()
        with patch('engine.embeddings.client.httpx.AsyncClient', return_value=http) as factory:
            client = embedding_client.EmbeddingClient()
            factory.assert_called_once_with(timeout=15)
            await client.close()
        http.aclose.assert_awaited_once()


class EmbeddingCacheTests(unittest.TestCase):
    def test_content_key_and_corrupt_entries(self):
        from dataclasses import replace
        import hashlib
        import json
        from pathlib import Path
        import tempfile


        with tempfile.TemporaryDirectory() as directory:
            cache = embedding_cache.EmbeddingCache(directory)
            text = 'passage: Title: The Matrix'
            expected = hashlib.sha256(json.dumps(
                {'text': text, 'embedding': embedding_spec.SPEC.metadata()}, ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
            self.assertEqual(cache.key(text), expected)
            self.assertIsNone(cache.get(text))
            cache.put(text, VECTOR)
            self.assertEqual(cache.get(text), VECTOR)
            self.assertNotEqual(cache.key(text), cache.key(text + '.'))
            self.assertNotEqual(cache.key(text), embedding_cache.EmbeddingCache(
                directory, replace(embedding_spec.SPEC, text_version='next')).key(text))
            entry = Path(directory) / (expected + '.json')
            for value in ('invalid json', '[]', json.dumps({'key': 'wrong', 'vector': VECTOR}),
                          json.dumps({'key': expected, 'vector': [0] * embedding_spec.SPEC.dimensions})):
                entry.write_text(value, encoding='utf-8')
                self.assertIsNone(cache.get(text))
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def test_cache_write_failure(self):
        from pathlib import Path
        import tempfile


        with tempfile.TemporaryDirectory() as directory:
            blocked = Path(directory) / 'file'
            blocked.write_text('occupied', encoding='utf-8')
            with helpers.expected_error(self) as raised:
                embedding_cache.EmbeddingCache(blocked).put('text', VECTOR)
            self.assertEqual(raised.exception._localization[0], 'embedding_cache')
