import asyncio
from datetime import timedelta
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
import uuid

import httpx
import sqlalchemy as sa
from sqlalchemy.ext import asyncio as sa_async

from backend.api import app as web_app
from backend.api.application import task_snapshots
from backend.api.application.services import search_tasks
from backend.api.http.transport import security
from backend.api.infrastructure import clock, models
from backend.api.infrastructure.repositories import search_tasks as repository
from backend.api.presentation import search_tasks as presentation
from backend.api.queue import publisher, worker
from backend.engine import errors


class SnapshotTests(unittest.TestCase):
    def test_structured_nested_errors_are_localized_when_read(self):
        exc = errors.annotate_error(OSError('private diagnostic'), 'wikidata_unavailable')
        raw = {'groups': [], 'messages': [{'key': 'import_failed', 'params': {'title': 'Film', 'error': exc}}]}
        frozen = task_snapshots.freeze(raw)
        self.assertEqual(frozen['messages'][0]['params']['error']['__search_error__']['key'], 'wikidata_unavailable')
        self.assertIn('Wikidata is unavailable', errors.format_message(task_snapshots.thaw(frozen)['messages'][0], 'en'))
        self.assertIn('Wikidata недоступна', errors.format_message(task_snapshots.thaw(frozen)['messages'][0], 'ru'))
        self.assertEqual(task_snapshots.freeze({'vector': [1], '_embedding': {}, 'id': 1}), {'id': 1})


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires a separate PostgreSQL schema')
class SearchQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = 'queue_test_' + uuid.uuid4().hex
        self.control = sa_async.create_async_engine(os.environ['TEST_DATABASE_URL'])
        async with self.control.begin() as connection:
            await connection.execute(sa.text('CREATE SCHEMA ' + self.schema))
        url = sa.engine.make_url(os.environ['TEST_DATABASE_URL']).update_query_dict(
            {'options': '-csearch_path=' + self.schema}).render_as_string(hide_password=False)
        self.app = web_app.create_app({'database_url': url})
        self.lifespan = self.app.router.lifespan_context(self.app)
        await self.lifespan.__aenter__()
        self.db = self.app.state.database
        async with self.db.engine.begin() as connection:
            await connection.run_sync(models.Base.metadata.create_all)
        self.app.state.movie_store.find_movies = AsyncMock(return_value=[])
        self.app.state.movie_store.count_movies = AsyncMock(return_value=250)
        self.app.state.movie_store.recommend = AsyncMock(return_value={'source': {'id': 1}, 'recommendations': []})
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        await self.client.get('/api/context')
        self.service = search_tasks.SearchTaskService(self.db.sessions)
        self.repo = repository.SearchTaskRepository()
        self.params = {'q': 'External film (2005)', 'mode': 'movie', 'limit': '5'}

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.lifespan.__aexit__(None, None, None)
        async with self.control.begin() as connection:
            await connection.execute(sa.text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        await self.control.dispose()

    async def post(self, path, **data):
        return await self.client.post('/api' + path, json=data, headers={
            'X-CSRF-Token': self.client.cookies[security.CSRF_COOKIE], 'Origin': 'http://test'})

    async def finish(self, task_id, result=None, error=None):
        async with self.db.sessions.begin() as session:
            await self.repo.claim(session, task_id, 'test-attempt')
        async with self.db.sessions.begin() as session:
            self.assertTrue(await self.repo.finish(session, task_id, 'test-attempt', result, error))

    async def test_concurrent_submissions_across_service_instances_and_database_constraint(self):
        services = [search_tasks.SearchTaskService(self.db.sessions) for _ in range(12)]
        results = await asyncio.gather(*(service.submit({**self.params, 'q': '  '+self.params['q']+' '}, None, 'guest')
                                        for service in services))
        task_ids = {task.id for task, conflict in results if not conflict}
        self.assertEqual(len(task_ids), 1)
        task_id = next(iter(task_ids))
        different, conflict = await self.service.submit({**self.params, 'limit': '10'}, None, 'guest')
        self.assertTrue(conflict)
        self.assertEqual(different.id, task_id)
        async with self.db.sessions() as session:
            self.assertEqual(await session.scalar(sa.select(sa.func.count()).select_from(models.SearchTask)), 1)
            self.assertEqual(await session.scalar(sa.select(sa.func.count()).select_from(models.SearchOutbox)), 1)
        with self.assertRaises(sa.exc.IntegrityError):
            async with self.db.sessions.begin() as session:
                await self.repo.add(session, different.owner_id, self.params)
        await self.finish(task_id, {'groups': [], 'messages': []})
        new, conflict = await self.service.submit({**self.params, 'q': 'Distinct external request xz9'}, None, 'guest')
        self.assertFalse(conflict)
        self.assertNotEqual(new.id, task_id)
        self.assertIsNone((await self.service.get(task_id, None, 'guest')).read_at)

    async def test_http_local_search_bypasses_slot_csrf_and_ownership(self):
        submitted = await self.post('/search', **self.params)
        self.assertEqual(submitted.status_code, 202, submitted.text)
        task_id = submitted.json()['task_id']
        same = await self.post('/search', **{**self.params, 'q': ' '+self.params['q']+' '})
        self.assertEqual(same.status_code, 202)
        self.assertEqual(same.json()['task_id'], task_id)
        conflict = await self.post('/search?lang=ru', **{**self.params, 'q': 'Distinct external request xz9'})
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['code'], 'external_search_in_progress')
        self.assertIn('Внешний поиск', conflict.json()['error'])
        self.assertEqual((await self.post('/search', q='1')).status_code, 200)
        self.app.state.movie_store.semantic_search = AsyncMock(return_value={'source': None, 'recommendations': []})
        self.assertEqual((await self.post('/search', q='space', mode='description')).status_code, 200)
        self.app.state.wikidata.search = AsyncMock()
        self.assertEqual((await self.client.get('/api/search', params=self.params)).status_code, 400)
        self.app.state.wikidata.search.assert_not_awaited()
        self.assertEqual((await self.client.post('/api/search-tasks/'+task_id+'/read')).status_code, 403)
        self.assertEqual((await self.client.post('/api/search-tasks/'+task_id+'/read', headers={
            'X-CSRF-Token': self.client.cookies[security.CSRF_COOKIE], 'Origin': 'https://foreign'})).status_code, 403)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test') as other:
            self.assertEqual((await other.get('/api/search-tasks/'+task_id)).status_code, 404)
            self.assertEqual((await other.get('/api/search-tasks')).json(), {'tasks': []})
        # Reading an active task does not release the slot or hide it.
        self.assertEqual((await self.post('/search-tasks/'+task_id+'/read')).status_code, 200)
        self.assertEqual(len((await self.client.get('/api/search-tasks')).json()['tasks']), 1)
        await self.finish(task_id, error=task_snapshots.freeze(errors.MovieNotFoundError('wikidata_not_found')))
        for lang in ('en', 'ru'):
            detail = (await self.client.get('/api/search-tasks/'+task_id+'?lang='+lang)).json()['task']
            self.assertEqual(detail['status'], 'failed')
            self.assertEqual(detail['error'], errors.format_error(errors.MovieNotFoundError('wikidata_not_found'), lang))
        self.assertEqual(len((await self.client.get('/api/search-tasks')).json()['tasks']), 1)
        await self.post('/search-tasks/'+task_id+'/read')
        self.assertEqual((await self.client.get('/api/search-tasks')).json()['tasks'], [])
        self.assertEqual((await self.post('/search', **self.params)).status_code, 202)

    async def test_login_guest_task_and_account_isolation(self):
        guest = (await self.post('/search', **self.params)).json()['task_id']
        response = await self.post('/register', email='one@example.com', password='safe-demo-password', password_repeat='safe-demo-password')
        self.assertEqual(response.status_code, 200, response.text)
        user_id = response.json()['user']['id']
        self.assertEqual((await self.post('/search', **{**self.params, 'q': 'Different'})).status_code, 409)
        self.assertEqual((await self.post('/search', **self.params)).json()['task_id'], guest)
        self.assertEqual((await self.client.get('/api/search-tasks/'+guest)).status_code, 200)
        await self.finish(guest, error={'unexpected': True})
        account = (await self.post('/search', **self.params)).json()['task_id']
        self.assertEqual((await self.service.get(account, user_id, None)).owner_id, 'u:'+str(user_id))
        # Another browser of the same account also observes the account slot.
        duplicate, conflict = await self.service.submit(self.params, user_id, 'other-browser')
        self.assertFalse(conflict)
        self.assertEqual(duplicate.id, account)
        async with self.db.sessions.begin() as session:
            other = models.User(email='two@example.com', password_hash='test')
            session.add(other)
            await session.flush()
            other_id = other.id
        independent, conflict = await self.service.submit(self.params, other_id, 'another')
        self.assertFalse(conflict)
        self.assertNotEqual(independent.id, account)
        self.assertIsNone(await self.service.get(account, other_id, 'another'))
        await self.post('/logout')
        self.assertEqual((await self.client.get('/api/search-tasks/'+account)).status_code, 404)

    async def test_lease_fencing_cancellation_and_terminal_redelivery(self):
        task, _ = await self.service.submit(self.params, None, 'guest')
        async with self.db.sessions.begin() as session:
            self.assertIsNotNone(await self.repo.claim(session, task.id, 'old'))
        async with self.db.sessions.begin() as session:
            self.assertIsNone(await self.repo.claim(session, task.id, 'new'))
            await session.execute(sa.update(models.SearchTask).values(lease_until=clock.now()-timedelta(seconds=1)))
        async with self.db.sessions.begin() as session:
            self.assertIsNotNone(await self.repo.claim(session, task.id, 'new'))
        async with self.db.sessions.begin() as session:
            self.assertFalse(await self.repo.renew(session, task.id, 'old'))
            self.assertFalse(await self.repo.finish(session, task.id, 'old', {}, None))
            await self.repo.release(session, task.id, 'old')
            self.assertTrue(await self.repo.renew(session, task.id, 'new'))
            await self.repo.release(session, task.id, 'new')
        started = asyncio.Event()
        async def slow(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        search = SimpleNamespace(search=AsyncMock(side_effect=slow))
        runner = worker.SearchWorker(self.db.sessions, search)
        execution = asyncio.create_task(runner.execute(task.id))
        await asyncio.wait_for(started.wait(), 5)
        execution.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await execution
        record = await self.service.get(task.id, None, 'guest')
        self.assertEqual(record.status, 'running')
        self.assertIsNone(record.lease_until)
        self.assertTrue((await self.service.submit({**self.params, 'q': 'different'}, None, 'guest'))[1])
        search.search = AsyncMock(return_value={'groups': [], 'messages': []})
        self.assertTrue(await runner.execute(task.id))
        self.assertTrue(await runner.execute(task.id))
        search.search.assert_awaited_once()

    async def test_worker_safe_errors_and_publisher_replay(self):
        task, _ = await self.service.submit(self.params, None, 'guest')
        producer = AsyncMock()
        producer.send_and_wait.side_effect = OSError('broker unavailable')
        with self.assertRaises(OSError):
            await publisher.publish_pending(self.db.sessions, producer, 'topic')
        self.assertTrue((await self.service.submit({**self.params, 'q': 'Distinct external request xz9'}, None, 'guest'))[1])
        producer.send_and_wait.side_effect = None
        self.assertEqual(await publisher.publish_pending(self.db.sessions, producer, 'topic'), 1)
        self.assertEqual(await publisher.publish_pending(self.db.sessions, producer, 'topic'), 0)
        search = SimpleNamespace(search=AsyncMock(side_effect=TypeError('secret traceback')))
        with self.assertLogs(worker.logger, level='ERROR') as logs:
            await worker.SearchWorker(self.db.sessions, search).execute(task.id)
        self.assertIn('Traceback', logs.output[0])
        record = await self.service.get(task.id, None, 'guest')
        self.assertEqual(record.error, {'unexpected': True})
        self.assertNotIn('secret', presentation.detail(record, 'en', [])['error'])
        another, _ = await self.service.submit(self.params, None, 'guest')
        search.search.side_effect = errors.MovieNotFoundError('wikidata_not_found')
        await worker.SearchWorker(self.db.sessions, search).execute(another.id)
        record = await self.service.get(another.id, None, 'guest')
        self.assertEqual(record.status, 'failed')
        self.assertIn('Wikidata', presentation.detail(record, 'ru', [])['error'])

    async def test_finished_snapshot_preserves_localization_and_rebuilds_card_references(self):
        from backend.api.tests import test_api

        guest = self.client.cookies[security.GUEST_COOKIE]
        task, _ = await self.service.submit(self.params, None, guest)
        movie = test_api.imported_movie()
        raw = {'groups': [{'source': movie, 'recommendations': []}], 'messages': []}
        await self.finish(task.id, task_snapshots.freeze(raw))
        # Account ownership is not required to read a browser's guest completion.
        response = await self.post('/register', email='cards@example.com', password='safe-demo-password', password_repeat='safe-demo-password')
        self.assertEqual(response.status_code, 200)
        first = (await self.client.get('/api/search-tasks/'+task.id+'?lang=en')).json()['task']['result']['groups'][0]['source']
        self.app.state.movie_cards.clear()
        second = (await self.client.get('/api/search-tasks/'+task.id+'?lang=ru')).json()['task']['result']['groups'][0]['source']
        self.assertEqual(first['id'], str(movie['id']))
        self.assertEqual(first['title'], 'New movie')
        self.assertEqual(second['title'], 'Новый фильм')
        self.assertNotEqual(first['mark_reference'], second['mark_reference'])
        self.assertIn(second['mark_reference'], self.app.state.movie_cards)

    @unittest.skipUnless(os.environ.get('QUEUE_INTEGRATION'), 'Requires Kafka, Qdrant and TEI on loopback')
    async def test_kafka_worker_restart_after_qdrant_write_and_duplicate_delivery(self):
        import json
        from pathlib import Path
        import sys
        import tempfile

        import aiokafka
        from aiokafka.admin import AIOKafkaAdminClient, NewTopic
        from qdrant_client import models as qmodels

        from backend.engine.stores import factory

        suffix = uuid.uuid4().hex
        topic = 'movie-search.test.' + suffix
        collection = 'queue_test_' + suffix
        group = 'queue-workers-test-' + suffix
        admin = AIOKafkaAdminClient(bootstrap_servers='127.0.0.1:19092')
        producer = aiokafka.AIOKafkaProducer(bootstrap_servers='127.0.0.1:19092', acks='all')
        store = factory.create_store('http://127.0.0.1:6333', collection, 'http://127.0.0.1:18080')
        process = None
        async def eventually(check, timeout=45):
            async with asyncio.timeout(timeout):
                while not await check():
                    if process is not None and process.returncode is not None:
                        self.fail('Worker exited: '+(await process.stderr.read()).decode())
                    await asyncio.sleep(.2)
        try:
            await admin.start()
            await admin.create_topics([NewTopic(topic, num_partitions=3, replication_factor=1)])
            await producer.start()
            await store.client.create_collection(collection, vectors_config={
                'semantic': qmodels.VectorParams(size=store.spec.dimensions, distance=qmodels.Distance.COSINE)},
                metadata={'embedding': store.spec.metadata()})
            params = {**self.params, 'q': 'New movie (2005)'}
            task, _ = await self.service.submit(params, None, 'kafka-browser')
            with tempfile.TemporaryDirectory(prefix='queue-test-') as temp:
                marker = Path(temp) / 'imported'
                env = {**os.environ, 'QUEUE_TEST_DATABASE_URL': self.app.state.settings.database_url,
                    'QUEUE_TEST_COLLECTION': collection, 'QUEUE_TEST_TOPIC': topic,
                    'QUEUE_TEST_GROUP': group, 'QUEUE_TEST_MARKER': str(marker), 'QUEUE_TEST_PAUSE': '1'}
                process = await asyncio.create_subprocess_exec(sys.executable, '-m',
                    'backend.api.tests.queue_worker_fixture', env=env, stderr=asyncio.subprocess.PIPE)
                self.assertEqual(await publisher.publish_pending(self.db.sessions, producer, topic), 1)
                async def imported():
                    return marker.exists()
                await eventually(imported)
                self.assertEqual(await store.count_movies(), 1)
                # Simulate abrupt process death after an insert, before durable completion.
                process.kill()
                await process.wait()
                record = await self.service.get(task.id, None, 'kafka-browser')
                self.assertEqual(record.status, 'running')
                self.assertIsNotNone(record.lease_until)
                self.assertTrue((await self.service.submit({**params, 'q': 'another external title'}, None, 'kafka-browser'))[1])
                # Expire the crashed attempt without making this test wait a full minute.
                async with self.db.sessions.begin() as session:
                    await session.execute(sa.update(models.SearchTask).where(models.SearchTask.id == task.id)
                        .values(lease_until=clock.now()-timedelta(seconds=1)))
                env['QUEUE_TEST_PAUSE'] = '0'
                process = await asyncio.create_subprocess_exec(sys.executable, '-m',
                    'backend.api.tests.queue_worker_fixture', env=env, stderr=asyncio.subprocess.PIPE)
                async def completed():
                    return (await self.service.get(task.id, None, 'kafka-browser')).status == 'succeeded'
                await eventually(completed)
                self.assertEqual(await store.count_movies(), 1)
                record = await self.service.get(task.id, None, 'kafka-browser')
                self.assertEqual(record.result['groups'][0]['source']['wikidata_id'], 'Q901')
                # Duplicate deliveries are acknowledged without re-running or changing the result.
                for _ in range(3):
                    await producer.send_and_wait(topic, json.dumps({'version': 1, 'task_id': task.id}).encode(), key=task.id.encode())
                observer = aiokafka.AIOKafkaConsumer(bootstrap_servers='127.0.0.1:19092', group_id=group)
                await observer.start()
                try:
                    metadata = await producer.partitions_for(topic)
                    ends = await observer.end_offsets([aiokafka.TopicPartition(topic, partition) for partition in metadata])
                    async def committed():
                        return all([(await observer.committed(tp) or 0) >= offset for tp, offset in ends.items()])
                    await eventually(committed)
                finally:
                    await observer.stop()
                self.assertEqual(await store.count_movies(), 1)
                process.terminate()
                self.assertEqual(await asyncio.wait_for(process.wait(), 10), 0)
                process = None
                # Graceful shutdown releases the attempt lease but retains the user slot.
                second, _ = await self.service.submit({**params, 'q': 'Fresh external title (2005)'}, None, 'kafka-browser')
                marker.unlink()
                env['QUEUE_TEST_PAUSE'] = '1'
                process = await asyncio.create_subprocess_exec(sys.executable, '-m',
                    'backend.api.tests.queue_worker_fixture', env=env, stderr=asyncio.subprocess.PIPE)
                await publisher.publish_pending(self.db.sessions, producer, topic)
                await eventually(imported)
                process.terminate()
                self.assertEqual(await asyncio.wait_for(process.wait(), 10), 0)
                process = None
                stopped = await self.service.get(second.id, None, 'kafka-browser')
                self.assertEqual(stopped.status, 'running')
                self.assertIsNone(stopped.lease_until)
                self.assertTrue((await self.service.submit(params, None, 'kafka-browser'))[1])
                env['QUEUE_TEST_PAUSE'] = '0'
                process = await asyncio.create_subprocess_exec(sys.executable, '-m',
                    'backend.api.tests.queue_worker_fixture', env=env, stderr=asyncio.subprocess.PIPE)
                async def second_completed():
                    return (await self.service.get(second.id, None, 'kafka-browser')).status == 'succeeded'
                await eventually(second_completed)
                self.assertEqual(await store.count_movies(), 1)
                process.terminate()
                self.assertEqual(await asyncio.wait_for(process.wait(), 10), 0)
                process = None
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()
            await producer.stop()
            await store.client.delete_collection(collection)
            await store.close()
            await admin.delete_topics([topic])
            await admin.close()

    @unittest.skipUnless(os.environ.get('QUEUE_INTEGRATION'), 'Requires local infrastructure and WebSocket transport')
    async def test_uvicorn_websocket_transport_and_reconnect(self):
        import json
        import socket
        import sys

        from websockets.asyncio import client as websocket_client
        from websockets import exceptions as websocket_errors

        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        base_url = 'http://127.0.0.1:' + str(port)
        ws_url = 'ws://127.0.0.1:' + str(port) + '/api/notifications/ws'
        env = {**os.environ, 'DATABASE_URL': self.app.state.settings.database_url}
        process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'uvicorn',
            'backend.api.app:create_app', '--factory', '--fd', str(listener.fileno()),
            env=env, pass_fds=(listener.fileno(),), stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE)
        listener.close()
        try:
            async with httpx.AsyncClient(base_url=base_url) as client:
                async with asyncio.timeout(15):
                    while True:
                        try:
                            response = await client.get('/api/context')
                            if response.status_code == 200:
                                break
                        except httpx.TransportError:
                            pass
                        if process.returncode is not None:
                            self.fail((await process.stderr.read()).decode())
                        await asyncio.sleep(.1)
                headers = {'Cookie': '; '.join(key+'='+value for key, value in client.cookies.items())}
                with self.assertRaises(websocket_errors.InvalidStatus) as caught:
                    async with websocket_client.connect(ws_url, origin='http://foreign.example', additional_headers=headers):
                        pass
                self.assertEqual(caught.exception.response.status_code, 403)
                async with websocket_client.connect(ws_url, origin=base_url, additional_headers=headers) as websocket:
                    self.assertEqual(json.loads(await asyncio.wait_for(websocket.recv(), 5)), {'event': 'heartbeat'})
                    task, _ = await self.service.submit(self.params, None, client.cookies[security.GUEST_COOKIE])
                    await self.finish(task.id, {'groups': [], 'messages': []})
                    message = json.loads(await asyncio.wait_for(websocket.recv(), 5))
                    self.assertEqual(message, {'event': 'search.completed', 'task_id': task.id, 'status': 'succeeded'})
                async with websocket_client.connect(ws_url, origin=base_url, additional_headers=headers) as websocket:
                    self.assertEqual(json.loads(await asyncio.wait_for(websocket.recv(), 5))['task_id'], task.id)
                response = await client.post('/api/search-tasks/'+task.id+'/read', json={}, headers={
                    'X-CSRF-Token': client.cookies[security.CSRF_COOKIE], 'Origin': base_url})
                self.assertEqual(response.status_code, 200)
                self.assertEqual((await client.get('/api/search-tasks')).json()['tasks'], [])
        finally:
            process.terminate()
            await asyncio.wait_for(process.wait(), 10)
