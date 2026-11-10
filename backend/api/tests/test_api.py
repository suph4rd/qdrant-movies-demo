import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.engine import catalog, constants, errors as engine_errors, i18n, imports, services
from backend.api.application import dtos, errors
from backend.api.http import api, dependencies, exception_handlers, security
from backend.api.infrastructure import snapshots


def imported_movie(qid=901):
    return {'id': imports.WIKIDATA_ID_BASE + qid, 'wikidata_id': 'Q' + str(qid),
            'title': 'Новый фильм', 'original_title': 'Original movie', 'year': 2005,
            'genres': ['Drama'], 'description': 'English fallback description.',
            'description_language': 'en', 'source': 'wikidata', 'alternative_titles': [],
            'translations': {'en': {'title': 'New movie', 'genres': ['Drama'],
                                     'description': 'English fallback description.'}}}


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(api.router)
        exception_handlers.register_exception_handlers(self.app)
        self.state = self.app.state
        self.state.settings = SimpleNamespace(cookie_secure=False)
        self.state.catalog = catalog.read_movies(constants.DEFAULT_DATA_PATH)
        self.state.movie_store = AsyncMock()
        self.state.movie_store.count_movies.return_value = 250
        self.state.wikidata = AsyncMock()
        self.state.search_results = snapshots.SearchResults()
        self.state.movie_cards = snapshots.MovieCards()
        self.auth = AsyncMock()
        self.auth.current_user.return_value = None
        self.account = AsyncMock()
        self.account.all_marks.return_value = {}
        self.admin = AsyncMock()
        for getter, value in ((dependencies.get_auth_service, self.auth),
                              (dependencies.get_account_service, self.account),
                              (dependencies.get_admin_service, self.admin)):
            self.enterContext(patch.object(dependencies, getter.__name__, return_value=value))
        self.client = self.enterContext(TestClient(self.app))
        self.client.cookies.set(security.CSRF_COOKIE, 'csrf', domain='testserver.local', path='/')

    def post(self, path, body=None, **kwargs):
        return self.client.post('/api' + path, json=body or {},
                                headers={'X-CSRF-Token': self.client.cookies[security.CSRF_COOKIE]}, **kwargs)

    def user(self, role='user'):
        user = dtos.User(1, 'user@example.com', role, False, datetime.now(timezone.utc), None)
        self.auth.current_user.return_value = user
        return user

    def test_context_localizes_without_mutating_catalog_and_issues_private_cookies(self):
        original = copy.deepcopy(self.state.catalog)
        self.client.cookies.clear()
        for lang in ('ru', 'en'):
            response = self.client.get('/api/context?lang=' + lang)
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertIsNone(result['user'])
            self.assertEqual(result['movie_count'], 250)
            self.assertEqual(len(result['catalog']), 250)
            self.assertEqual(result['catalog'][0]['id'], '1')
            self.assertEqual(result['catalog'][0]['title'], i18n.localize_movie(original[0], lang)['title'])
            self.assertNotIn('vector', result['catalog'][0])
            self.assertEqual(result['csrf_token'], self.client.cookies[security.CSRF_COOKIE])
            self.assertEqual(response.headers['content-language'], lang)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            self.assertIn('HttpOnly', response.headers.get('set-cookie'))
        self.assertEqual(original, self.state.catalog)

    def test_expected_count_error_is_optional_but_programming_error_propagates(self):
        self.state.movie_store.count_movies.side_effect = engine_errors.CollectionCountError('count')
        self.assertIsNone(self.client.get('/api/context').json()['movie_count'])
        self.state.movie_store.count_movies.side_effect = TypeError('bug')
        with self.assertRaisesRegex(TypeError, 'bug'):
            self.client.get('/api/context')

    def test_mutations_require_csrf_header_and_matching_origin(self):
        for headers in ({}, {'X-CSRF-Token': 'wrong'},
                        {'X-CSRF-Token': 'csrf', 'Origin': 'https://foreign.example'}):
            response = self.client.post('/api/search?lang=ru', json={'q': '1'}, headers=headers)
            self.assertEqual(response.status_code, 403)
            self.assertIn('error', response.json())
            self.assertEqual(response.headers['content-language'], 'ru')
        self.assertEqual(self.client.post('/api/logout', json={},
            headers={'X-CSRF-Token': 'csrf', 'Origin': 'http://testserver'}).status_code, 200)

    def test_malformed_input_is_localized_and_never_coerces_movie_ids_or_states(self):
        self.user()
        for body in ({'movie_id': 9007199254740993, 'flag': 'liked', 'state': True},
                     {'movie_id': '1', 'flag': 'liked', 'state': 'false'},
                     {'movie_id': '1', 'flag': 'liked', 'state': True, 'unexpected': 1}):
            response = self.post('/account/marks?lang=ru', body)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json(), {'error': 'Некорректный запрос.'})
        self.account.update_mark.assert_not_awaited()
        response = self.client.post('/api/login', content='{', headers={
            'content-type': 'application/json', 'X-CSRF-Token': 'csrf'})
        self.assertEqual(response.status_code, 422)

    def test_search_snapshot_reuse_language_switch_and_imported_references(self):
        self.user()
        movie = imported_movie()
        result = {'groups': [{'source': movie, 'recommendations': [
            {'id': movie['id'] + 1, 'payload': imported_movie(902), 'score': .8}]}],
                  'messages': [{'key': 'import_added', 'params': {'title': movie['title']}}]}
        original = copy.deepcopy(result)
        with patch.object(services.MovieSearchService, 'search', return_value=result) as search:
            token = self.post('/search', {'q': 'New movie', 'mode': 'movie', 'limit': '5'}).json()['token']
            for lang in ('ru', 'en', 'ru'):
                response = self.client.get('/api/search', params={
                    'q': 'New movie', 'mode': 'movie', 'limit': '5', 'result': token, 'lang': lang})
                self.assertEqual(response.json()['movie_count'], 250)
                source = response.json()['result']['groups'][0]['source']
                point = response.json()['result']['groups'][0]['recommendations'][0]
                self.assertEqual(source['id'], str(movie['id']))
                self.assertEqual(point['id'], str(movie['id'] + 1))
                self.assertEqual(point['payload']['id'], str(movie['id'] + 1))
                self.assertEqual(source['wikidata_id'], 'Q901')
                self.assertIn(source['mark_reference'], self.state.movie_cards)
                self.assertEqual(source['title'], 'Новый фильм' if lang == 'ru' else 'New movie')
            search.assert_awaited_once_with('New movie', limit=5, allow_import=True)
        self.assertEqual(result, original)

    def test_expired_or_mismatched_snapshot_is_read_only(self):
        result = {'source': None, 'recommendations': []}
        with patch.object(services.MovieSearchService, 'search', return_value=result) as search:
            token = self.post('/search', {'q': 'new', 'limit': '5'}).json()['token']
            self.client.get('/api/search', params={'q': 'other', 'result': token, 'limit': '5'})
            self.assertFalse(search.call_args.kwargs['allow_import'])
            self.state.search_results.clear()
            self.client.get('/api/search', params={'q': 'new', 'result': token, 'limit': '5', 'allow_import': 'true'})
            self.assertFalse(search.call_args.kwargs['allow_import'])
        self.state.wikidata.search.assert_not_awaited()

    def test_search_errors_remain_cached_and_localized(self):
        with patch.object(services.MovieSearchService, 'search', side_effect=engine_errors.InputValidationError('empty')) as search:
            token = self.post('/search', {'q': '', 'limit': '5'}).json()['token']
            for lang in ('ru', 'en'):
                response = self.client.get('/api/search', params={'q': '', 'limit': '5', 'result': token, 'lang': lang})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['error'], i18n.translate('empty', lang))
            self.assertEqual(search.await_count, 1)
        with patch.object(services.MovieSearchService, 'search', side_effect=TypeError('bug')):
            with self.assertRaisesRegex(TypeError, 'bug'):
                self.post('/search', {'q': '1'})

    def test_bad_modes_limits_and_description_search(self):
        for params in ({'q': '1', 'mode': 'bad'}, {'q': '1', 'limit': '999'}):
            self.assertEqual(self.client.get('/api/search', params=params).status_code, 400)
        with patch.object(services, 'semantic_search', return_value={'source': None, 'recommendations': []}) as search:
            token = self.post('/search', {'q': 'space', 'mode': 'description', 'limit': '5'}).json()['token']
            self.client.get('/api/search', params={'q': 'space', 'mode': 'description', 'limit': '5', 'result': token})
            search.assert_awaited_once()
        self.state.wikidata.search.assert_not_awaited()

    def test_auth_rotates_session_and_csrf_for_each_transition(self):
        self.user()
        self.auth.register.return_value = 'registered'
        self.auth.login.return_value = 'logged-in'
        for path, data, expected in (('/register', {'email': 'a@b.com', 'password': 'secret', 'password_repeat': 'secret'}, 'registered'),
                                     ('/login', {'email': 'a@b.com', 'password': 'secret'}, 'logged-in'),
                                     ('/logout', {}, None)):
            old = self.client.cookies[security.CSRF_COOKIE]
            response = self.post(path, data)
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(old, response.json()['csrf_token'])
            self.assertEqual(response.json()['csrf_token'], self.client.cookies[security.CSRF_COOKIE])
            self.assertEqual(self.client.cookies.get(security.SESSION_COOKIE), expected)
            self.assertEqual(response.json()['user'] is None, expected is None)
        self.auth.logout.assert_awaited_once_with('logged-in')

    def test_duplicate_email_status_and_unexpected_auth_error(self):
        self.auth.register.side_effect = errors.EmailRegistered()
        response = self.post('/register?lang=ru', {'email': 'a@b.com', 'password': 'secret', 'password_repeat': 'secret'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['error'], i18n.translate_message(errors.EmailRegistered().message, 'ru'))
        self.auth.login.side_effect = TypeError('bug')
        with self.assertRaisesRegex(TypeError, 'bug'):
            self.post('/login', {'email': 'a@b.com', 'password': 'secret'})

    def test_account_marks_forward_string_id_boolean_and_reference(self):
        self.user()
        identifier = str(2**64 - 1)
        response = self.post('/account/marks', {'movie_id': identifier, 'flag': 'liked', 'state': True, 'reference': 'verified'})
        self.assertEqual(response.json(), {'marks': {}})
        self.account.update_mark.assert_awaited_once_with(1, identifier, 'liked', True, 'verified')
        self.account.update_mark.side_effect = errors.AuthenticationRequired()
        self.assertEqual(self.post('/account/marks', {'movie_id': '1', 'flag': 'liked', 'state': True}).status_code, 401)

    def test_account_list_pagination_and_localization(self):
        self.user()
        mark = dtos.Mark('1', True, False, False)
        self.account.lists.return_value = [dtos.MovieList('watched', 2, 41, [(self.state.catalog[0], mark)])]
        response = self.client.get('/api/account?list=watched&page=2&lang=ru')
        self.account.lists.assert_awaited_once_with(1, 'watched', 2)
        listing = response.json()['lists'][0]
        self.assertEqual(listing['label'], 'Просмотрено')
        self.assertTrue(listing['has_next'])
        self.assertEqual(listing['movies'][0]['movie']['id'], '1')
        for page in ('0', '-1', '1000001', 'bad', '1' * 5000):
            self.assertEqual(self.client.get('/api/account', params={'page': page}).status_code, 400)

    def test_admin_access_statuses_and_valid_actions(self):
        self.assertEqual(self.client.get('/api/admin/users').status_code, 401)
        self.assertEqual(self.client.get('/api/account').status_code, 401)
        self.user()
        self.assertEqual(self.client.get('/api/admin/users').status_code, 403)
        user = self.user('admin')
        self.admin.list_users.return_value = dtos.UserPage([user], True)
        result = self.client.get('/api/admin/users?q=user&role=admin&state=active&page=2').json()
        self.assertTrue(result['has_next'])
        self.admin.list_users.assert_awaited_once_with('user', 'admin', 'active', 2)
        self.admin.detail.return_value = dtos.UserDetail(user, [])
        self.assertEqual(self.client.get('/api/admin/users/1').json()['user']['id'], 1)
        self.assertEqual(self.post('/admin/users/2', {'action': 'delete', 'confirmation_email': 'user@example.com'}).json(), {'ok': True})
        self.admin.change_user.assert_awaited_once_with('', 2, 'delete', 'user@example.com')
        for error, status in ((errors.AuthenticationRequired(), 401), (errors.AdministratorRequired(), 403),
                              (errors.UserNotFound(), 404), (errors.ScenarioError('Invalid user action.'), 400)):
            self.admin.change_user.side_effect = error
            self.assertEqual(self.post('/admin/users/2', {'action': 'block'}).status_code, status)
        self.admin.change_user.side_effect = TypeError('bug')
        with self.assertRaisesRegex(TypeError, 'bug'):
            self.post('/admin/users/2', {'action': 'block'})

    def test_large_catalog_ids_are_strings_everywhere(self):
        movie = copy.deepcopy(self.state.catalog[0])
        movie['id'] = 2**64 - 1
        self.state.catalog = [movie]
        result = {'source': movie, 'recommendations': [
            {'id': movie['id'], 'payload': movie, 'score': .8}]}
        with patch.object(services.MovieSearchService, 'search', return_value=result):
            response = self.client.get('/api/search?q=large').json()
        group = response['result']['groups'][0]
        for identifier in (group['source']['id'], group['recommendations'][0]['id'],
                           group['recommendations'][0]['payload']['id'],
                           self.client.get('/api/context').json()['catalog'][0]['id']):
            self.assertEqual(identifier, str(2**64 - 1))


class ConcurrentApiLanguageTests(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_language_selection_does_not_mutate_catalog_or_result(self):
        import asyncio
        import httpx

        application = FastAPI()
        application.include_router(api.router)
        exception_handlers.register_exception_handlers(application)
        state = application.state
        state.settings = SimpleNamespace(cookie_secure=False)
        state.catalog = catalog.read_movies(constants.DEFAULT_DATA_PATH)
        state.movie_store = AsyncMock()
        state.movie_store.count_movies.return_value = 250
        state.wikidata = AsyncMock()
        state.search_results = snapshots.SearchResults()
        state.movie_cards = snapshots.MovieCards()
        original = copy.deepcopy(state.catalog)
        auth = AsyncMock()
        auth.current_user.return_value = None
        result = {'source': state.catalog[0], 'recommendations': [
            {'id': 2, 'payload': state.catalog[1], 'score': .9}]}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://test') as client:
            with patch.object(dependencies, 'get_auth_service', return_value=auth), patch.object(
                    services.MovieSearchService, 'search', return_value=result):
                languages = ('en', 'ru') * 10
                responses = await asyncio.gather(*[
                    client.get('/api/search?q=1&lang=' + lang) for lang in languages])
        for response, lang in zip(responses, languages):
            self.assertEqual(response.headers['content-language'], lang)
            self.assertEqual(response.json()['result']['groups'][0]['source']['title'],
                             i18n.localize_movie(original[0], lang)['title'])
        self.assertEqual(state.catalog, original)
