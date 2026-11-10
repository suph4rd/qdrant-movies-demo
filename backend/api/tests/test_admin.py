from datetime import timedelta
from types import SimpleNamespace
import asyncio
import os
import unittest
import uuid

from fastapi import FastAPI
from sqlalchemy.ext import asyncio as sa_async
import httpx
import sqlalchemy as sa

from backend.api.http import security
from backend.api.http import api, exception_handlers
from backend.api.infrastructure import clock
from backend.api.infrastructure import database
from backend.api.infrastructure import models
from backend.api.infrastructure import passwords


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL to a separate PostgreSQL database')
class AdminTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = 'test_admin_' + uuid.uuid4().hex
        self.root_engine = sa_async.create_async_engine(os.environ['TEST_DATABASE_URL'])
        async with self.root_engine.begin() as connection:
            await connection.execute(sa.text('CREATE SCHEMA ' + self.schema))
        url = sa.engine.make_url(os.environ['TEST_DATABASE_URL']).update_query_dict(
            {'options': '-csearch_path=' + self.schema})
        self.database = database.Database(url)
        async with self.database.engine.begin() as connection:
            await connection.run_sync(models.Base.metadata.create_all)
        self.app = FastAPI()
        self.app.state.database = self.database
        self.app.state.settings = SimpleNamespace(cookie_secure=False)
        self.app.include_router(api.router)
        exception_handlers.register_exception_handlers(self.app)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.admin_id, self.admin_token = await self.add_user('admin@example.com', role='admin')
        self.user_id, self.user_token = await self.add_user('user@example.com')
        self.client.cookies.set(security.SESSION_COOKIE, self.admin_token)
        self.client.cookies.set(security.CSRF_COOKIE, 'csrf')

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.database.close()
        async with self.root_engine.begin() as connection:
            await connection.execute(sa.text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        await self.root_engine.dispose()

    async def add_user(self, email, role='user'):
        token = uuid.uuid4().hex
        async with self.database.sessions.begin() as session:
            user = models.User(email=email, role=role, password_hash='unused')
            session.add(user)
            await session.flush()
            session.add(models.Session(token_hash=passwords.token_hash(token), user_id=user.id,
                                        expires_at=clock.now() + timedelta(days=1)))
            return user.id, token

    async def post(self, user_id, action, **extra):
        return await self.client.post('/api/admin/users/' + str(user_id),
                                      headers={'X-CSRF-Token': 'csrf'}, json={'action': action, **extra})

    async def test_access_csrf_and_self_protection(self):
        for action in ('block', 'delete', 'demote'):
            response = await self.post(self.admin_id, action, confirmation_email='admin@example.com')
            self.assertEqual(response.status_code, 400)
        response = await self.client.post('/api/admin/users/' + str(self.user_id), json={'action': 'block'})
        self.assertEqual(response.status_code, 403)
        self.client.cookies.set(security.SESSION_COOKIE, self.user_token)
        self.assertEqual((await self.client.get('/api/admin/users')).status_code, 403)
        self.assertEqual((await self.post(self.admin_id, 'block')).status_code, 403)
        self.client.cookies.clear()
        self.assertEqual((await self.client.get('/api/admin/users')).status_code, 401)

    async def test_block_delete_restore_and_role_changes(self):
        self.assertEqual((await self.post(self.user_id, 'block')).status_code, 200)
        async with self.database.sessions() as session:
            self.assertTrue((await session.get(models.User, self.user_id)).blocked)
            self.assertEqual(await session.scalar(sa.select(sa.func.count()).select_from(models.Session).where(
                models.Session.user_id == self.user_id)), 0)
        self.assertEqual((await self.post(self.user_id, 'unblock')).status_code, 200)
        for action, role in (('promote', 'admin'), ('demote', 'user')):
            self.assertEqual((await self.post(self.user_id, action)).status_code, 200)
            async with self.database.sessions() as session:
                self.assertEqual((await session.get(models.User, self.user_id)).role, role)
        self.assertEqual((await self.post(self.user_id, 'delete', confirmation_email='wrong@example.com')).status_code, 400)
        self.assertEqual((await self.post(self.user_id, 'delete', confirmation_email='user@example.com')).status_code, 200)
        self.assertEqual((await self.post(self.user_id, 'unblock')).status_code, 400)
        async with self.database.sessions() as session:
            deleted = await session.get(models.User, self.user_id)
            self.assertIsNotNone(deleted.deleted_at)
            self.assertEqual(deleted.email, 'user@example.com')
        self.assertEqual((await self.post(self.user_id, 'restore')).status_code, 200)
        async with self.database.sessions() as session:
            restored = await session.get(models.User, self.user_id)
            self.assertTrue(restored.blocked)
            self.assertIsNone(restored.deleted_at)

    async def test_concurrent_admin_actions_preserve_an_active_administrator(self):
        other_id, other_token = await self.add_user('other-admin@example.com', role='admin')
        async def block(actor_token, target):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test',
                    cookies={security.SESSION_COOKIE: actor_token, security.CSRF_COOKIE: 'csrf'}) as client:
                return await client.post('/api/admin/users/' + str(target), headers={'X-CSRF-Token': 'csrf'}, json={'action': 'block'})
        responses = await asyncio.gather(block(self.admin_token, other_id), block(other_token, self.admin_id))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 401])
        async with self.database.sessions() as session:
            self.assertEqual(await session.scalar(sa.select(sa.func.count()).select_from(models.User).where(
                models.User.role == 'admin', models.User.blocked.is_(False), models.User.deleted_at.is_(None))), 1)

    async def test_search_filters_pagination_and_localized_detail(self):
        for index in range(21):
            await self.add_user(f'page{index:02}@example.com')
        response = await self.client.get('/api/admin/users?q=page&role=user&state=active&lang=en')
        self.assertEqual(response.status_code, 200)
        self.assertIn('page19@example.com', response.text)
        self.assertNotIn('page20@example.com', response.text)
        response = await self.client.get('/api/admin/users?q=page&page=2&lang=ru')
        self.assertIn('page20@example.com', response.text)
        self.assertEqual(response.headers['content-language'], 'ru')
        response = await self.client.get('/api/admin/users/' + str(self.user_id) + '?lang=ru')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['id'], self.user_id)
        self.assertTrue(all(not group['movies'] for group in response.json()['lists']))
        self.assertEqual((await self.client.get('/api/admin/users?state=unknown')).status_code, 400)
        self.assertEqual((await self.client.get('/api/admin/users/999999')).status_code, 404)

    async def test_lists_are_read_only_and_survive_deletion(self):
        snapshot = {'id': 1, 'title': 'Фильм', 'description': 'Описание', 'genres': ['Драма'],
                    'year': 2000, 'translations': {'en': {'title': 'Movie', 'description': 'Description',
                                                       'genres': ['Drama']}}}
        async with self.database.sessions.begin() as session:
            session.add(models.SavedMovie(id='1', snapshot=snapshot))
            await session.flush()
            session.add(models.Mark(user_id=self.user_id, movie_id='1', watched=True, liked=True))
        response = await self.client.get('/api/admin/users/' + str(self.user_id) + '?lang=en')
        self.assertIn('Movie', response.text)
        self.assertNotIn('name="movie_id"', response.text)
        await self.post(self.user_id, 'delete', confirmation_email='user@example.com')
        await self.post(self.user_id, 'restore')
        async with self.database.sessions() as session:
            mark = await session.get(models.Mark, (self.user_id, '1'))
            self.assertTrue(mark.watched)
            self.assertTrue(mark.liked)
            self.assertEqual((await session.get(models.SavedMovie, '1')).snapshot, snapshot)
        response = await self.client.get('/api/admin/users?page=0&lang=ru')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Некорректный номер страницы.', response.text)

    async def test_concurrent_demotion_rechecks_administrator_role(self):
        other_id, other_token = await self.add_user('demote-admin@example.com', role='admin')
        async def demote(actor_token, target):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test',
                    cookies={security.SESSION_COOKIE: actor_token, security.CSRF_COOKIE: 'csrf'}) as client:
                return await client.post('/api/admin/users/' + str(target), headers={'X-CSRF-Token': 'csrf'}, json={'action': 'demote'})
        responses = await asyncio.gather(demote(self.admin_token, other_id), demote(other_token, self.admin_id))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 403])
        async with self.database.sessions() as session:
            self.assertEqual(await session.scalar(sa.select(sa.func.count()).select_from(models.User).where(
                models.User.role == 'admin', models.User.blocked.is_(False), models.User.deleted_at.is_(None))), 1)
