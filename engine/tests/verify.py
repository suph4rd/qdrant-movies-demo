import asyncio
import math
import os
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace as NS
from qdrant_client import models

from engine import catalog as movie_catalog
from engine import constants
from engine import errors
from engine import services
from engine.embeddings import client as embedding_client
from engine.embeddings import spec as embedding_spec
from engine.stores import semantic


def cosine(left, right):
    return sum(x*y for x,y in zip(left,right)) / (math.hypot(*left)*math.hypot(*right))


def assert_ranking(results, vectors, query, limit, exclude=None):
    scores = {i:cosine(query,v) for i,v in vectors.items() if i != exclude}
    expected = sorted(scores.values(),reverse=True)[:limit]
    assert len(results) == limit
    assert len({p['id'] for p in results}) == limit
    for point, score in zip(results, expected):
        assert point['id'] != exclude
        assert abs(point['score']-scores[point['id']]) < 1e-5
        assert abs(point['score']-score) < 1e-5


async def verify_schema_protection():
    for vectors in (models.VectorParams(size=10, distance='Cosine'),
                    {'semantic': models.VectorParams(size=10, distance='Cosine')},
                    {'semantic': models.VectorParams(size=embedding_spec.SPEC.dimensions, distance='Dot')}):
        client, embeddings = AsyncMock(), AsyncMock()
        embeddings.spec = embedding_spec.SPEC
        client.get_collections.return_value = NS(collections=[NS(name=constants.DEFAULT_COLLECTION)])
        client.get_collection.return_value = NS(config=NS(
            params=NS(vectors=vectors, sparse_vectors=None), metadata={'embedding': embedding_spec.SPEC.metadata()}))
        store = semantic.SemanticMovieStore('http://unused', client=client, embeddings=embeddings)
        try:
            await store.load(constants.DEFAULT_DATA_PATH)
        except errors.SemanticSchemaError as exc:
            assert exc._localization[0] == 'semantic_schema'
        else:
            raise AssertionError('Incompatible collection accepted')
        client.create_collection.assert_not_awaited()
        client.upsert.assert_not_awaited()
        embeddings.encode_documents.assert_not_awaited()
        await store.close()


async def verify():
    await verify_schema_protection()
    store=semantic.SemanticMovieStore(os.environ.get('QDRANT_URL',constants.DEFAULT_URL),
                             embedding_url=os.environ.get('EMBEDDING_URL',constants.DEFAULT_EMBEDDING_URL),
                             collection_name=os.environ.get('MOVIES_COLLECTION',constants.DEFAULT_COLLECTION),
                             **({'cache_path':os.environ['EMBEDDING_CACHE']} if 'EMBEDDING_CACHE' in os.environ else {}))
    try:
        data=movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)
        await store.load(constants.DEFAULT_DATA_PATH)
        with patch.object(embedding_client.EmbeddingClient, 'encode_documents', side_effect=AssertionError('Unexpected cache miss')):
            assert await store.load(constants.DEFAULT_DATA_PATH) == {'loaded':250,'count':250}
        assert (await store.client.count(collection_name=store.collection_name,exact=True)).count == 250
        records, offset=await store.client.scroll(collection_name=store.collection_name,limit=300,
                                                   with_vectors=True,with_payload=True)
        assert offset is None and len(records) == 250
        vectors={p.id:p.vector['semantic'] for p in records}
        by_id={m['id']:m for m in data}
        for point in records:
            assert point.payload['translations'] == by_id[point.id]['translations']
            assert point.payload['_embedding']['revision'] == store.spec.revision
        for movie_id in (1,16,21):
            for limit in (5,10,20,50):
                result=await store.recommend(movie_id,limit)
                assert_ranking(result['recommendations'],vectors,vectors[movie_id],limit,movie_id)
        assert await services.search(store,'1',data) == await services.search(store,'Матрица',data)
        assert await services.search(store,'1',data) == await services.search(store,'The Matrix',data)
        for query in ('An astronaut survives on Mars.','Космонавт выживает на Марсе.'):
            vector=await store.embeddings.encode_query(query)
            for limit in (5,10,20,50):
                result=await services.semantic_search(store,query,limit)
                assert result['source'] is None
                assert_ranking(result['recommendations'],vectors,vector,limit)
        try:
            await store.recommend(999)
        except errors.MovieNotFoundError as exc:
            assert exc._localization[0] == 'unknown_id'
        else:
            raise AssertionError('Unknown ID accepted')
    finally:
        await store.close()
    print('OK: semantic index, two loads, zero repeat inference, 250 records, independent cosine, '
          'both languages, both scenarios, limits and source exclusion.')


if __name__ == '__main__':
    asyncio.run(verify())
