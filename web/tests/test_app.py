import os
import tempfile
import unittest
from unittest.mock import patch

from engine import DEFAULT_DATA_PATH, services
from web.app import create_app


DATA = DEFAULT_DATA_PATH


class WebTests(unittest.TestCase):
    def setUp(self):
        with patch.object(services.requests, 'request') as api:
            self.app = create_app({'TESTING': True, 'QDRANT_URL': 'http://test:6333'})
            api.assert_not_called()
        self.client = self.app.test_client()
        self.client.environ_base['HTTP_ACCEPT_LANGUAGE'] = 'ru'
        self.catalog = services.read_movies(DATA)

    def test_apps_have_independent_stores_and_configuration(self):
        with patch.object(services.requests, 'request') as api:
            other = create_app({'TESTING': True, 'QDRANT_URL': 'http://other:6333',
                                'MOVIES_PATH': 'missing-catalog.json'})
            api.assert_not_called()
        store = self.app.extensions['movie_store']
        other_store = other.extensions['movie_store']
        self.assertIsNot(store, other_store)
        self.assertEqual(store.base_url, 'http://test:6333')
        self.assertEqual(other_store.base_url, 'http://other:6333')
        with patch.object(services.requests, 'request', side_effect=services.requests.exceptions.ConnectionError('offline')) as api:
            for app in (self.app, other, self.app):
                with patch.object(services, 'read_movies', return_value=self.catalog) as read:
                    html = app.test_client().get('/?q=1').get_data(as_text=True)
                    read.assert_called_once_with(app.config['MOVIES_PATH'])
                self.assertIn(app.config['QDRANT_URL'], html)
                self.assertEqual(api.call_args.args[1],
                                 app.config['QDRANT_URL'] + '/collections/movies/points')
        self.assertEqual({rule.endpoint for rule in self.app.url_map.iter_rules()},
                         {'index', 'search', 'static'})

    def test_initial(self):
        with patch.object(services.requests, 'request') as api:
            response = self.client.get('/')
            api.assert_not_called()
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
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
            search.assert_called_once_with(self.app.extensions['movie_store'], ' Матрица ', self.catalog, limit=5)
        html = response.get_data(as_text=True)
        self.assertIn('value=" Матрица "', html)
        self.assertLess(html.index('</form>'), html.index('Похожие на'))
        self.assertEqual(html.count('<article>'), 5)
        self.assertIn('0.9000', html)
        self.assertIn(self.catalog[1]['description'], html)

    def test_limit_options_and_persistence(self):
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('<option value="5" selected>', html)
        for value in ('5', '10', '20', '50'):
            self.assertIn(f'<option value="{value}"', html)
            with patch.object(services, 'search', side_effect=services.DemoError('response')) as search:
                redirect = self.client.post('/search', data={'query': '1', 'limit': value})
                self.assertEqual(redirect.status_code, 303)
                self.assertIn('limit=' + value, redirect.headers['Location'])
                for _ in range(2):
                    html = self.client.get(redirect.headers['Location']).get_data(as_text=True)
                    self.assertIn(f'<option value="{value}" selected>', html)
                    self.assertIn('Некорректный ответ Qdrant', html)
                search.assert_called_with(self.app.extensions['movie_store'], '1', self.catalog, limit=int(value))
            with patch.object(services, 'search', return_value={
                'source': self.catalog[0], 'recommendations': [],
            }) as search:
                html = self.client.get('/', query_string={'q': '1', 'limit': value}).get_data(as_text=True)
                self.assertIn(f'<option value="{value}" selected>', html)
                search.assert_called_once_with(self.app.extensions['movie_store'], '1', self.catalog, limit=int(value))

    def test_invalid_limits(self):
        for value in ('', '0', '6', '249', '250', '-1', '5.0', 'abc', '<script>'):
            with self.subTest(value=value), patch.object(services, 'search') as search:
                response = self.client.post('/search', data={'query': 'Матрица', 'limit': value})
                html = self.client.get(response.headers['Location']).get_data(as_text=True)
                self.assertIn('Выберите количество', html)
                self.assertIn('value="Матрица"', html)
                self.assertIn('Некорректное значение:', html)
                self.assertNotIn('<script>', html)
                search.assert_not_called()

    def test_input_errors_do_not_call_qdrant(self):
        with patch.object(services.requests, 'request') as api:
            for query, message in (('', 'Введите'), ('999', 'Неизвестный ID'), ('-1', 'ID должен')):
                response = self.client.get('/', query_string={'q': query})
                self.assertIn(message, response.get_data(as_text=True))
            api.assert_not_called()

    def test_unavailable_qdrant_and_escaping(self):
        query = '<script>alert(1)</script>'
        with patch.object(services, 'search', side_effect=services.DemoError('response')):
            html = self.client.get('/', query_string={'q': query}).get_data(as_text=True)
        self.assertIn('Некорректный ответ Qdrant', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('Traceback', html)

    def test_empty_results(self):
        with patch.object(services, 'search', return_value={
            'source': self.catalog[0], 'recommendations': [],
        }):
            html = self.client.get('/?q=1').get_data(as_text=True)
        self.assertIn('Похожих фильмов пока нет', html)

    def test_missing_post_field(self):
        response = self.client.post('/search')
        self.assertEqual(response.status_code, 303)
        html = self.client.get(response.headers['Location']).get_data(as_text=True)
        self.assertIn('Введите название или ID', html)


    def test_assets_and_catalog_from_other_directory(self):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                app = create_app({'TESTING': True})
                self.assertEqual(app.config['MOVIES_PATH'], DATA)
                with app.test_client() as client:
                    page = client.get('/?lang=ru')
                    self.assertIn('value="Матрица"', page.get_data(as_text=True))
                    self.assertIn('/static/style.css', page.get_data(as_text=True))
                    css = client.get('/static/style.css')
                    self.assertEqual(css.status_code, 200)
                    self.assertEqual(css.mimetype, 'text/css')
                    self.assertTrue(css.get_data())
                    css.close()
            finally:
                os.chdir(original)


if __name__ == '__main__':
    unittest.main()
