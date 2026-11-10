import asyncio

from fastapi import WebSocketDisconnect

from backend.api.http import dependencies
from backend.api.http.adapters import search_task_helpers


class SearchNotifications:
    def __init__(self, websocket):
        self.websocket = websocket

    async def run(self):
        expected = str(self.websocket.url.replace(scheme='https' if self.websocket.url.scheme == 'wss' else 'http',
                                             path='/', query='')).rstrip('/')
        if self.websocket.headers.get('origin', '').rstrip('/') != expected:
            await self.websocket.close(code=1008)
            return
        await self.websocket.accept()
        sent = set()

        async def receive():
            while True:
                # Receive disconnects promptly even when no task completes.
                await self.websocket.receive_text()

        receiver = asyncio.create_task(receive())
        try:
            ticks = 0
            while not receiver.done():
                user, guest = await search_task_helpers.identity(self.websocket)
                tasks = await dependencies.get_search_task_service(self.websocket).list(user.id if user else None, guest)
                for task in tasks:
                    if task.status in ('succeeded', 'failed') and task.id not in sent:
                        await self.websocket.send_json({'event': 'search.completed',
                                                   'task_id': task.id, 'status': task.status})
                        sent.add(task.id)
                if ticks % 15 == 0:
                    await self.websocket.send_json({'event': 'heartbeat'})
                ticks += 1
                await asyncio.wait({receiver}, timeout=1)
            await receiver
        except WebSocketDisconnect:
            pass
        finally:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
