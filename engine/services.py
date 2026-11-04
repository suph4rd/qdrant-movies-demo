from engine import catalog as movie_catalog, validators


async def search(store, query, catalog, limit=5):
    validators.validate_limit(limit)
    return await store.recommend(movie_catalog.resolve_movie(query, catalog)['id'], limit=limit)
