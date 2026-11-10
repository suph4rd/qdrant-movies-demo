import asyncio
import os
from pathlib import Path
import signal

from backend.api import config
from backend.api.infrastructure import database
from backend.api.queue import worker
from backend.api.tests import test_api
from backend.engine import catalog, services
from backend.engine.stores import factory


async def run():
    settings = config.Settings(database_url=os.environ['QUEUE_TEST_DATABASE_URL'],
        movies_collection=os.environ['QUEUE_TEST_COLLECTION'],
        kafka_search_topic=os.environ['QUEUE_TEST_TOPIC'], kafka_search_group=os.environ['QUEUE_TEST_GROUP'])
    db = database.Database(settings.database_url)
    store = factory.create_store(settings.qdrant_url, settings.movies_collection,
                                 settings.embedding_url, settings.embedding_cache)
    original_import = store.import_movie

    async def import_movie(movie, movies):
        result = await original_import(movie, movies)
        Path(os.environ['QUEUE_TEST_MARKER']).touch()
        if os.environ.get('QUEUE_TEST_PAUSE') == '1':
            await asyncio.Event().wait()
        return result

    class External:
        async def search(self, title, year):
            return {'movies': [test_api.imported_movie()], 'messages': []}

    store.import_movie = import_movie
    search = services.MovieSearchService(store, catalog.read_movies(settings.movies_path), External())
    task = asyncio.create_task(worker.consume(db.sessions, search, settings))
    for signum in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(signum, task.cancel)
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        await store.close()
        await db.close()


if __name__ == '__main__':
    asyncio.run(run())
