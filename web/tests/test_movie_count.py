from unittest.mock import patch
import unittest

from fastapi.testclient import TestClient

from engine import errors, i18n, services
from web import app as web_app
from web.tests import forms


class MovieCountWebTests(unittest.TestCase):
    def setUp(self):
        self.app = web_app.create_app()
        self.client = self.enterContext(TestClient(self.app, follow_redirects=False))

    def test_current_count_in_both_languages_including_zero(self):
        with patch.object(self.app.state.movie_store, 'count_movies') as count:
            for lang in ('en', 'ru'):
                for value in (0, 250, 251):
                    count.return_value = value
                    page = self.client.get('/', params={'lang': lang})
                    self.assertIn(i18n.translate('eyebrow', lang, count=value), page.text)
                    self.assertNotIn(i18n.translate('count_unavailable', lang), page.text)
            self.assertEqual(count.await_count, 6)

    def test_import_redirect_and_snapshot_refresh_read_current_count(self):
        with patch.object(self.app.state.movie_store, 'count_movies', side_effect=[250, 251, 251]) as count, patch.object(
                services.MovieSearchService, 'search', return_value={'groups': [], 'messages': []}) as search:
            self.assertIn(i18n.translate('eyebrow', count=250), self.client.get('/?lang=en').text)
            redirect = forms.post(self.client, '/search', data={'query': 'New movie', 'lang': 'en'})
            for _ in range(2):
                page = self.client.get(redirect.headers['location'])
                self.assertIn(i18n.translate('eyebrow', count=251), page.text)
            search.assert_awaited_once_with('New movie', limit=5, allow_import=True)
            self.assertEqual(count.await_count, 3)

    def test_expected_count_failure_is_localized_without_hiding_results(self):
        with patch.object(self.app.state.movie_store, 'count_movies', side_effect=errors.IndexStateError('response')), patch.object(
                services.MovieSearchService, 'search', return_value={'source': None, 'recommendations': []}):
            for lang in ('en', 'ru'):
                page = self.client.get('/', params={'q': '1', 'lang': lang})
                self.assertEqual(page.status_code, 200)
                self.assertIn(i18n.translate('count_unavailable', lang), page.text)
                self.assertIn(i18n.translate('no_results', lang), page.text)
                self.assertNotIn(i18n.translate('response', lang), page.text)

    def test_unexpected_count_error_propagates(self):
        failure = TypeError('bug')
        with patch.object(self.app.state.movie_store, 'count_movies', side_effect=failure):
            with self.assertRaises(TypeError) as raised:
                self.client.get('/')
        self.assertIs(raised.exception, failure)
