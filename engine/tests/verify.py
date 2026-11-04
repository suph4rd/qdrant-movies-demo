from engine import catalog as movie_catalog, store as movie_store
from engine.errors import DemoError
import math
import asyncio
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace as NS
from qdrant_client import models
from markupsafe import escape
from engine import DEFAULT_DATA_PATH, services
from engine.i18n import localize_movie
from web.app import create_app


async def verify():
    store = movie_store.QdrantMovieStore('http://127.0.0.1:6333')
    try:
        data = movie_catalog.read_movies(DEFAULT_DATA_PATH)
        for _ in range(2):
            assert await store.load(DEFAULT_DATA_PATH) == {'loaded': 250, 'count': 250}
            assert (await store.client.count(collection_name='movies', exact=True)).count == 250
        payload = (await store.client.retrieve(collection_name='movies', ids=[1], with_payload=True))[0].payload
        assert payload['translations'] == data[0]['translations']
        for movie_id in (1, 16, 21):
            for limit in (5, 10, 20, 50):
                results = (await store.recommend(movie_id, limit=limit))['recommendations']
                assert len(results) == limit and movie_id not in {p['id'] for p in results}
                source = next(m['vector'] for m in data if m['id'] == movie_id)
                def cosine(v):
                    return sum(x*y for x,y in zip(source,v)) / math.sqrt(sum(x*x for x in source)*sum(x*x for x in v))
                scores = {m['id']: cosine(m['vector']) for m in data if m['id'] != movie_id}
                expected = sorted(scores.values(), reverse=True)[:limit]
                for point, score in zip(results, expected):
                    assert abs(point['score'] - scores[point['id']]) < 1e-5
                    assert abs(point['score'] - score) < 1e-5
        by_id = await services.search(store, '1', data)
        by_title = await services.search(store, '  мАтРиЦа  ', data)
        assert by_id == by_title == await services.search(store, 'The Matrix', data)
        assert len(by_id['recommendations']) == 5
        try:
            await store.recommend(999)
        except DemoError as exc:
            assert exc.key == 'unknown_id'
        else:
            raise AssertionError('Unknown ID accepted')
        for vectors in (models.VectorParams(size=3, distance='Cosine'),
                        models.VectorParams(size=10, distance='Dot'),
                        {'named': models.VectorParams(size=10, distance='Cosine')},
                        models.VectorParams(size=10, distance='Cosine',
                            multivector_config=models.MultiVectorConfig(comparator='max_sim'))):
            client = AsyncMock()
            client.get_collections.return_value = NS(collections=[NS(name='movies')])
            client.get_collection.return_value = NS(config=NS(params=NS(vectors=vectors)))
            mock_store = movie_store.QdrantMovieStore('http://unused', client=client)
            try:
                await mock_store.load(DEFAULT_DATA_PATH)
            except DemoError as exc:
                assert exc.key == 'schema'
                client.create_collection.assert_not_awaited()
                client.upsert.assert_not_awaited()
            else:
                raise AssertionError('Incompatible collection accepted')
        legacy = {'source': {k: v for k, v in by_id['source'].items() if k != 'translations'},
                  'recommendations': [{**p, 'payload': {k: v for k, v in p['payload'].items() if k != 'translations'}}
                                      for p in by_id['recommendations']]}
        from fastapi.testclient import TestClient
        app = create_app()
        for lang in ('en', 'ru'):
            with TestClient(app) as client:
                with patch.object(app.state.movie_store, 'recommend', return_value=legacy):
                    page = client.get('/', params={'q': 'The Matrix', 'lang': lang}).text
            assert localize_movie(data[0], lang)['title'] in page
            assert page.count('<article>') == 5
            for point in legacy['recommendations']:
                movie = next(m for m in data if m['id'] == point['id'])
                assert str(escape(localize_movie(movie, lang)['title'])) in page
    finally:
        await store.close()
    print('OK: two loads retain 250 records; translations, 5/10/20/50 results, cosine ranking, source exclusion, unknown IDs, schema protection, and legacy payload localization.')


if __name__ == '__main__':
    asyncio.run(verify())
