from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import asyncio
import os
import unittest
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import pool
from sqlalchemy.ext import asyncio as sa_async
import httpx
import sqlalchemy as sa

from web.application import credential_validation
from web.http import security
from web.http.routes import auth
from web.infrastructure import clock
from web.infrastructure import database
from web.infrastructure import models
from web.infrastructure import passwords
from web.presentation import pages


class CredentialTests(unittest.IsolatedAsyncioTestCase):
    def test_email_and_password_validation(self):
        self.assertEqual(credential_validation.normalize_email('  PERSON@Example.com '), 'person@example.com')
        self.assertEqual(credential_validation.normalize_email('ＰＥＲＳＯＮ@example.com'), 'person@example.com')
        for email in ('a\x00@example.com', '', 'no-at.example.com', 'a@b', 'a b@example.com', 'a' * 255 + '@b.com'):
            with self.subTest(email=email), self.assertRaises(ValueError):
                credential_validation.normalize_email(email)
        for password in ('a' * 11, 'a' * 129):
            with self.assertRaises(ValueError):
                credential_validation.validate_password(password, password)
        for size in (12, 128):
            credential_validation.validate_password('a' * size, 'a' * size)
        with self.assertRaisesRegex(ValueError, 'do not match'):
            credential_validation.validate_password('a' * 12, 'b' * 12)

    async def test_argon2id_hash_and_wrong_password(self):
        encoded = await passwords.hash_password('correct-password')
        self.assertTrue(encoded.startswith('$argon2id$'))
        self.assertTrue(await passwords.verify_password(encoded, 'correct-password'))
        self.assertFalse(await passwords.verify_password(encoded, 'incorrect-password'))
        self.assertFalse(await passwords.verify_password(passwords.DUMMY_HASH, 'incorrect-password'))

    async def test_csrf_rejects_missing_mismatch_and_foreign_origin(self):
        for cookie, supplied, origin in (('', '', None), ('abc', 'xyz', None),
                                           ('abc', 'abc', 'https://foreign.example')):
            request = SimpleNamespace(form=AsyncMock(return_value={'csrf_token': supplied}),
                                      cookies={security.CSRF_COOKIE: cookie},
                                      headers={'origin': origin} if origin else {},
                                      base_url='http://test/', query_params={})
            with self.assertRaises(HTTPException) as caught:
                await security.check_csrf(request)
            self.assertEqual(caught.exception.status_code, 403)

    def test_session_cookie_security(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            settings=SimpleNamespace(cookie_secure=True))))
        response = auth.issue_cookie(request, auth.RedirectResponse('/account', 303), 'secret')
        cookie = response.headers.getlist('set-cookie')[0]
        for part in ('HttpOnly', 'Secure', 'SameSite=lax', 'Max-Age=604800'):
            self.assertIn(part, cookie)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires an isolated TEST_DATABASE_URL PostgreSQL database')
class AuthenticationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.environ['TEST_DATABASE_URL']

    def setUp(self):
        self.email = 'auth-' + uuid.uuid4().hex + '@example.com'
        self.password = 'safe-demo-password'
        self.database = database.Database(self.url)
        self.database.engine = sa_async.create_async_engine(self.url, poolclass=pool.NullPool)
        self.database.sessions = sa_async.async_sessionmaker(self.database.engine, expire_on_commit=False)
        self.app = FastAPI()
        self.app.state.database = self.database
        self.app.state.settings = SimpleNamespace(cookie_secure=False)
        self.app.include_router(auth.router)
        # Keep these tests independent of engine services and the integrated navigation.
        self.render_patch = patch.object(pages, 'render', side_effect=self.render)
        self.render_patch.start()
        self.client = TestClient(self.app)
        self.client.cookies.set(security.CSRF_COOKIE, 'csrf', domain='testserver.local', path='/')

    async def render(self, request, template, values=None, status_code=200):
        from fastapi.responses import JSONResponse
        lang = request.query_params.get('lang', 'en')
        values = values or {}
        error = values.get('error')
        if error and lang == 'ru':
            error = pages.translate(error, lang)
        return JSONResponse({'error': error, 'email': values.get('email')}, status_code=status_code)

    def tearDown(self):
        self.render_patch.stop()
        self.client.close()

        async def cleanup():
            async with self.database.sessions() as session, session.begin():
                user = await session.scalar(sa.select(models.User).where(models.User.email == self.email))
                if user:
                    await session.execute(sa.delete(models.Session).where(models.Session.user_id == user.id))
                    await session.delete(user)
            await self.database.close()

        asyncio.run(cleanup())

    def post(self, path, **fields):
        return self.client.post(path, data={'csrf_token': self.client.cookies.get(security.CSRF_COOKIE),
                                           **fields}, follow_redirects=False)

    def register(self):
        return self.post('/register', email=self.email, password=self.password,
                         password_repeat=self.password)

    def test_registration_duplicate_wrong_password_login_and_logout(self):
        self.assertEqual(self.register().status_code, 303)
        token = self.client.cookies.get(security.SESSION_COOKIE)
        self.assertIsNotNone(token)
        self.assertEqual(self.register().status_code, 409)
        self.assertEqual(self.post('/logout').status_code, 303)
        self.assertIsNone(self.client.cookies.get(security.SESSION_COOKIE))
        self.assertEqual(self.post('/login', email=self.email, password='wrong').status_code, 400)
        self.assertEqual(self.post('/login', email=self.email.upper(), password=self.password).status_code, 303)
        self.assertNotEqual(token, self.client.cookies.get(security.SESSION_COOKIE))

    def test_csrf_and_localized_errors(self):
        response = self.client.post('/register', data={'email': self.email})
        self.assertEqual(response.status_code, 403)
        response = self.post('/register?lang=ru', email=self.email, password='short', password_repeat='short')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Пароль', response.json()['error'])

    def test_expiration_revocation_block_and_delete(self):
        self.assertEqual(self.register().status_code, 303)
        token = self.client.cookies.get(security.SESSION_COOKIE)

        async def user_for_cookie():
            request = SimpleNamespace(cookies={security.SESSION_COOKIE: token}, app=self.app)
            return await security.current_user(request)

        self.assertIsNotNone(asyncio.run(user_for_cookie()))

        async def alter(kind):
            async with self.database.sessions() as session, session.begin():
                user = await session.scalar(sa.select(models.User).where(models.User.email == self.email))
                if kind == 'expired':
                    await session.execute(sa.update(models.Session).where(
                        models.Session.user_id == user.id).values(expires_at=clock.now() - timedelta(seconds=1)))
                elif kind == 'blocked':
                    user.blocked = True
                else:
                    user.deleted_at = clock.now()

        asyncio.run(alter('expired'))
        self.assertIsNone(asyncio.run(user_for_cookie()))
        self.assertEqual(self.post('/login', email=self.email, password=self.password).status_code, 303)
        token = self.client.cookies.get(security.SESSION_COOKIE)
        asyncio.run(alter('blocked'))
        self.assertIsNone(asyncio.run(user_for_cookie()))
        self.assertEqual(self.post('/login', email=self.email, password=self.password).status_code, 400)
        asyncio.run(alter('deleted'))
        self.assertEqual(self.register().status_code, 409)
        self.assertEqual(self.post('/login', email=self.email, password=self.password).status_code, 400)

    def test_logout_revokes_stored_token(self):
        self.register()
        token = self.client.cookies.get(security.SESSION_COOKIE)
        self.post('/logout')
        self.client.cookies.set(security.SESSION_COOKIE, token, domain='testserver.local', path='/')

        async def query():
            async with self.database.sessions() as session:
                return await session.get(models.Session, passwords.token_hash(token))

        self.assertIsNone(asyncio.run(query()))

    def test_concurrent_registration_has_one_winner(self):
        async def submit():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                         base_url='http://testserver',
                                         cookies={security.CSRF_COOKIE: 'csrf'}) as client:
                return await client.post('/register', data={
                    'csrf_token': 'csrf', 'email': self.email,
                    'password': self.password, 'password_repeat': self.password})

        async def compete():
            return await asyncio.gather(submit(), submit())

        responses = asyncio.run(compete())
        self.assertEqual(sorted(response.status_code for response in responses), [303, 409])
