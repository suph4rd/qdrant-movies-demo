import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from engine import catalog as movie_catalog
from engine import i18n as engine_i18n
from engine.stores import factory
from web import app as web_app


class LifecycleTests(unittest.TestCase):
    def test_factory_does_no_io_and_lifespan_closes_store(self):
        store = AsyncMock()
        with patch.object(movie_catalog, 'read_movies', wraps=movie_catalog.read_movies) as read, patch.object(
                factory, 'create_store', return_value=store) as create_store:
            app = web_app.create_app()
            read.assert_not_called()
            create_store.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'handler failed'):
                with TestClient(app) as client:
                    original = copy.deepcopy(app.state.catalog)
                    client.get('/?lang=en')
                    client.get('/?lang=ru')
                    self.assertEqual(app.state.catalog, original)
                    read.assert_called_once()
                    raise RuntimeError('handler failed')
            store.close.assert_awaited_once()


    def test_each_startup_owns_a_separate_lifespan_and_store(self):
        first_store, second_store = AsyncMock(), AsyncMock()
        with patch.object(factory, 'create_store', side_effect=[first_store, second_store]), patch.object(
                movie_catalog, 'read_movies', wraps=movie_catalog.read_movies) as read:
            app = web_app.create_app()
            first_lifespan = app.router.lifespan_context(app)
            second_lifespan = app.router.lifespan_context(app)
            self.assertIsNot(first_lifespan, second_lifespan)
            for expected in (first_store, second_store):
                with TestClient(app) as client:
                    self.assertIs(app.state.movie_store, expected)
                    self.assertEqual(client.get('/').status_code, 200)
                expected.close.assert_awaited_once()
            self.assertEqual(read.call_count, 2)


class ConcurrentLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_searches_keep_language_local(self):
        app = web_app.create_app()
        async with app.router.lifespan_context(app):
            original = copy.deepcopy(app.state.catalog)

            async def recommend(movie_id, limit=5, exclude_ids=None):
                await asyncio.sleep(0)
                return {'source': {'id': 1}, 'recommendations': [{'id': 2, 'score': .9, 'payload': {}}]}

            with patch.object(app.state.movie_store, 'recommend', side_effect=recommend):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    responses = await asyncio.gather(*[
                        client.get('/?q=1&lang=' + lang) for lang in ('en', 'ru') * 10])
            for response, lang in zip(responses, ('en', 'ru') * 10):
                self.assertEqual(response.headers['content-language'], lang)
                self.assertIn(engine_i18n.translate('heading', lang), response.text)
                self.assertEqual(response.text.count('<article>'), 1)
            self.assertEqual(app.state.catalog, original)
