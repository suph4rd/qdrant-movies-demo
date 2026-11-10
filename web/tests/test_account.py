from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote
import asyncio
import copy
import itertools
import os
import unittest
import uuid

from sqlalchemy.ext import asyncio as sa_async
import httpx
import sqlalchemy as sa

from engine import errors
from web import app as web_app
from web.application.services import account as account_service
from web.http import security
from web.infrastructure import clock
from web.infrastructure import database
from web.infrastructure import models
from web.infrastructure import passwords
from web.infrastructure import snapshots
from web.tests import test_imports


class MarkStateTests(unittest.TestCase):
    def test_all_states_and_idempotence(self):
        for watched, liked, watchlist in itertools.product((False, True), repeat=3):
            if watched and watchlist:
                continue
            for flag, state in itertools.product(account_service.FLAGS, (False, True)):
                mark = SimpleNamespace(watched=watched, liked=liked, watchlist=watchlist)
                account_service.apply_mark(mark, flag, state)
                expected = vars(mark).copy()
                account_service.apply_mark(mark, flag, state)
                self.assertEqual(vars(mark), expected)
                self.assertFalse(mark.watched and mark.watchlist)
                self.assertEqual(getattr(mark, flag), state)
                if flag != 'liked':
                    self.assertEqual(mark.liked, liked)
                if not state:
                    for other in account_service.FLAGS:
                        if other != flag:
                            self.assertEqual(getattr(mark, other),
                                             {'watched': watched, 'liked': liked, 'watchlist': watchlist}[other])

    def test_server_references_validate_and_copy(self):
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(catalog=[], movie_cards=snapshots.MovieCards())))
        movie = test_imports.imported_movie()
        original = copy.deepcopy(movie)
        reference = request.app.state.movie_cards.reference(request.app.state.catalog, movie)
        movie['title'] = 'Changed'
        self.assertEqual(request.app.state.movie_cards[reference], original)
        with self.assertRaises(errors.InputValidationError):
            request.app.state.movie_cards.reference(request.app.state.catalog, {'id': 999, 'title': 'Forged'})
        for _ in range(1030):
            request.app.state.movie_cards.reference(request.app.state.catalog, original)
        self.assertEqual(len(request.app.state.movie_cards), 1024)
        self.assertNotIn(reference, request.app.state.movie_cards)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'TEST_DATABASE_URL is required')
class AccountDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = 'account_test_' + uuid.uuid4().hex
        self.url = os.environ['TEST_DATABASE_URL']
        self.control = sa_async.create_async_engine(self.url)
        async with self.control.begin() as connection:
            await connection.execute(sa.text('CREATE SCHEMA ' + self.schema))
        separator = '&' if '?' in self.url else '?'
        self.database = database.Database(self.url + separator + 'options=' + quote('-csearch_path=' + self.schema))
        async with self.database.engine.begin() as connection:
            await connection.run_sync(models.Base.metadata.create_all)
        self.app = web_app.create_app({'database_url': self.url})
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.owned_database = self.app.state.database
        self.app.state.database = self.database
        async with self.database.sessions.begin() as session:
            user = models.User(email='one@example.com', password_hash='unused')
            second = models.User(email='two@example.com', password_hash='unused')
            session.add_all([user, second])
            await session.flush()
            self.user_id, self.second_id = user.id, second.id
            from datetime import timedelta
            session.add_all([models.Session(token_hash=passwords.token_hash(token), user_id=owner,
                                             expires_at=clock.now() + timedelta(days=1))
                             for token, owner in [('one', user.id), ('two', second.id)]])
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),
                                       base_url='http://test', cookies={
                                           security.SESSION_COOKIE: 'one', security.CSRF_COOKIE: 'csrf'})

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.database.close()
        self.app.state.database = self.owned_database
        await self.lifespan.__aexit__(None, None, None)
        async with self.control.begin() as connection:
            await connection.execute(sa.text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        await self.control.dispose()

    async def post_mark(self, movie_id=1, flag='watched', state='true', **extra):
        return await self.client.post('/account/marks', data={
            'movie_id': str(movie_id), 'flag': flag, 'state': state,
            'csrf_token': 'csrf', 'lang': 'en', **extra})

    async def test_marks_repeat_exclusion_and_isolation(self):
        for flag in ('watchlist', 'watched', 'liked', 'liked'):
            self.assertEqual((await self.post_mark(flag=flag)).status_code, 303)
        async with self.database.sessions() as session:
            mark = await session.get(models.Mark, (self.user_id, '1'))
            self.assertEqual((mark.watched, mark.liked, mark.watchlist), (True, True, False))
        self.client.cookies.set(security.SESSION_COOKIE, 'two')
        response = await self.client.get('/account')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('<article>', response.text)
        await self.post_mark(flag='watchlist')
        async with self.database.sessions() as session:
            first = await session.get(models.Mark, (self.user_id, '1'))
            second = await session.get(models.Mark, (self.second_id, '1'))
            self.assertTrue(first.watched)
            self.assertTrue(second.watchlist)
            self.assertFalse(second.watched)

    async def test_import_snapshot_survives_cache_and_store_loss(self):
        movie = test_imports.imported_movie()
        request = SimpleNamespace(app=self.app)
        reference = request.app.state.movie_cards.reference(request.app.state.catalog, movie)
        self.assertEqual((await self.post_mark(movie['id'], 'liked', reference=reference)).status_code, 303)
        self.app.state.movie_cards.clear()
        self.app.state.movie_store.recommend = AsyncMock(side_effect=OSError('offline'))
        self.app.state.movie_store.request = AsyncMock(side_effect=OSError('offline'))
        url = str(self.database.engine.url.render_as_string(hide_password=False))
        await self.database.close()
        self.database = database.Database(url)
        self.app.state.database = self.database
        response = await self.client.get('/account?lang=en')
        self.assertIn('New movie', response.text)
        response = await self.client.get('/account?lang=ru')
        self.assertIn('Новый фильм', response.text)
        self.assertEqual((await self.post_mark(movie['id'], 'watchlist')).status_code, 303)
        self.assertEqual((await self.post_mark(movie['id'] + 1, 'liked', reference=reference)).status_code, 400)

    async def test_concurrent_first_marks_keep_one_row(self):
        responses = await asyncio.gather(*[self.post_mark(flag=flag)
            for flag in ('watchlist', 'watched', 'liked', 'watched', 'liked')])
        self.assertTrue(all(response.status_code == 303 for response in responses))
        async with self.database.sessions() as session:
            marks = (await session.scalars(sa.select(models.Mark))).all()
            saved = (await session.scalars(sa.select(models.SavedMovie))).all()
            self.assertEqual(len(marks), 1)
            self.assertEqual(len(saved), 1)
            self.assertTrue(marks[0].liked)
            self.assertFalse(marks[0].watched and marks[0].watchlist)

    async def test_pagination_and_localizations(self):
        for movie_id in range(1, 22):
            self.assertEqual((await self.post_mark(movie_id)).status_code, 303)
        first = await self.client.get('/account?lang=en')
        self.assertEqual(first.text.count('<article>'), 20)
        self.assertIn('Watched (21)', first.text)
        second = await self.client.get('/account?list=watched&page=2&lang=ru')
        self.assertEqual(second.text.count('<article>'), 1)
        self.assertIn('Просмотрено (21)', second.text)
        self.assertIn('Страница 2', second.text)
        self.assertIn('В этом списке пока нет фильмов.', second.text)
        self.assertEqual((await self.client.get('/account?page=-1')).status_code, 400)

    async def test_rejects_guest_csrf_and_forged_metadata(self):
        self.assertEqual((await self.post_mark(csrf_token='wrong')).status_code, 403)
        self.assertEqual((await self.post_mark(999999, title='Forged', description='Forged')).status_code, 400)
        self.assertEqual((await self.post_mark(flag='admin')).status_code, 400)
        self.assertEqual((await self.post_mark(state='toggle')).status_code, 400)
        self.client.cookies.clear()
        self.assertEqual((await self.client.get('/account')).status_code, 401)
        self.assertEqual((await self.post_mark()).status_code, 401)
