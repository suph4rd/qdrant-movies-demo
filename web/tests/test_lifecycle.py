from engine import catalog as movie_catalog, store as movie_store
from engine.errors import DemoError
import asyncio
import copy
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from engine.i18n import translate
from web.app import create_app


class LifecycleTests(unittest.TestCase):
    def test_factory_does_no_io_and_lifespan_closes_store(self):
        store = AsyncMock()
        with patch.object(movie_catalog, 'read_movies', wraps=movie_catalog.read_movies) as read, patch.object(
                movie_store, 'QdrantMovieStore', return_value=store) as factory:
            app = create_app()
            read.assert_not_called()
            factory.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, 'handler failed'):
                with TestClient(app) as client:
                    original = copy.deepcopy(app.state.catalog)
                    client.get('/?lang=en')
                    client.get('/?lang=ru')
                    self.assertEqual(app.state.catalog, original)
                    read.assert_called_once()
                    raise RuntimeError('handler failed')
            store.close.assert_awaited_once()


class ConcurrentLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_searches_keep_language_local(self):
        app = create_app()
        async with app.router.lifespan_context(app):
            original = copy.deepcopy(app.state.catalog)

            async def recommend(movie_id, limit=5):
                await asyncio.sleep(0)
                return {'source': {}, 'recommendations': [{'id': 2, 'score': .9, 'payload': {}}]}

            with patch.object(app.state.movie_store, 'recommend', side_effect=recommend):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    responses = await asyncio.gather(*[
                        client.get('/?q=1&lang=' + lang) for lang in ('en', 'ru') * 10])
            for response, lang in zip(responses, ('en', 'ru') * 10):
                self.assertEqual(response.headers['content-language'], lang)
                self.assertIn(translate('heading', lang), response.text)
                self.assertEqual(response.text.count('<article>'), 1)
            self.assertEqual(app.state.catalog, original)
