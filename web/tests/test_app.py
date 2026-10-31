"""Автономные проверки Flask."""
import os
import tempfile
import unittest
from unittest.mock import patch

from engine import DEFAULT_DATA_PATH, services
from web.app import create_app


DATA = DEFAULT_DATA_PATH


class WebTests(unittest.TestCase):
    def setUp(self):
        with patch.object(services, 'request') as api:
            self.app = create_app({'TESTING': True, 'QDRANT_URL': 'http://test:6333'})
            api.assert_not_called()
        self.client = self.app.test_client()
        self.catalog = services.read_movies(DATA)

    def test_initial(self):
        with patch.object(services, 'request') as api:
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
            search.assert_called_once_with('http://test:6333', ' Матрица ', self.catalog)
        html = response.get_data(as_text=True)
        self.assertIn('value=" Матрица "', html)
        self.assertLess(html.index('</form>'), html.index('Похожие на'))
        self.assertEqual(html.count('<article>'), 5)
        self.assertIn('0.9000', html)
        self.assertIn(self.catalog[1]['description'], html)

    def test_input_errors_do_not_call_qdrant(self):
        with patch.object(services, 'request') as api:
            for query, message in (('', 'Введите'), ('999', 'Неизвестный ID'), ('-1', 'ID должен')):
                response = self.client.get('/', query_string={'q': query})
                self.assertIn(message, response.get_data(as_text=True))
            api.assert_not_called()

    def test_unavailable_qdrant_and_escaping(self):
        query = '<script>alert(1)</script>'
        with patch.object(services, 'search', side_effect=services.DemoError('Нет соединения с Qdrant')):
            html = self.client.get('/', query_string={'q': query}).get_data(as_text=True)
        self.assertIn('Нет соединения с Qdrant', html)
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
                    page = client.get('/')
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
