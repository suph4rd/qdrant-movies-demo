from unittest.mock import AsyncMock, patch
import unittest

from fastapi.testclient import TestClient

from backend.engine import imports
from backend.api import app as web_app


def imported_movie(qid=901):
    return {'id': imports.WIKIDATA_ID_BASE + qid, 'wikidata_id': 'Q' + str(qid),
            'title': 'Новый фильм', 'original_title': 'Original movie', 'year': 2005,
            'genres': ['Drama'], 'description': 'English fallback description.',
            'description_language': 'en', 'source': 'wikidata', 'alternative_titles': [],
            'translations': {'en': {'title': 'New movie', 'genres': ['Drama'],
                                     'description': 'English fallback description.'}}}


class WikidataLifecycleTests(unittest.TestCase):
    def test_factory_defers_client_creation_and_closes_owned_client(self):
        wikidata = AsyncMock()
        store = AsyncMock()
        with patch.object(web_app.wikidata, 'WikidataClient', return_value=wikidata) as create, patch.object(
                web_app.factory, 'create_store', return_value=store):
            app = web_app.create_app()
            create.assert_not_called()
            with TestClient(app) as client:
                self.assertIn(client.get('/').status_code, (200, 503))
                self.assertFalse(hasattr(app.state.settings, 'tmdb_api_token'))
            create.assert_called_once_with()
        wikidata.close.assert_awaited_once()
        store.close.assert_awaited_once()

    def test_store_closes_when_wikidata_close_fails(self):
        wikidata, store = AsyncMock(), AsyncMock()
        wikidata.close.side_effect = RuntimeError('close failed')
        with patch.object(web_app.wikidata, 'WikidataClient', return_value=wikidata), patch.object(
                web_app.factory, 'create_store', return_value=store):
            with self.assertRaisesRegex(RuntimeError, 'close failed'), TestClient(
                    web_app.create_app()):
                pass
        store.close.assert_awaited_once()

    def test_store_closes_when_wikidata_creation_fails(self):
        store = AsyncMock()
        with patch.object(web_app.wikidata, 'WikidataClient', side_effect=RuntimeError('create failed')), patch.object(
                web_app.factory, 'create_store', return_value=store):
            with self.assertRaisesRegex(RuntimeError, 'create failed'), TestClient(web_app.create_app()):
                pass
        store.close.assert_awaited_once()
