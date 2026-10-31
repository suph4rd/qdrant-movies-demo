from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit
import unittest
from unittest.mock import patch

from engine import DEFAULT_DATA_PATH, services
from engine.i18n import localize_movie, translate
from web.app import create_app


class LanguageLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and 'hreflang' in attrs:
            self.links[attrs['hreflang']] = attrs['href']


class WebLocalizationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True})
        self.client = self.app.test_client()
        self.catalog = services.read_movies(DEFAULT_DATA_PATH)

    def assert_language(self, response, lang):
        self.assertEqual(response.headers['Content-Language'], lang)
        self.assertIn(f'<html lang="{lang}">', response.text)
        self.assertIn(translate('heading', lang), response.text)
        self.assertIn(f'name="lang" value="{lang}"', response.text)

    def test_selection_priority_and_cookie(self):
        self.assert_language(self.client.get('/'), 'en')
        self.client = self.app.test_client()
        self.assert_language(self.client.get('/', headers={'Accept-Language': 'de, ru-RU;q=0.8, en;q=0.5'}), 'ru')
        self.assert_language(self.client.get('/', headers={'Accept-Language': 'en'}), 'ru')
        self.assert_language(self.client.get('/?lang=en', headers={'Accept-Language': 'ru'}), 'en')
        self.assert_language(self.client.get('/?lang=de', headers={'Accept-Language': 'ru'}), 'en')
        self.client.set_cookie('lang', 'de')
        self.assert_language(self.client.get('/?lang=fr', headers={'Accept-Language': 'ru'}), 'ru')
        self.client = self.app.test_client()
        self.assert_language(self.client.get('/', headers={'Accept-Language': 'de, fr'}), 'en')

    def test_switch_preserves_parameters_and_post_redirect_get(self):
        for lang in ('en', 'ru'):
            query = ' Матрица & <test> '
            response = self.client.get('/', query_string={'q': query, 'limit': '20', 'lang': lang})
            links = LanguageLinks(response.text).links
            self.assertEqual(set(links), {'en', 'ru'})
            for target, link in links.items():
                self.assertEqual(parse_qs(urlsplit(link).query), {'q': [query], 'limit': ['20'], 'lang': [target]})
                self.assert_language(self.client.get(link), target)
            with patch.object(services, 'search', side_effect=services.DemoError('response')) as search:
                response = self.client.post('/search', data={'query': query, 'limit': '20', 'lang': lang})
                self.assertEqual(response.status_code, 303)
                search.assert_not_called()
                self.assertEqual(parse_qs(urlsplit(response.location).query), {'q': [query], 'limit': ['20'], 'lang': [lang]})
                for _ in range(2):
                    page = self.client.get(response.location)
                    self.assert_language(page, lang)
                    self.assertIn(translate('response', lang), page.text)
                    self.assertIn('<option value="20" selected>', page.text)
                    self.assertNotIn('<test>', page.text)

    def test_initial_switch_does_not_submit_empty_query(self):
        for link in LanguageLinks(self.client.get('/').text).links.values():
            self.assertNotIn('q', parse_qs(urlsplit(link).query))
            self.assertNotIn('role="alert"', self.client.get(link).text)

    def test_old_payload_metadata_is_replaced_from_local_catalog(self):
        store = self.app.extensions['movie_store']
        for lang in ('en', 'ru'):
            for query in ('The Matrix', 'Матрица'):
                with patch.object(store, 'request', side_effect=[
                    [{'id': 1, 'payload': {'title': 'obsolete source'}}],
                    {'points': [{'id': 2, 'score': .9876, 'payload': {'title': 'obsolete recommendation'}}]},
                ]):
                    response = self.client.get('/', query_string={'q': query, 'lang': lang})
                self.assert_language(response, lang)
                self.assertIn(localize_movie(self.catalog[0], lang)['title'], response.text)
                self.assertIn(localize_movie(self.catalog[1], lang)['title'], response.text)
                self.assertIn('0.9876', response.text)
                self.assertNotIn('obsolete', response.text)

    def test_localized_validation_and_ambiguity_without_network(self):
        for lang in ('en', 'ru'):
            for params, key in (({'q': ''}, 'empty'), ({'q': 'absent title'}, 'not_found'), ({'q': '1', 'limit': '6'}, 'web_limit')):
                with patch.object(services.requests, 'request') as api:
                    response = self.client.get('/', query_string={**params, 'lang': lang})
                    api.assert_not_called()
                self.assertIn(translate(key, lang), response.text)
            response = self.client.get('/', query_string={'q': 'Гарри', 'lang': lang})
            title = 'Harry Potter' if lang == 'en' else 'Гарри Поттер'
            self.assertIn(title, response.text.split('role="alert">')[1])
