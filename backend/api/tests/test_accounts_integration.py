from unittest.mock import AsyncMock
import os
import unittest
import uuid

from sqlalchemy.ext import asyncio as sa_async
import httpx
import sqlalchemy as sa

from backend.api import app as web_app
from backend.api import create_admin
from backend.api.http.transport import security
from backend.api.infrastructure import models
from backend.api.infrastructure import passwords


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires a separate PostgreSQL database')
class AccountFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = 'flow_test_' + uuid.uuid4().hex
        self.control = sa_async.create_async_engine(os.environ['TEST_DATABASE_URL'])
        async with self.control.begin() as connection:
            await connection.execute(sa.text('CREATE SCHEMA ' + self.schema))
        url = sa.engine.make_url(os.environ['TEST_DATABASE_URL']).update_query_dict(
            {'options': '-csearch_path=' + self.schema})
        self.app = web_app.create_app({'database_url': url.render_as_string(hide_password=False)})
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.app.state.movie_store.count_movies = AsyncMock(return_value=250)
        async with self.app.state.database.engine.begin() as connection:
            await connection.run_sync(models.Base.metadata.create_all)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.admin = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.admin.aclose()
        await self.lifespan.__aexit__(None, None, None)
        async with self.control.begin() as connection:
            await connection.execute(sa.text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        await self.control.dispose()

    async def post(self, client, path, **data):
        return await client.post('/api' + path, json=data,
            headers={'X-CSRF-Token': client.cookies[security.CSRF_COOKIE]})

    async def test_registration_search_lists_and_administrative_recovery(self):
        for lang in ('en', 'ru'):
            response = await self.client.get('/api/context?lang=' + lang)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['content-language'], lang)
        self.assertEqual((await self.post(self.client, '/register?lang=ru', email='Person@Example.com',
            password='safe-demo-password', password_repeat='safe-demo-password')).status_code, 200)
        self.app.state.movie_store.recommend = AsyncMock(return_value={
            'source': {'id': 1}, 'recommendations': [{'id': 2, 'payload': {}, 'score': .9}]})
        response = await self.post(self.client, '/search', q='1')
        self.assertEqual(response.status_code, 200)
        response = await self.client.get('/api/search', params={'q': '1', 'result': response.json()['token']})
        self.assertEqual(response.json()['result']['groups'][0]['recommendations'][0]['id'], '2')
        response = await self.post(self.client, '/account/marks', movie_id='2', flag='liked', state=True)
        self.assertEqual(response.status_code, 200)
        self.app.state.movie_store.recommend.side_effect = OSError('Qdrant is unavailable')
        response = await self.client.get('/api/account?lang=en')
        self.assertEqual(response.json()['lists'][1]['total'], 1)
        async with self.app.state.database.sessions.begin() as session:
            user_id = await session.scalar(sa.select(models.User.id).where(
                models.User.email == 'person@example.com'))
            session.add(models.User(email='admin@example.com', role='admin',
                                    password_hash=await passwords.hash_password('safe-admin-password')))
        await self.admin.get('/api/context')
        self.assertEqual((await self.post(self.admin, '/login', email='admin@example.com',
            password='safe-admin-password')).status_code, 200)
        self.assertEqual((await self.client.get('/api/admin/users')).status_code, 403)
        path = '/admin/users/' + str(user_id)
        self.assertEqual((await self.post(self.admin, path, action='block')).status_code, 200)
        self.assertEqual((await self.client.get('/api/account')).status_code, 401)
        self.assertEqual((await self.post(self.admin, path, action='unblock')).status_code, 200)
        self.assertEqual((await self.post(self.client, '/login', email='person@example.com',
            password='safe-demo-password')).status_code, 200)
        self.assertEqual((await self.post(self.admin, path, action='delete',
            confirmation_email='person@example.com')).status_code, 200)
        self.assertEqual((await self.client.get('/api/account')).status_code, 401)
        self.assertEqual((await self.post(self.client, '/register', email='person@example.com',
            password='safe-demo-password', password_repeat='safe-demo-password')).status_code, 409)
        self.assertEqual((await self.post(self.admin, path, action='restore')).status_code, 200)
        self.assertEqual((await self.post(self.client, '/login', email='person@example.com',
            password='safe-demo-password')).status_code, 400)
        self.assertEqual((await self.post(self.admin, path, action='unblock')).status_code, 200)
        self.assertEqual((await self.post(self.client, '/login', email='person@example.com',
            password='safe-demo-password')).status_code, 200)
        self.assertEqual((await self.client.get('/api/account?lang=en')).json()['lists'][1]['total'], 1)
        self.assertEqual((await self.post(self.client, '/logout')).status_code, 200)
        self.assertEqual((await self.client.get('/api/account')).status_code, 401)

    async def test_concurrent_first_administrator_bootstrap(self):
        import asyncio

        url = self.app.state.settings.database_url
        results = await asyncio.gather(
            create_admin.create_admin(url, ' FIRST@example.com ', 'first-admin-password'),
            create_admin.create_admin(url, 'second@example.com', 'second-admin-password'),
            return_exceptions=True)
        self.assertEqual(sum(result is None for result in results), 1)
        failures = [result for result in results if result is not None]
        self.assertIsInstance(failures[0], ValueError)
        async with self.app.state.database.sessions() as session:
            administrators = (await session.scalars(sa.select(models.User).where(
                models.User.role == 'admin'))).all()
            self.assertEqual(len(administrators), 1)
            administrator = administrators[0]
            password = 'first-admin-password' if administrator.email == 'first@example.com' else 'second-admin-password'
            self.assertTrue(await passwords.verify_password(administrator.password_hash, password))
