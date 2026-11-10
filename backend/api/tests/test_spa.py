from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from fastapi.testclient import TestClient

from backend.api import app
from backend.api.http import spa


class SpaDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(TemporaryDirectory())
        self.root = Path(self.directory)
        self.enterContext(patch.object(spa, 'CLIENT_PATH', self.root))
        self.client = TestClient(app.create_app())
        self.addCleanup(self.client.close)

    def test_direct_links_refresh_and_assets_use_built_client(self):
        (self.root / 'index.html').write_text('<html><div id="app"></div></html>')
        (self.root / 'assets').mkdir()
        (self.root / 'assets' / 'app-123.js').write_text('window.ready = true;')
        for path in ('/', '/login', '/register', '/account?list=liked&page=2',
                     '/admin/users', '/admin/users/12?lang=ru'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('id="app"', response.text)
                self.assertEqual(response.headers['cache-control'], 'no-cache')
        asset = self.client.get('/assets/app-123.js')
        self.assertEqual(asset.status_code, 200)
        self.assertIn('javascript', asset.headers['content-type'])
        self.assertIn('immutable', asset.headers['cache-control'])

    def test_missing_api_and_static_never_serve_index(self):
        (self.root / 'index.html').write_text('SPA shell')
        for path in ('/api', '/api/missing', '/assets/missing.js', '/static/style.css',
                     '/missing.js', '/assets', '/static', '/assets/../../private.txt'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(set(response.json()), {'error'})
                self.assertNotIn('SPA shell', response.text)
        self.assertEqual(self.client.post('/login', json={}).status_code, 405)
        self.assertEqual(self.client.post('/api/missing', json={}).status_code, 404)

    def test_missing_build_has_actionable_localized_diagnostic(self):
        for lang, expected in [('en', 'Client build is missing'), ('ru', 'Сборка клиента отсутствует')]:
            response = self.client.get('/account?lang=' + lang)
            self.assertEqual(response.status_code, 503)
            self.assertIn(expected, response.json()['error'])
            self.assertIn('npm run build', response.json()['error'])
