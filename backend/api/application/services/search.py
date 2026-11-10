from backend.engine import errors, services
from backend.api.application import constants


class SearchService:
    def __init__(self, catalog, store, wikidata, results):
        self.catalog = catalog
        self.store = store
        self.wikidata = wikidata
        self.results = results

    async def search(self, params, allow_import=False):
        mode = params.get('mode', constants.DEFAULT_MODE)
        limit = params.get('limit', constants.DEFAULT_WEB_LIMIT)
        query = params.get('q', '')
        if mode not in constants.SEARCH_MODES:
            raise errors.InputValidationError('search_mode')
        if limit not in constants.LIMIT_OPTIONS:
            raise errors.InputValidationError('web_limit')
        if 'q' not in params:
            return None
        snapshot = self.results.matching(params.get('result'), (query, mode, limit))
        if not allow_import and snapshot:
            if snapshot['error'] is not None:
                raise snapshot['error']
            return snapshot['result']
        if mode == 'description':
            return await services.semantic_search(self.store, query, limit=int(limit))
        search = services.MovieSearchService(self.store, self.catalog, self.wikidata)
        return await search.search(query, limit=int(limit), allow_import=allow_import)

    async def submit(self, params):
        result, error = None, None
        try:
            result = await self.search(params, allow_import=True)
        except Exception as exc:
            if not errors.is_expected_error(exc):
                raise
            error = exc
        return self.results.put({'params': (params['q'], params['mode'], params['limit']),
                                 'result': result, 'error': error})
