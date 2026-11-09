from engine import catalog as movie_catalog
from engine import constants
from engine import validators
from engine.embeddings import texts as embedding_texts


async def search(store, query, catalog, limit=constants.DEFAULT_LIMIT):
    validators.validate_limit(limit)
    return await store.recommend(movie_catalog.resolve_movie(query, catalog)['id'], limit=limit)


async def semantic_search(store, query, limit=constants.DEFAULT_LIMIT):
    validators.validate_limit(limit)
    embedding_texts.query_text(query)
    return await store.semantic_search(query, limit=limit)
