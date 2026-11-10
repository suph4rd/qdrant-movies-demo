from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlsplit
import html
import unittest

from fastapi.testclient import TestClient

from engine import services
from engine.stores import semantic
from web import app as web_app
from web.http import security
from web.infrastructure import models
from web.presentation import account as account_presentation
from web.tests import forms


class MarkReturnTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(semantic.SemanticMovieStore, 'count_movies', return_value=250))

    def test_only_local_search_and_account_targets_are_allowed(self):
        fallback = '/account?list=liked&lang=ru'
        for value in (None, '', 'https://evil.test/', '//evil.test/account',
                      '/other', '/account/extra', '/\\evil.test', '/\n/evil.test',
                      '///evil.test', ' /account', '/%61ccount'):
            with self.subTest(value=value):
                self.assertEqual(account_presentation.mark_return_url(value, 'liked', 'ru'), fallback)
        for value in ('/', '/?q=movie&mode=movie&limit=5&lang=ru&result=token',
                      '/account?list=liked&page=2&lang=ru'):
            self.assertEqual(account_presentation.mark_return_url(value, 'liked', 'ru'), value)

    def test_search_mark_returns_to_snapshot_with_updated_button(self):
        user = SimpleNamespace(id=1, email='test@example.com', blocked=False, deleted_at=None)
        mark = SimpleNamespace(movie_id='1', watched=False, liked=False, watchlist=False)
        session = AsyncMock()
        session.scalar.return_value = user
        session.get.side_effect = lambda model, key: mark if model is models.Mark else object()
        session.scalars.return_value = [mark]
        sessions = MagicMock()
        sessions.return_value.__aenter__.return_value = session
        sessions.begin.return_value.__aenter__.return_value = session
        with patch.object(security, 'current_user', return_value=user), TestClient(
                web_app.create_app(), follow_redirects=False) as client:
            client.app.state.database.sessions = sessions
            movie = client.app.state.catalog[0]
            mark.movie_id = str(movie['id'])
            result = {'source': movie, 'recommendations': []}
            with patch.object(services.MovieSearchService, 'search', return_value=result) as search:
                response = forms.post(client, '/search', {'query': movie['title'], 'lang': 'en'})
                location = urlsplit(response.headers['location'])
                target = location.path + '?' + location.query
                first = client.get(target)
                self.assertIn('name="return_url" value="' + html.escape(target, quote=True) + '"', first.text)
                self.assertIn('Add to Liked', first.text)
                response = forms.post(client, '/account/marks', {
                    'movie_id': str(movie['id']), 'flag': 'liked', 'state': 'true',
                    'return_url': target, 'lang': 'en'})
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers['location'], target)
                refreshed = client.get(response.headers['location'])
                self.assertIn('Remove from Liked', refreshed.text)
                self.assertEqual(search.await_count, 1)
            for target in ('https://evil.test/', '//evil.test/account'):
                response = forms.post(client, '/account/marks', {
                    'movie_id': str(movie['id']), 'flag': 'liked', 'state': 'false',
                    'return_url': target, 'lang': 'en'})
                self.assertEqual(response.headers['location'], '/account?list=liked&lang=en')
            target = '/account?list=watchlist&page=2&lang=ru'
            response = forms.post(client, '/account/marks', {
                'movie_id': str(movie['id']), 'flag': 'liked', 'state': 'true',
                'return_url': target, 'lang': 'ru'})
            self.assertEqual(response.headers['location'], target)

    def test_description_snapshot_is_reused_after_redirect(self):
        with TestClient(web_app.create_app(), follow_redirects=False) as client:
            with patch.object(services, 'semantic_search', return_value={
                    'source': None, 'recommendations': []}) as search:
                response = forms.post(client, '/search', {
                    'query': 'space', 'mode': 'description', 'lang': 'en'})
                self.assertIn('result=', response.headers['location'])
                client.get(response.headers['location'])
                client.get(response.headers['location'])
                self.assertEqual(search.await_count, 1)
