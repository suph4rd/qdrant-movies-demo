from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api.http import dependencies
from backend.api.http.routes import search_tasks
from backend.api.http.transport import security


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(search_tasks.router)
        self.auth = AsyncMock()
        self.auth.current_user.return_value = SimpleNamespace(id=7)
        self.service = AsyncMock()
        self.service.list.return_value = [SimpleNamespace(id='a'*32, status='succeeded')]
        self.enterContext(patch.object(dependencies, 'get_auth_service', return_value=self.auth))
        self.enterContext(patch.object(dependencies, 'get_search_task_service', return_value=self.service))
        self.client = self.enterContext(TestClient(self.app))
        self.client.cookies.set(security.GUEST_COOKIE, 'browser-token')

    def test_foreign_and_missing_origin_rejected_before_accept(self):
        for headers in ({}, {'Origin': 'https://foreign.example'}):
            with self.assertRaises(WebSocketDisconnect) as caught:
                with self.client.websocket_connect('/api/notifications/ws', headers=headers):
                    pass
            self.assertEqual(caught.exception.code, 1008)
        self.service.list.assert_not_awaited()

    def test_completion_identity_and_deduplication(self):
        with self.client.websocket_connect('/api/notifications/ws', headers={'Origin': 'http://testserver'}) as socket:
            self.assertEqual(socket.receive_json(), {'event': 'search.completed', 'task_id': 'a'*32, 'status': 'succeeded'})
            self.assertEqual(socket.receive_json(), {'event': 'heartbeat'})
            self.service.list.assert_awaited_with(7, 'browser-token')
            # A second completion wakes the next poll; the first must not be sent twice.
            self.service.list.return_value = [SimpleNamespace(id='a'*32, status='succeeded'),
                                              SimpleNamespace(id='b'*32, status='failed')]
            self.assertEqual(socket.receive_json(), {'event': 'search.completed', 'task_id': 'b'*32, 'status': 'failed'})
        with self.client.websocket_connect('/api/notifications/ws', headers={'Origin': 'http://testserver'}) as socket:
            self.assertEqual(socket.receive_json()['task_id'], 'a'*32)


class ConsumerRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_delivery_never_commits_or_advances_to_next_message(self):
        import asyncio
        import json

        from backend.api.queue import worker

        class Consumer:
            def __init__(self):
                self.stop = AsyncMock()
                self.commit = AsyncMock()
                self.deliveries = 0

            def subscribe(self, topics, listener):
                self.listener = listener

            async def start(self):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                self.deliveries += 1
                return SimpleNamespace(topic='test', partition=0, offset=self.deliveries,
                    value=json.dumps({'version': 1, 'task_id': 'a'*32}).encode())

        for outcome in (False, asyncio.CancelledError()):
            consumer = Consumer()
            execution = AsyncMock(return_value=False)
            if isinstance(outcome, Exception) or isinstance(outcome, asyncio.CancelledError):
                execution.side_effect = outcome
            settings = SimpleNamespace(kafka_bootstrap_servers='test', kafka_search_group='test', kafka_search_topic='test')
            with patch.object(worker.aiokafka, 'AIOKafkaConsumer', return_value=consumer), patch.object(
                    worker, 'SearchWorker', return_value=SimpleNamespace(execute=execution)):
                with self.assertRaises(worker.DeliveryInterrupted):
                    await worker.consume(None, None, settings)
            consumer.commit.assert_not_awaited()
            consumer.stop.assert_awaited_once()
            self.assertEqual(consumer.deliveries, 1)


class NotificationCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_sender_failure_cancels_and_awaits_receiver(self):
        import asyncio
        from starlette.datastructures import URL

        from backend.api.http.adapters import notifications
        from backend.api.http.adapters import search_task_helpers

        started = asyncio.Event()
        stopped = asyncio.Event()
        receiver_tasks = []

        async def receive():
            receiver_tasks.append(asyncio.current_task())
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        async def send(data):
            await started.wait()
            raise WebSocketDisconnect()

        websocket = SimpleNamespace(url=URL('ws://testserver/api/notifications/ws'),
            headers={'origin': 'http://testserver'}, accept=AsyncMock(),
            receive_text=receive, send_json=send)
        service = AsyncMock()
        service.list.return_value = []
        with patch.object(search_task_helpers, 'identity', AsyncMock(return_value=(None, 'guest'))), patch.object(
                dependencies, 'get_search_task_service', return_value=service):
            await notifications.SearchNotifications(websocket).run()
        self.assertTrue(stopped.is_set())
        self.assertEqual(len(receiver_tasks), 1)
        self.assertTrue(receiver_tasks[0].done())
        self.assertTrue(receiver_tasks[0].cancelled())
