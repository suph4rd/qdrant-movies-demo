from engine import catalog as movie_catalog, store as movie_store
from engine.errors import DemoError
import os
import tempfile
import unittest
from unittest.mock import patch

from engine import DEFAULT_DATA_PATH, services
from web.app import create_app, Settings
from fastapi.testclient import TestClient
from contextlib import ExitStack


DATA = DEFAULT_DATA_PATH


class WebTests(unittest.TestCase):
    def setUp(self):
        self.stack = self.enterContext(ExitStack())
        self.app = create_app(Settings(qdrant_url='http://test:6333'))
        self.client = self.stack.enter_context(TestClient(self.app, follow_redirects=False))
        self.catalog = movie_catalog.read_movies(DEFAULT_DATA_PATH)
        self.client.headers['Accept-Language'] = 'ru'

    def test_apps_have_independent_stores_and_configuration(self):
        with patch.object(movie_catalog, 'read_movies', wraps=movie_catalog.read_movies) as read:
            other = create_app(Settings(qdrant_url='http://other:6333'))
            read.assert_not_called()
            with TestClient(other) as client:
                self.assertIsNot(self.app.state.movie_store, other.state.movie_store)
                self.assertIsNot(self.app.state.catalog, other.state.catalog)
                client.get('/')
                client.get('/?lang=ru')
                read.assert_called_once_with(DEFAULT_DATA_PATH)

    def test_invalid_catalog_fails_startup(self):
        with self.assertRaises(DemoError), TestClient(create_app(Settings(movies_path='missing.json'))):
            pass

    def test_initial(self):
        with patch.object(self.app.state.movie_store.client, 'retrieve') as api:
            response = self.client.get('/')
            api.assert_not_called()
        self.assertEqual(response.status_code, 200)
        html = response.text
        self.assertIn('Начните с любимого фильма', html)
        self.assertIn('value="Матрица"', html)

    def test_post_redirect_and_results(self):
        result = {'source': self.catalog[0], 'recommendations': [
            {'id': m['id'], 'payload': m, 'score': .9} for m in self.catalog[1:6]
        ]}
        with patch.object(services, 'search', return_value=result) as search:
            response = self.client.post('/search', data={'query': ' Матрица '})
            self.assertEqual(response.status_code, 303)
            search.assert_not_called()
            response = self.client.get(response.headers['Location'])
            search.assert_called_once_with(self.app.state.movie_store, ' Матрица ', self.catalog, limit=5)
        html = response.text
        self.assertIn('value=" Матрица "', html)
        self.assertLess(html.index('</form>'), html.index('Похожие на'))
        self.assertEqual(html.count('<article>'), 5)
        self.assertIn('0.9000', html)
        self.assertIn(self.catalog[1]['description'], html)

    def test_limit_options_and_persistence(self):
        html = self.client.get('/').text
        self.assertIn('<option value="5" selected>', html)
        for value in ('5', '10', '20', '50'):
            self.assertIn(f'<option value="{value}"', html)
            with patch.object(services, 'search', side_effect=DemoError('response')) as search:
                redirect = self.client.post('/search', data={'query': '1', 'limit': value})
                self.assertEqual(redirect.status_code, 303)
                self.assertIn('limit=' + value, redirect.headers['Location'])
                for _ in range(2):
                    html = self.client.get(redirect.headers['Location']).text
                    self.assertIn(f'<option value="{value}" selected>', html)
                    self.assertIn('Некорректный ответ Qdrant', html)
                search.assert_called_with(self.app.state.movie_store, '1', self.catalog, limit=int(value))
            with patch.object(services, 'search', return_value={
                'source': self.catalog[0], 'recommendations': [],
            }) as search:
                html = self.client.get('/', params={'q': '1', 'limit': value}).text
                self.assertIn(f'<option value="{value}" selected>', html)
                search.assert_called_once_with(self.app.state.movie_store, '1', self.catalog, limit=int(value))

    def test_invalid_limits(self):
        for value in ('', '0', '6', '249', '250', '-1', '5.0', 'abc', '<script>'):
            with self.subTest(value=value), patch.object(services, 'search') as search:
                response = self.client.post('/search', data={'query': 'Матрица', 'limit': value})
                html = self.client.get(response.headers['Location']).text
                self.assertIn('Выберите количество', html)
                self.assertIn('value="Матрица"', html)
                self.assertIn('Некорректное значение:', html)
                self.assertNotIn('<script>', html)
                search.assert_not_called()

    def test_input_errors_do_not_call_qdrant(self):
        with patch.object(self.app.state.movie_store.client, 'retrieve') as api:
            for query, message in (('', 'Введите'), ('999', 'Неизвестный ID'), ('-1', 'ID должен')):
                response = self.client.get('/', params={'q': query})
                self.assertIn(message, response.text)
            api.assert_not_called()

    def test_unavailable_qdrant_and_escaping(self):
        query = '<script>alert(1)</script>'
        with patch.object(services, 'search', side_effect=DemoError('response')):
            html = self.client.get('/', params={'q': query}).text
        self.assertIn('Некорректный ответ Qdrant', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('Traceback', html)

    def test_empty_results(self):
        with patch.object(services, 'search', return_value={
            'source': self.catalog[0], 'recommendations': [],
        }):
            html = self.client.get('/?q=1').text
        self.assertIn('Похожих фильмов пока нет', html)

    def test_unknown_recommendation_id_renders_error(self):
        with patch.object(services, 'search', return_value={
            'source': self.catalog[0],
            'recommendations': [{'id': 999, 'score': .9, 'payload': {}}],
        }):
            response = self.client.get('/?q=1&lang=en')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Unknown movie ID: 999', response.text)
        self.assertNotIn('<article>', response.text)

    def test_missing_post_field(self):
        response = self.client.post('/search')
        self.assertEqual(response.status_code, 303)
        html = self.client.get(response.headers['Location']).text
        self.assertIn('Введите название или ID', html)


    def test_assets_and_catalog_from_other_directory(self):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                app = create_app()
                self.assertEqual(app.state.settings.movies_path, DATA)
                with TestClient(app) as client:
                    page = client.get('/?lang=ru')
                    self.assertIn('value="Матрица"', page.text)
                    self.assertIn('/static/style.css', page.text)
                    css = client.get('/static/style.css')
                    self.assertEqual(css.status_code, 200)
                    self.assertEqual(css.headers['content-type'].split(';')[0], 'text/css')
                    self.assertTrue(css.content)
                    css.close()
            finally:
                os.chdir(original)


if __name__ == '__main__':
    unittest.main()
