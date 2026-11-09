from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from contextlib import ExitStack

from engine import catalog as movie_catalog
from engine import constants
from engine import errors
from engine import i18n as engine_i18n
from engine import services
from web import app as web_app


class LanguageLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = {name: value for name, value in attrs}
        if tag == 'a' and 'hreflang' in attrs:
            self.links[attrs['hreflang']] = attrs['href']


class WebLocalizationTests(unittest.TestCase):
    def setUp(self):
        self.stack = self.enterContext(ExitStack())
        self.app = web_app.create_app(web_app.Settings(qdrant_url='http://test:6333'))
        self.client = self.stack.enter_context(TestClient(self.app, follow_redirects=False))
        self.catalog = movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)

    def assert_language(self, response, lang):
        self.assertEqual(response.headers['Content-Language'], lang)
        self.assertIn(f'<html lang="{lang}">', response.text)
        self.assertIn(engine_i18n.translate('heading', lang), response.text)
        self.assertIn(f'name="lang" value="{lang}"', response.text)

    def test_selection_priority_and_cookie(self):
        self.assert_language(self.client.get('/'), 'en')
        self.client.cookies.clear()
        self.assert_language(self.client.get('/', headers={'Accept-Language': 'de, ru-RU;q=0.8, en;q=0.5'}), 'ru')
        self.assert_language(self.client.get('/', headers={'Accept-Language': 'en'}), 'ru')
        self.assert_language(self.client.get('/?lang=en', headers={'Accept-Language': 'ru'}), 'en')
        self.assert_language(self.client.get('/?lang=de', headers={'Accept-Language': 'ru'}), 'en')
        self.client.cookies.set('lang', 'de')
        self.assert_language(self.client.get('/?lang=fr', headers={'Accept-Language': 'ru'}), 'ru')
        self.client.cookies.clear()
        self.assert_language(self.client.get('/', headers={'Accept-Language': 'de, fr'}), 'en')

    def test_switch_preserves_parameters_and_post_redirect_get(self):
        for lang in ('en', 'ru'):
            query = ' Матрица & <test> '
            with patch.object(services.MovieSearchService, 'search', side_effect=errors.MovieNotFoundError('search_saved_only')):
                response = self.client.get('/', params={'q': query, 'limit': '20', 'lang': lang})
            links = LanguageLinks(response.text).links
            self.assertEqual(set(links), {'en', 'ru'})
            for target, link in links.items():
                self.assertEqual(parse_qs(urlsplit(link).query), {'q': [query], 'limit': ['20'], 'mode': ['movie'], 'lang': [target]})
                with patch.object(services.MovieSearchService, 'search', side_effect=errors.MovieNotFoundError('search_saved_only')):
                    self.assert_language(self.client.get(link), target)
            with patch.object(services.MovieSearchService, 'search', side_effect=errors.IndexStateError('response')) as search:
                response = self.client.post('/search', data={'query': query, 'limit': '20', 'lang': lang})
                self.assertEqual(response.status_code, 303)
                search.assert_called_once()
                redirect_params = parse_qs(urlsplit(response.headers['Location']).query)
                self.assertTrue(redirect_params.pop('result'))
                self.assertEqual(redirect_params, {'q': [query], 'limit': ['20'], 'mode': ['movie'], 'lang': [lang]})
                for _ in range(2):
                    page = self.client.get(response.headers['Location'])
                    self.assert_language(page, lang)
                    self.assertIn(engine_i18n.translate('response', lang), page.text)
                    self.assertIn('<option value="20" selected>', page.text)
                    self.assertNotIn('<test>', page.text)

    def test_initial_switch_does_not_submit_empty_query(self):
        for link in LanguageLinks(self.client.get('/').text).links.values():
            self.assertNotIn('q', parse_qs(urlsplit(link).query))
            self.assertNotIn('role="alert"', self.client.get(link).text)

    def test_old_payload_metadata_is_replaced_from_local_catalog(self):
        store = self.app.state.movie_store
        for lang in ('en', 'ru'):
            for query in ('The Matrix', 'Матрица'):
                with patch.object(store, 'recommend', return_value={
                    'source': {'title': 'obsolete source'},
                    'recommendations': [{'id': 2, 'score': .9876, 'payload': {'title': 'obsolete recommendation'}}],
                }):
                    response = self.client.get('/', params={'q': query, 'lang': lang})
                self.assert_language(response, lang)
                self.assertIn(engine_i18n.localize_movie(self.catalog[0], lang)['title'], response.text)
                self.assertIn(engine_i18n.localize_movie(self.catalog[1], lang)['title'], response.text)
                self.assertIn('0.9876', response.text)
                self.assertNotIn('obsolete', response.text)

    def test_localized_validation_and_ambiguity_without_network(self):
        for lang in ('en', 'ru'):
            for params, key in (({'q': ''}, 'empty'), ({'q': '1', 'limit': '6'}, 'web_limit')):
                with patch.object(self.app.state.movie_store.client, 'retrieve') as api:
                    response = self.client.get('/', params={**params, 'lang': lang})
                    api.assert_not_called()
                self.assertIn(engine_i18n.translate(key, lang), response.text)
            with patch.object(self.app.state.movie_store, 'find_movies', return_value=[]):
                response = self.client.get('/', params={'q': 'absent title', 'lang': lang})
            self.assertIn(engine_i18n.translate('search_saved_only', lang), response.text)
