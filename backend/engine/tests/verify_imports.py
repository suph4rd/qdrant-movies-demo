import asyncio
import os
import tempfile
import uuid

from backend.engine import catalog
from backend.engine import constants
from backend.engine import imports
from backend.engine import services
from backend.engine.stores import semantic


async def verify():
    name = 'movies_import_check_' + uuid.uuid4().hex
    directory = tempfile.TemporaryDirectory()
    options = {
        'base_url': os.environ.get('QDRANT_URL', constants.DEFAULT_URL),
        'embedding_url': os.environ.get('EMBEDDING_URL', constants.DEFAULT_EMBEDDING_URL),
        'collection_name': name, 'cache_path': directory.name,
    }
    store = semantic.SemanticMovieStore(**options)
    movie = {
        'id': imports.WIKIDATA_ID_BASE + 999999999, 'wikidata_id': 'Q999999999',
        'source': 'wikidata', 'title': 'Import verification fixture',
        'original_title': 'Import verification fixture', 'year': 2020,
        'description': 'An astronaut explores a remote planet and returns home.',
        'genres': ['Science Fiction'], 'description_language': 'en',
        'alternative_titles': ['Integration fixture alias'],
        'translations': {'en': {'title': 'Import verification fixture',
            'description': 'An astronaut explores a remote planet and returns home.',
            'genres': ['Science Fiction']}},
    }
    data = catalog.read_movies(constants.DEFAULT_DATA_PATH)
    try:
        assert await store.load(constants.DEFAULT_DATA_PATH) == {'loaded': 250, 'count': 250}
        competing = semantic.SemanticMovieStore(**options)
        try:
            results = await asyncio.gather(store.import_movie(movie, data),
                                           competing.import_movie(movie, data),
                                           store.import_movie(movie, data))
        finally:
            await competing.close()
        assert sum(r['created'] for r in results) == 1
        assert (await store.client.count(collection_name=name, exact=True)).count == 251
        await store.close()
        store = semantic.SemanticMovieStore(**options)
        assert (await store.find_movies('Integration fixture alias', 2020))[0]['id'] == movie['id']
        assert not (await store.import_movie(movie, data))['created']
        assert await store.load(constants.DEFAULT_DATA_PATH) == {'loaded': 250, 'count': 251}
        result = await services.search_movies(store, movie['title'], data)
        assert result['groups'][0]['source']['id'] == movie['id']
        assert all(p['id'] != movie['id'] for p in result['groups'][0]['recommendations'])
        result = await store.recommend(1, exclude_ids=[1, movie['id']], limit=10)
        assert all(p['id'] not in (1, movie['id']) for p in result['recommendations'])
        print('OK: isolated collection; real TEI; concurrent and repeated import; '
              'new store persistence; reload retains 250 originals plus imported record; source exclusion.')
    finally:
        try:
            await store.client.delete_collection(collection_name=name)
        finally:
            await store.close()
            directory.cleanup()


if __name__ == '__main__':
    asyncio.run(verify())
