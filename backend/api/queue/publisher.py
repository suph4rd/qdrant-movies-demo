import asyncio
import json
import logging
import signal

import aiokafka

from backend.api import config
from backend.api.infrastructure import database
from backend.api.infrastructure.repositories import search_tasks


logger = logging.getLogger(__name__)


async def publish_pending(sessions, producer, topic):
    repository = search_tasks.SearchTaskRepository()
    async with sessions() as session:
        pending = await repository.unpublished(session)
    for task_id in pending:
        # No DB transaction is held while waiting for Kafka's acknowledgement.
        await producer.send_and_wait(topic, json.dumps({'version': 1, 'task_id': task_id}).encode(),
                                     key=task_id.encode())
        async with sessions() as session, session.begin():
            await repository.published(session, task_id)
    return len(pending)


async def run(settings):
    db = database.Database(settings.database_url)
    try:
        while True:
            producer = aiokafka.AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers,
                                                acks='all', enable_idempotence=True)
            try:
                await producer.start()
                while True:
                    if not await publish_pending(db.sessions, producer, settings.kafka_search_topic):
                        await asyncio.sleep(1)
            except (aiokafka.errors.KafkaError, OSError):
                logger.exception('Kafka publisher unavailable; outbox retained')
            finally:
                await producer.stop()
            await asyncio.sleep(5)
    finally:
        await db.close()


def main():
    async def entry():
        task = asyncio.create_task(run(config.Settings()))
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, task.cancel)
        try:
            await task
        except asyncio.CancelledError:
            pass
    logging.basicConfig(level=logging.INFO)
    asyncio.run(entry())


if __name__ == '__main__':
    main()
