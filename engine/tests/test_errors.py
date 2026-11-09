import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from engine import catalog as movie_catalog
from engine import errors
from engine import validators
from engine.embeddings import cache as embedding_cache
from engine.embeddings import client as embedding_client
from engine.embeddings import spec as embedding_spec
from engine.stores import semantic


class ErrorTypeTests(unittest.TestCase):
    def test_input_and_lookup_types_and_localization(self):
        with self.assertRaises(errors.InputValidationError) as raised:
            validators.validate_id(-1)
        error = raised.exception
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error._localization[0], 'id')
        self.assertEqual(error.args, ('id',))
        self.assertNotEqual(errors.format_error(error, 'ru'), errors.format_error(error, 'en'))
        with self.assertRaises(errors.MovieNotFoundError) as raised:
            movie_catalog.resolve_movie('999', [])
        self.assertIsInstance(raised.exception, LookupError)
        self.assertEqual(raised.exception._localization[1]['id'], 999)

    def test_file_and_json_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / 'missing.json'
            with self.assertRaises(FileNotFoundError) as raised:
                movie_catalog.read_movies(missing)
            self.assertIsInstance(raised.exception, OSError)
            self.assertEqual(raised.exception.errno, 2)
            self.assertEqual(raised.exception.filename, str(missing))
            path = Path(directory) / 'invalid.json'
            path.write_text('{bad', encoding='utf-8')
            with self.assertRaises(json.JSONDecodeError) as raised:
                movie_catalog.read_movies(path)
            self.assertIsInstance(raised.exception, json.JSONDecodeError)
            for attr in ('doc', 'pos', 'lineno', 'colno'):
                self.assertEqual(getattr(raised.exception, attr), getattr(json.JSONDecodeError('Expecting property name enclosed in double quotes', '{bad', 1), attr))
            self.assertNotEqual(errors.format_error(raised.exception, 'en'), errors.format_error(raised.exception, 'ru'))


class ExternalErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_embedding_preserves_transport_types_and_request(self):
        request = httpx.Request('GET', 'http://tei/info')
        for kind in (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError):
            original = kind('offline', request=request)
            http = AsyncMock()
            http.request.side_effect = original
            with self.assertRaises(kind) as raised:
                await embedding_client.EmbeddingClient(client=http).check_model()
            self.assertIs(raised.exception, original)
            self.assertIs(raised.exception.request, request)
            self.assertNotEqual(errors.format_error(raised.exception, 'en'), errors.format_error(raised.exception, 'ru'))

    async def test_qdrant_status_retains_diagnostics(self):
        original = UnexpectedResponse(503, 'Unavailable', b'busy', {'Retry-After': '1'})
        client, embeddings = AsyncMock(), AsyncMock()
        embeddings.spec = embedding_spec.SPEC
        client.get_collections.side_effect = original
        store = semantic.SemanticMovieStore('http://qdrant', client=client, embeddings=embeddings)
        with self.assertRaises(UnexpectedResponse) as raised:
            await store.request('get_collections')
        self.assertIsInstance(raised.exception, UnexpectedResponse)
        self.assertIs(raised.exception, original)
        for attr in ('status_code', 'reason_phrase', 'content', 'headers'):
            self.assertEqual(getattr(raised.exception, attr), getattr(original, attr))

    async def test_embedding_status_preserves_response(self):
        request = httpx.Request('GET', 'http://tei/info')
        response = httpx.Response(503, request=request)
        original = httpx.HTTPStatusError('unavailable', request=request, response=response)
        http = AsyncMock()
        http.request.side_effect = original
        with self.assertRaises(httpx.HTTPStatusError) as raised:
            await embedding_client.EmbeddingClient(client=http).check_model()
        self.assertIs(raised.exception.request, request)
        self.assertIs(raised.exception.response, response)
        self.assertIs(raised.exception, original)

    async def test_missing_index_uses_status_and_preserves_cause(self):
        client, embeddings = AsyncMock(), AsyncMock()
        embeddings.spec = embedding_spec.SPEC
        original = UnexpectedResponse(404, 'Not Found', b'absent', {})
        client.get_collection.side_effect = original
        store = semantic.SemanticMovieStore('http://qdrant', client=client, embeddings=embeddings)
        with self.assertRaises(errors.SemanticSchemaError) as raised:
            await store.check_index()
        self.assertIsInstance(raised.exception.__cause__, UnexpectedResponse)
        self.assertIs(raised.exception.__cause__, original)
        client.upsert.assert_not_awaited()

    async def test_wrapped_programming_error_propagates(self):
        client, embeddings = AsyncMock(), AsyncMock()
        embeddings.spec = embedding_spec.SPEC
        original = ResponseHandlingException(TypeError('bug'))
        client.get_collections.side_effect = original
        store = semantic.SemanticMovieStore('http://qdrant', client=client, embeddings=embeddings)
        with self.assertRaises(ResponseHandlingException) as raised:
            await store.request('get_collections')
        self.assertIs(raised.exception, original)


class AnnotationTests(unittest.TestCase):
    def test_annotation_preserves_exception_state_and_existing_cause(self):
        request = httpx.Request('GET', 'http://tei/info')
        examples = [
            FileNotFoundError(2, 'missing', '/catalog.json'),
            json.JSONDecodeError('invalid', '{bad', 1),
            UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid start byte'),
            httpx.ReadTimeout('offline', request=request),
            UnexpectedResponse(503, 'Unavailable', b'busy', {}),
        ]
        for original in examples:
            with self.subTest(kind=type(original)):
                cause = RuntimeError('original cause')
                original.__cause__ = cause
                args, message = original.args, str(original)
                attributes = dict(original.__dict__)
                self.assertFalse(errors.is_expected_error(original))
                self.assertIs(errors.annotate_error(original, 'read', detail=original), original)
                self.assertTrue(errors.is_expected_error(original))
                self.assertEqual(original.args, args)
                self.assertEqual(str(original), message)
                self.assertIs(original.__cause__, cause)
                for name, value in attributes.items():
                    self.assertIs(getattr(original, name), value)
                self.assertNotEqual(errors.format_error(original), errors.format_error(original, 'ru'))

    def test_catalog_reraises_original_file_json_and_unicode_errors(self):
        examples = [
            FileNotFoundError(2, 'missing', '/catalog.json'),
            json.JSONDecodeError('invalid', '{bad', 1),
            UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid start byte'),
        ]
        for original in examples:
            with self.subTest(kind=type(original)):
                with patch.object(Path, 'read_text', side_effect=original):
                    with self.assertRaises(type(original)) as raised:
                        movie_catalog.read_movies('unused.json')
                self.assertIs(raised.exception, original)
                self.assertTrue(errors.is_expected_error(original))

    def test_cache_reraises_original_os_error_with_localized_path(self):
        original = PermissionError(13, 'denied', '/cache')
        cause = RuntimeError('existing cause')
        original.__cause__ = cause
        cache = embedding_cache.EmbeddingCache('/cache')
        vector = [1.0] + [0.0] * (embedding_spec.SPEC.dimensions - 1)
        with patch.object(Path, 'mkdir', side_effect=original):
            with self.assertRaises(PermissionError) as raised:
                cache.put('text', vector)
        self.assertIs(raised.exception, original)
        self.assertIs(original.__cause__, cause)
        for lang in ('en', 'ru'):
            self.assertIn('/cache', errors.format_error(original, lang))
        self.assertNotEqual(errors.format_error(original), errors.format_error(original, 'ru'))

    def test_unannotated_errors_remain_unexpected(self):
        for original in (ValueError('bug'), TypeError('bug'), OSError('bug')):
            self.assertFalse(errors.is_expected_error(original))
            self.assertEqual(errors.format_error(original), str(original))


class ResponseAnnotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_response_handling_preserves_original_and_cause(self):
        request = httpx.Request('GET', 'http://qdrant')
        for source in (json.JSONDecodeError('invalid', '{', 1),
                       httpx.ConnectError('offline', request=request), OSError('offline')):
            with self.subTest(kind=type(source)):
                original = ResponseHandlingException(source)
                original.__cause__ = source
                args, message = original.args, str(original)
                client, embeddings = AsyncMock(), AsyncMock()
                embeddings.spec = embedding_spec.SPEC
                client.get_collections.side_effect = original
                store = semantic.SemanticMovieStore('http://qdrant', client=client, embeddings=embeddings)
                with self.assertRaises(ResponseHandlingException) as raised:
                    await store.request('get_collections')
                self.assertIs(raised.exception, original)
                self.assertIs(original.source, source)
                self.assertIs(original.__cause__, source)
                self.assertEqual(original.args, args)
                self.assertEqual(str(original), message)
                self.assertTrue(errors.is_expected_error(original))

    async def test_embedding_reraises_original_json_error(self):
        original = json.JSONDecodeError('invalid', '{', 1)
        http = AsyncMock()
        http.request.side_effect = original
        with self.assertRaises(json.JSONDecodeError) as raised:
            await embedding_client.EmbeddingClient(client=http).check_model()
        self.assertIs(raised.exception, original)
        self.assertTrue(errors.is_expected_error(original))
