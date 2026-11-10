from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import ast
import unittest

from sqlalchemy import exc as sa_errors

from engine import errors as engine_errors
from engine import services as engine_services
from web.application import dtos
from web.application import errors
from web.application.services import account, admin, auth, search
from web.infrastructure import clock
from web.infrastructure import passwords
from web.infrastructure import snapshots


class SessionFactory:
    def __init__(self):
        self.active = False
        self.outcomes = []
        self.session = SimpleNamespace(begin=self.transaction)

    @asynccontextmanager
    async def __call__(self):
        yield self.session

    @asynccontextmanager
    async def transaction(self):
        self.active = True
        try:
            yield self.session
        except BaseException:
            self.outcomes.append('rollback')
            raise
        else:
            self.outcomes.append('commit')
        finally:
            self.active = False

    @asynccontextmanager
    async def begin(self):
        async with self.transaction():
            yield self.session


def user(user_id=1, role='user', **values):
    return SimpleNamespace(**{'id': user_id, 'email': f'user{user_id}@example.com',
        'password_hash': 'encoded', 'role': role, 'blocked': False,
        'created_at': clock.now(), 'deleted_at': None, **values})


class SearchServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.results = snapshots.SearchResults()
        self.store = AsyncMock()
        self.service = search.SearchService([], self.store, object(), self.results)
        self.params = {'q': 'space', 'mode': 'description', 'limit': '5'}

    async def test_snapshot_returns_raw_result_and_checks_all_parameters(self):
        raw = {'source': None, 'recommendations': []}
        with patch.object(engine_services, 'semantic_search', return_value=raw) as execute:
            token = await self.service.submit(self.params)
            params = {**self.params, 'result': token}
            self.assertIs(await self.service.search(params), raw)
            self.assertIs(await self.service.search(params), raw)
            execute.assert_awaited_once_with(self.store, 'space', limit=5)
            for key, value in [('q', 'ocean'), ('mode', 'movie'), ('limit', '10')]:
                self.assertIsNone(self.results.matching(token, tuple(
                    {**self.params, key: value}[name] for name in ('q', 'mode', 'limit'))))
            await self.service.search({**params, 'q': 'ocean'})
            self.assertEqual(execute.await_count, 2)

    async def test_expected_error_is_replayed_but_unexpected_error_is_not_cached(self):
        failure = engine_errors.InputValidationError('web_limit')
        with patch.object(engine_services, 'semantic_search', side_effect=failure):
            token = await self.service.submit(self.params)
        with self.assertRaises(engine_errors.InputValidationError) as caught:
            await self.service.search({**self.params, 'result': token})
        self.assertIs(caught.exception, failure)
        with patch.object(engine_services, 'semantic_search', side_effect=TypeError('bug')):
            with self.assertRaises(TypeError):
                await self.service.submit(self.params)
        self.assertEqual(len(self.results), 1)

    async def test_empty_search_and_invalid_parameters_do_not_call_engine(self):
        self.assertIsNone(await self.service.search({}))
        for params in ({'mode': 'unknown'}, {'limit': '0'}):
            with self.assertRaises(engine_errors.InputValidationError):
                await self.service.search(params)
        self.store.recommend.assert_not_awaited()

    async def test_movie_search_receives_injected_dependencies_and_import_policy(self):
        with patch.object(engine_services, 'MovieSearchService') as service_type:
            service_type.return_value.search = AsyncMock(return_value={'source': None, 'recommendations': []})
            params = {**self.params, 'mode': 'movie'}
            await self.service.submit(params)
            service_type.assert_called_once_with(self.store, self.service.catalog, self.service.wikidata)
            service_type.return_value.search.assert_awaited_once_with('space', limit=5, allow_import=True)

    def test_fifo_limits_and_reads_do_not_refresh_eviction_order(self):
        first = self.results.put({'params': ('a', 'movie', '5')})
        second = self.results.put({'params': ('b', 'movie', '5')})
        self.results.get(first)
        for _ in range(127):
            self.results.put({})
        self.assertEqual(len(self.results), 128)
        self.assertNotIn(first, self.results)
        self.assertIn(second, self.results)


class AuthServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.factory = SessionFactory()
        self.users = AsyncMock()
        self.tokens = AsyncMock()
        self.service = auth.AuthService(self.factory, self.users, self.tokens)
        self.users.add.return_value = user()
        self.users.by_email.return_value = user()

    async def test_registration_normalizes_email_and_rotates_session_in_transaction(self):
        async def add(*args):
            self.assertTrue(self.factory.active)
        self.tokens.add.side_effect = add
        with patch.object(passwords, 'hash_password', return_value='encoded'):
            token = await self.service.register(' USER@Example.com ', 'valid-password', 'valid-password', 'old')
        self.users.add.assert_awaited_once_with(self.factory.session, 'user@example.com', 'encoded')
        self.tokens.delete.assert_awaited_once_with(self.factory.session, passwords.token_hash('old'))
        args = self.tokens.add.await_args.args
        self.assertEqual(args[1:3], (passwords.token_hash(token), 1))
        self.assertEqual(self.factory.outcomes, ['commit'])

    async def test_registration_duplicate_rolls_back_and_preserves_unexpected_failure(self):
        for sqlstate in ('23505', '23514'):
            failure = sa_errors.IntegrityError('insert', {}, SimpleNamespace(sqlstate=sqlstate))
            self.users.add.side_effect = failure
            with patch.object(passwords, 'hash_password', return_value='encoded'):
                expected = errors.EmailRegistered if sqlstate == '23505' else sa_errors.IntegrityError
                with self.assertRaises(expected) as caught:
                    await self.service.register('user@example.com', 'valid-password', 'valid-password')
            if sqlstate == '23505':
                self.assertIs(caught.exception.__cause__, failure)
            else:
                self.assertIs(caught.exception, failure)
        self.assertEqual(self.factory.outcomes, ['rollback', 'rollback'])
        self.tokens.add.assert_not_awaited()

    async def test_login_rehashes_and_replaces_session(self):
        existing = self.users.by_email.return_value
        with patch.object(passwords, 'verify_password', return_value=True), patch.object(
                type(passwords.PASSWORD_HASHER), 'check_needs_rehash', return_value=True), patch.object(
                passwords, 'hash_password', return_value='new-encoded'):
            token = await self.service.login('USER1@example.com', 'valid-password', 'previous')
        self.assertEqual(existing.password_hash, 'new-encoded')
        self.assertEqual(self.tokens.add.await_args.args[1], passwords.token_hash(token))
        self.assertEqual(self.factory.outcomes, ['commit'])

    async def test_unknown_blocked_deleted_and_invalid_credentials_never_create_session(self):
        for existing in (None, user(blocked=True), user(deleted_at=clock.now())):
            self.users.by_email.return_value = existing
            with patch.object(passwords, 'verify_password', return_value=True) as verify:
                with self.assertRaisesRegex(errors.ScenarioError, 'Invalid email or password'):
                    await self.service.login('invalid', 'x' * 129)
                verify.assert_awaited_once_with(existing.password_hash if existing else passwords.DUMMY_HASH, '')
        self.tokens.add.assert_not_awaited()
        self.assertEqual(self.factory.outcomes, ['rollback'] * 3)

    async def test_current_user_returns_dto_and_logout_revokes_token(self):
        self.assertIsNone(await self.service.current_user(None))
        self.tokens.user.assert_not_awaited()
        self.tokens.user.return_value = user()
        result = await self.service.current_user('token')
        self.assertIsInstance(result, dtos.User)
        self.assertFalse(hasattr(result, 'password_hash'))
        await self.service.logout('token')
        self.tokens.delete.assert_awaited_once_with(self.factory.session, passwords.token_hash('token'))

    async def test_admin_bootstrap_uses_lock_and_rejects_existing_admin(self):
        async def count(session):
            self.assertTrue(self.factory.active)
            self.users.admin_lock.assert_awaited_once_with(session)
            return 1
        self.users.active_admin_count.side_effect = count
        with patch.object(passwords, 'hash_password', return_value='encoded'):
            with self.assertRaisesRegex(errors.ScenarioError, 'already exists'):
                await self.service.create_admin('admin@example.com', 'valid-password')
        self.users.add.assert_not_awaited()
        self.assertEqual(self.factory.outcomes, ['rollback'])


class AccountServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.factory = SessionFactory()
        self.users = AsyncMock()
        self.users.lock.return_value = user()
        self.marks = AsyncMock()
        self.mark = SimpleNamespace(movie_id='1', watched=False, liked=True, watchlist=True)
        self.marks.get_or_create.return_value = self.mark
        self.marks.saved.return_value = object()
        self.service = account.AccountService(self.factory, [{'id': 1, 'title': 'Movie'}],
            snapshots.MovieCards(), self.users, self.marks)

    async def test_updates_serialize_user_and_preserve_exclusive_states(self):
        async def saved(session, movie_id):
            self.assertTrue(self.factory.active)
            self.users.lock.assert_awaited_with(session, 1)
            return object()
        self.marks.saved.side_effect = saved
        await self.service.update_mark(1, '01', 'watched', True)
        self.assertEqual((self.mark.watched, self.mark.liked, self.mark.watchlist), (True, True, False))
        await self.service.update_mark(1, '1', 'watchlist', True)
        self.assertEqual((self.mark.watched, self.mark.liked, self.mark.watchlist), (False, True, True))
        self.assertEqual(self.factory.outcomes, ['commit', 'commit'])

    async def test_unknown_snapshot_is_rejected_before_mark_creation(self):
        self.marks.saved.return_value = None
        with self.assertRaisesRegex(errors.ScenarioError, 'Invalid movie selection'):
            await self.service.update_mark(1, '999', 'liked', True)
        self.marks.save.assert_not_awaited()
        self.marks.get_or_create.assert_not_awaited()
        self.assertEqual(self.factory.outcomes, ['rollback'])

    async def test_blocked_or_deleted_user_cannot_write(self):
        for existing in (None, user(blocked=True), user(deleted_at=clock.now())):
            self.users.lock.return_value = existing
            with self.assertRaises(errors.AuthenticationRequired):
                await self.service.update_mark(1, '1', 'liked', True)
        self.marks.saved.assert_not_awaited()

    async def test_catalog_snapshot_is_saved_and_returned_marks_are_plain_data(self):
        self.marks.saved.return_value = None
        await self.service.update_mark(1, '1', 'liked', False)
        self.marks.save.assert_awaited_once_with(self.factory.session, '1', {'id': 1, 'title': 'Movie'})
        self.marks.all.return_value = [self.mark]
        self.assertIsInstance((await self.service.all_marks(1))['1'], dtos.Mark)
        self.marks.list.return_value = (1, [(SimpleNamespace(snapshot={'id': 1}), self.mark)])
        result = await self.service.lists(1, 'liked', 2)
        self.assertEqual([listing.page for listing in result], [1, 2, 1])
        self.assertIsInstance(result[0].movies[0][1], dtos.Mark)


class AdminServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.factory = SessionFactory()
        self.users = AsyncMock()
        self.tokens = AsyncMock()
        self.actor = user(1, 'admin')
        self.target = user(2)
        self.tokens.user.return_value = self.actor
        self.users.get.return_value = self.target
        self.service = admin.AdminService(self.factory, AsyncMock(), self.users, self.tokens)

    async def test_block_delete_restore_revoke_sessions_inside_locked_transaction(self):
        async def actor(*args, **kwargs):
            self.assertTrue(self.factory.active)
            self.users.admin_lock.assert_awaited_with(self.factory.session)
            return self.actor
        self.tokens.user.side_effect = actor
        async def revoke(*args):
            self.assertTrue(self.factory.active)
        self.tokens.revoke.side_effect = revoke
        for action in ('block', 'unblock', 'delete', 'restore'):
            await self.service.change_user('token', 2, action, ' USER2@example.com ')
        self.assertIsNone(self.target.deleted_at)
        self.assertTrue(self.target.blocked)
        self.assertEqual(self.tokens.revoke.await_count, 3)
        self.assertEqual(self.factory.outcomes, ['commit'] * 4)
        self.tokens.user.assert_awaited_with(self.factory.session, passwords.token_hash('token'), lock=True)
        self.users.get.assert_awaited_with(self.factory.session, 2, lock=True)

    async def test_self_and_last_admin_protection(self):
        for target, message in ((self.actor, 'yourself'), (user(2, 'admin'), 'last active')):
            for action in ('block', 'demote', 'delete'):
                self.users.get.return_value = target
                self.users.active_admin_count.return_value = 1
                with self.assertRaisesRegex(errors.ScenarioError, message):
                    await self.service.change_user('token', target.id, action, target.email)
        self.tokens.revoke.assert_not_awaited()
        self.assertEqual(self.factory.outcomes, ['rollback'] * 6)

    async def test_actor_is_revalidated_after_lock(self):
        for actor, expected in ((None, errors.AuthenticationRequired), (user(), errors.AdministratorRequired)):
            self.tokens.user.return_value = actor
            with self.assertRaises(expected):
                await self.service.change_user('token', 2, 'block')
        self.users.get.assert_not_awaited()
        self.tokens.revoke.assert_not_awaited()

    async def test_invalid_actions_deleted_targets_and_confirmation(self):
        for action, confirmation, deleted in [('invalid', '', False), ('delete', 'wrong', False),
                ('restore', '', False), ('unblock', '', True), ('promote', '', True)]:
            self.target.deleted_at = clock.now() if deleted else None
            with self.assertRaises(errors.ScenarioError):
                await self.service.change_user('token', 2, action, confirmation)
        self.tokens.revoke.assert_not_awaited()
        self.assertFalse(self.target.blocked)
        self.assertEqual(self.target.role, 'user')

    async def test_filters_and_user_dtos(self):
        with self.assertRaises(errors.ScenarioError):
            await self.service.list_users('', 'root', '', 1)
        self.users.list.assert_not_awaited()
        self.users.list.return_value = [user(i) for i in range(21)]
        page = await self.service.list_users('query', 'user', 'active', 2)
        self.assertTrue(page.has_next)
        self.assertEqual(len(page.users), 20)
        self.assertIsInstance(page.users[0], dtos.User)
        self.users.list.assert_awaited_once_with(self.factory.session, 'query', 'user', 'active', 20, 21)


class LayerBoundaryTests(unittest.TestCase):
    def test_services_and_repositories_do_not_import_http_or_presentation(self):
        root = Path(__file__).resolve().parents[1]
        forbidden = {'fastapi', 'starlette', 'web.presentation', 'web.http', 'web.app'}
        for directory in ('application', 'infrastructure'):
            for path in (root / directory).rglob('*.py'):
                for node in ast.walk(ast.parse(path.read_text())):
                    if isinstance(node, ast.Import):
                        names = [item.name for item in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        names = [node.module or '', *[f'{node.module}.{item.name}' for item in node.names]]
                    else:
                        continue
                    for name in names:
                        self.assertFalse(any(name == item or name.startswith(item + '.') for item in forbidden),
                                         f'{path}: {name}')

    def test_http_and_presentation_do_not_import_sql_or_models(self):
        root = Path(__file__).resolve().parents[1]
        paths = [*(root / 'http').rglob('*.py'), *(root / 'presentation').rglob('*.py')]
        for path in paths:
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    names = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or '', *[f'{node.module}.{item.name}' for item in node.names]]
                else:
                    continue
                for name in names:
                    self.assertFalse(any(name == prefix or name.startswith(prefix + '.')
                        for prefix in ('sqlalchemy', 'web.infrastructure')), f'{path}: {name}')
