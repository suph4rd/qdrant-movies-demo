import asyncio
import json
import logging
import signal
import uuid

import aiokafka

from backend.api import config
from backend.api.application import task_snapshots
from backend.api.infrastructure import database, models
from backend.api.infrastructure.repositories import search_tasks
from backend.engine import catalog, errors, services, wikidata
from backend.engine.stores import factory


logger = logging.getLogger(__name__)


class SearchWorker:
    def __init__(self, sessions, search):
        self.sessions = sessions
        self.search = search
        self.repository = search_tasks.SearchTaskRepository()

    async def execute(self, task_id):
        token = uuid.uuid4().hex
        while True:
            async with self.sessions() as session, session.begin():
                task = await self.repository.claim(session, task_id, token)
                if task is None:
                    existing = await session.get(models.SearchTask, task_id)
                    if existing is None or existing.status in search_tasks.TERMINAL:
                        return True
            if task is not None:
                break
            # A duplicate delivery must not acknowledge an unfinished leased task.
            await asyncio.sleep(1)
        work = asyncio.create_task(self.search.search(task.query, limit=int(task.limit), allow_import=True))
        heartbeat = asyncio.create_task(self.heartbeat(task_id, token))
        try:
            done, _ = await asyncio.wait({work, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done:
                await heartbeat
                return False
            result, error = None, None
            try:
                result = task_snapshots.freeze(await work)
            except Exception as exc:
                if errors.is_expected_error(exc):
                    error = task_snapshots.freeze(exc)
                else:
                    logger.exception('Unexpected external search failure for task %s', task_id)
                    error = {'unexpected': True}
            async with self.sessions() as session, session.begin():
                return await self.repository.finish(session, task_id, token, result, error)
        finally:
            work.cancel()
            heartbeat.cancel()
            await asyncio.gather(work, heartbeat, return_exceptions=True)
            async with self.sessions() as session, session.begin():
                await self.repository.release(session, task_id, token)

    async def heartbeat(self, task_id, token):
        while True:
            await asyncio.sleep(15)
            async with self.sessions() as session, session.begin():
                if not await self.repository.renew(session, task_id, token):
                    return


class DeliveryInterrupted(RuntimeError):
    pass


class RebalanceListener(aiokafka.ConsumerRebalanceListener):
    def __init__(self):
        self.work = None

    async def on_partitions_revoked(self, revoked):
        if self.work is not None:
            self.work.cancel()
            await asyncio.gather(self.work, return_exceptions=True)

    async def on_partitions_assigned(self, assigned):
        pass


async def consume(sessions, search, settings):
    worker = SearchWorker(sessions, search)
    listener = RebalanceListener()
    consumer = aiokafka.AIOKafkaConsumer(bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_search_group, enable_auto_commit=False, auto_offset_reset='earliest',
        max_poll_interval_ms=3600000)
    consumer.subscribe([settings.kafka_search_topic], listener=listener)
    try:
        await consumer.start()
        async for message in consumer:
            try:
                data = json.loads(message.value)
                if (not isinstance(data, dict) or data.get('version') != 1
                        or not isinstance(data.get('task_id'), str) or len(data['task_id']) != 32):
                    raise ValueError('Invalid search request envelope')
            except (ValueError, TypeError, UnicodeError):
                logger.exception('Discarding invalid Kafka search request')
            else:
                listener.work = asyncio.create_task(worker.execute(data['task_id']))
                try:
                    finished = await asyncio.shield(listener.work)
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
                    # Rejoin from committed offsets, including retained partitions.
                    raise DeliveryInterrupted()
                finally:
                    if listener.work.done():
                        listener.work = None
                if not finished:
                    raise DeliveryInterrupted()
            try:
                await consumer.commit({aiokafka.TopicPartition(message.topic, message.partition): message.offset + 1})
            except aiokafka.errors.CommitFailedError:
                # A new consumer will observe the durable final state on redelivery.
                logger.info('Partition reassigned before search offset commit')
    finally:
        if listener.work is not None:
            listener.work.cancel()
            await asyncio.gather(listener.work, return_exceptions=True)
            listener.work = None
        await consumer.stop()


async def run(settings):
    db = database.Database(settings.database_url)
    store = factory.create_store(settings.qdrant_url, settings.movies_collection,
                                 settings.embedding_url, settings.embedding_cache)
    client = wikidata.WikidataClient()
    try:
        movies = catalog.read_movies(settings.movies_path)
        search = services.MovieSearchService(store, movies, client)
        while True:
            try:
                await consume(db.sessions, search, settings)
            except DeliveryInterrupted:
                logger.info('Search delivery interrupted; rejoining from committed offsets')
            except (aiokafka.errors.KafkaError, OSError):
                logger.exception('Kafka worker unavailable; retrying')
            await asyncio.sleep(5)
    finally:
        try:
            await client.close()
        finally:
            try:
                await store.close()
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
