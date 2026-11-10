from backend.engine import catalog as movie_catalog
from backend.engine import constants
from backend.engine import errors
from backend.engine import imports
from backend.engine import validators
from backend.engine.embeddings import texts as embedding_texts


async def search(store, query, catalog, limit=constants.DEFAULT_LIMIT):
    validators.validate_limit(limit)
    return await store.recommend(movie_catalog.resolve_movie(query, catalog)['id'], limit=limit)


async def semantic_search(store, query, limit=constants.DEFAULT_LIMIT):
    validators.validate_limit(limit)
    embedding_texts.query_text(query)
    return await store.semantic_search(query, limit=limit)


class MovieSearchService:
    def __init__(self, store, catalog, wikidata=None):
        self.store = store
        self.catalog = catalog
        self.wikidata = wikidata

    async def search(self, query, limit=constants.DEFAULT_LIMIT, allow_import=False):
        validators.validate_limit(limit)
        title, year = imports.parse_query(query)
        if title.lstrip('+-').isdecimal() and year is None:
            return await self.search_id(title, limit)

        messages = []
        sources = await self.find_saved(title, year)
        if not sources:
            if not allow_import:
                raise errors.MovieNotFoundError('search_saved_only')
            sources = await self.import_movies(title, year, messages)
        groups = await self.recommend(sources, limit, messages)
        return {'groups': groups, 'messages': messages}

    async def search_id(self, title, limit):
        try:
            movie_id = int(title)
        except ValueError as exc:
            raise errors.InputValidationError('id') from exc
        validators.validate_id(movie_id)
        result = await self.store.recommend(movie_id, limit=limit)
        source = next((m for m in self.catalog if m['id'] == movie_id), result['source'])
        return {'groups': [{**result, 'source': source}], 'messages': []}

    async def find_saved(self, title, year):
        sources = [m for m in self.catalog if imports.matches(m, title, year)]
        if not sources:
            sources = await self.store.find_movies(title, year)
        # Preserve partial-title navigation for the original catalog, but only exact
        # external matches can trigger an import.
        if not sources:
            normalized = imports.normalize_title(title)
            sources = [m for m in self.catalog if (year is None or m['year'] == year)
                       and any(normalized in t for t in imports.titles(m))]
        return sources

    async def import_movies(self, title, year, messages):
        if self.wikidata is None:
            raise errors.MovieNotFoundError('wikidata_unavailable')
        external = await self.wikidata.search(title, year)
        messages.extend(external['messages'])
        sources = []
        for movie in external['movies']:
            try:
                saved = await self.store.import_movie(movie, self.catalog)
            except Exception as exc:
                if not errors.is_expected_error(exc):
                    raise
                messages.append({'key': 'import_failed', 'params': {
                    'title': movie['title'], 'error': exc}})
                continue
            sources.append(saved['movie'])
            messages.append({'key': 'import_added' if saved['created'] else 'import_existing',
                             'params': {'title': saved['movie']['title']}})
        if not external['movies'] and not messages:
            raise errors.MovieNotFoundError('wikidata_not_found')
        return sources

    async def recommend(self, sources, limit, messages):
        sources = list({movie['id']: movie for movie in sources}.values())
        excluded = [m['id'] for m in sources]
        groups = []
        for movie in sources:
            try:
                result = await self.store.recommend(movie['id'], limit=limit, exclude_ids=excluded)
            except Exception as exc:
                if not errors.is_expected_error(exc):
                    raise
                messages.append({'key': 'import_failed', 'params': {
                    'title': movie['title'], 'error': exc}})
                continue
            groups.append({**result, 'source': movie})
        return groups


async def search_movies(store, query, catalog, limit=constants.DEFAULT_LIMIT,
                        wikidata=None, allow_import=False):
    return await MovieSearchService(store, catalog, wikidata).search(query, limit, allow_import)
