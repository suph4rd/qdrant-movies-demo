from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException

from backend.engine import i18n
from backend.engine.stores import factory
from backend.api import app
from backend.api.application import errors
from backend.api.http import dependencies
from backend.api.http.transport import security
from backend.api.http.adapters import security as authentication
from backend.api.tests import forms


class ServiceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(factory, 'create_store', return_value=AsyncMock()))
        self.client = self.enterContext(TestClient(app.create_app(), follow_redirects=False))
        self.user = SimpleNamespace(id=1, email='user@example.com', role='admin')
        self.enterContext(patch.object(authentication, 'current_user', return_value=self.user))

    def test_admin_errors_are_localized_with_original_status(self):
        service = AsyncMock()
        with patch.object(dependencies, 'get_admin_service', return_value=service):
            for lang in ('en', 'ru'):
                for failure, status in ((errors.AuthenticationRequired(), 401),
                        (errors.AdministratorRequired(), 403), (errors.UserNotFound(), 404),
                        (errors.ScenarioError('Invalid user action.'), 400)):
                    service.change_user.side_effect = failure
                    response = forms.post(self.client, '/admin/users/2?lang=' + lang, {'action': 'block'})
                    self.assertEqual(response.status_code, status)
                    self.assertIn(i18n.translate_message(failure.message, lang), response.text)
                    self.assertEqual(response.headers['content-language'], lang)

    def test_admin_unexpected_errors_propagate(self):
        service = AsyncMock()
        service.change_user.side_effect = TypeError('bug')
        with patch.object(dependencies, 'get_admin_service', return_value=service):
            with self.assertRaisesRegex(TypeError, 'bug'):
                forms.post(self.client, '/admin/users/2', {'action': 'block'})

    def test_http_error_preserves_headers_and_localized_page(self):
        service = AsyncMock()
        with patch.object(dependencies, 'get_admin_service', return_value=service):
            for lang in ('en', 'ru'):
                message = i18n.translate_message('Authentication required', lang)
                service.change_user.side_effect = HTTPException(
                    401, message, headers={'WWW-Authenticate': 'Bearer'})
                response = forms.post(self.client, '/admin/users/2?lang=' + lang, {'action': 'block'})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.headers['www-authenticate'], 'Bearer')
                self.assertEqual(response.headers['content-language'], lang)
                self.assertIn(message, response.text)

    def test_account_maps_locked_user_failure_and_retains_csrf_check(self):
        service = AsyncMock()
        service.update_mark.side_effect = errors.AuthenticationRequired()
        with patch.object(dependencies, 'get_account_service', return_value=service):
            response = self.client.post('/api/account/marks', json={'flag': 'liked', 'state': True})
            self.assertEqual(response.status_code, 403)
            service.update_mark.assert_not_awaited()
            response = forms.post(self.client, '/account/marks?lang=ru',
                                  {'movie_id': '1', 'flag': 'liked', 'state': True})
            self.assertEqual(response.status_code, 401)
            self.assertIn(i18n.translate_message('Authentication required', 'ru'), response.text)
