import copy
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from engine import errors
from engine import imports
from engine import services
from web import app as web_app
from web.tests import test_i18n


def imported_movie(qid=901):
    return {'id': imports.WIKIDATA_ID_BASE + qid, 'wikidata_id': 'Q' + str(qid),
            'title': 'Новый фильм', 'original_title': 'Original movie', 'year': 2005,
            'genres': ['Drama'], 'description': 'English fallback description.',
            'description_language': 'en', 'source': 'wikidata', 'alternative_titles': [],
            'translations': {'en': {'title': 'New movie', 'genres': ['Drama'],
                                     'description': 'English fallback description.'}}}


class ImportWebTests(unittest.TestCase):
    def setUp(self):
        self.wikidata = AsyncMock()
        self.enterContext(patch.object(web_app.wikidata, 'WikidataClient', return_value=self.wikidata))
        self.app = web_app.create_app()
        self.client = self.enterContext(TestClient(self.app, follow_redirects=False))

    def test_post_import_snapshot_refresh_language_and_payload(self):
        movie = imported_movie()
        result = {'groups': [{'source': movie, 'recommendations': [
            {'id': movie['id'] + 1, 'payload': imported_movie(902), 'score': .8}]}],
                  'messages': [{'key': 'import_added', 'params': {'title': movie['title']}}]}
        original = copy.deepcopy(result)
        with patch.object(services.MovieSearchService, 'search', return_value=result) as search:
            redirect = self.client.post('/search', data={'query': 'New movie (2005)', 'lang': 'ru'})
            self.assertEqual(redirect.status_code, 303)
            search.assert_awaited_once_with('New movie (2005)', limit=5, allow_import=True)
            location = redirect.headers['location']
            for _ in range(2):
                response = self.client.get(location)
                self.assertIn('Добавлен фильм', response.text)
                self.assertIn('Новый фильм', response.text)
                self.assertIn('(2005) · Original movie · Q901', response.text)
                self.assertIn('Язык описания: EN', response.text)
                self.assertIn('краткое описание', response.text)
                self.assertIn('https://www.wikidata.org/wiki/Q902', response.text)
            for lang, link in test_i18n.LanguageLinks(response.text).links.items():
                page = self.client.get(link)
                self.assertEqual(page.headers['content-language'], lang)
                self.assertIn('result=', link)
                self.assertIn('New movie' if lang == 'en' else 'Новый фильм', page.text)
            self.assertEqual(search.await_count, 1)
        self.assertEqual(result, original)

    def test_get_and_tampered_snapshot_are_read_only(self):
        result = {'groups': [], 'messages': []}
        with patch.object(services.MovieSearchService, 'search', return_value=result) as search:
            redirect = self.client.post('/search', data={'query': 'New movie'})
            params = {key: value[0] for key, value in parse_qs(urlsplit(redirect.headers['location']).query).items()}
            params['q'] = 'Other movie'
            self.client.get('/?' + urlencode(params))
            self.assertFalse(search.call_args.kwargs['allow_import'])
            self.client.get('/?q=Other+movie&allow_import=true')
            self.assertFalse(search.call_args.kwargs['allow_import'])
        self.wikidata.search.assert_not_awaited()

    def test_partial_errors_are_localized_after_redirect(self):
        result = {'groups': [], 'messages': [
            {'key': 'import_added', 'params': {'title': 'Saved'}},
            {'key': 'import_failed', 'params': {'title': 'Skipped',
                                               'error': errors.InputValidationError('wikidata_invalid')}}]}
        with patch.object(services.MovieSearchService, 'search', return_value=result):
            redirect = self.client.post('/search', data={'query': 'New movie', 'lang': 'ru'})
            page = self.client.get(redirect.headers['location'])
        self.assertIn('Добавлен фильм: Saved', page.text)
        self.assertIn('Не удалось обработать Skipped', page.text)
        self.assertIn('Некорректный ответ Wikidata', page.text)

    def test_legacy_tmdb_records_keep_source_links(self):
        movie = imported_movie()
        movie.pop('wikidata_id')
        movie.update(id=imports.TMDB_ID_BASE + 901, tmdb_id=901, source='tmdb')
        result = {'groups': [{'source': movie, 'recommendations': [
            {'id': movie['id'], 'payload': movie, 'score': .8}]}], 'messages': []}
        with patch.object(services.MovieSearchService, 'search', return_value=result):
            response = self.client.get('/?q=New+movie&lang=en')
        self.assertIn('https://www.themoviedb.org/movie/901', response.text)
        self.assertIn('Source: TMDB', response.text)
        self.assertNotIn('Short description from Wikidata', response.text)
        self.assertNotIn('Wikidata provides a short description', response.text)

    def test_snapshots_are_bounded(self):
        with patch.object(services.MovieSearchService, 'search', return_value={'groups': [], 'messages': []}):
            for _ in range(130):
                self.client.post('/search', data={'query': 'New movie'})
        self.assertEqual(len(self.app.state.search_results), 128)

    def test_description_never_imports(self):
        with patch.object(services, 'semantic_search', return_value={'source': None, 'recommendations': []}):
            redirect = self.client.post('/search', data={'query': 'space', 'mode': 'description'})
            self.client.get(redirect.headers['location'])
        self.wikidata.search.assert_not_awaited()


class WikidataLifecycleTests(unittest.TestCase):
    def test_factory_defers_client_creation_and_closes_owned_client(self):
        wikidata = AsyncMock()
        store = AsyncMock()
        with patch.object(web_app.wikidata, 'WikidataClient', return_value=wikidata) as create, patch.object(
                web_app.factory, 'create_store', return_value=store):
            app = web_app.create_app()
            create.assert_not_called()
            with TestClient(app) as client:
                self.assertEqual(client.get('/').status_code, 200)
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
