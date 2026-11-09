from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

from engine import errors
from engine import i18n as engine_i18n
from engine import services
from web import constants as web_constants
from web import i18n as web_i18n


templates = Jinja2Templates(directory=web_constants.TEMPLATES_PATH)


class IndexService:
    def __init__(self, request, catalog, store, params=None):
        self.request = request
        self.params = request.query_params if params is None else params
        self.catalog = catalog
        self.store = store
        self.lang = web_i18n.select_language(request)
        self.mode = self.params.get('mode', web_constants.DEFAULT_MODE)
        self.query = self.params.get('q', '')
        self.limit = self.params.get('limit', web_constants.DEFAULT_WEB_LIMIT)

    async def prepare_result(self, allow_import=False, raw=False):
        if self.mode not in web_constants.SEARCH_MODES:
            raise errors.InputValidationError('search_mode')
        if self.limit not in web_constants.LIMIT_OPTIONS:
            raise errors.InputValidationError('web_limit')
        if 'q' not in self.params:
            return None
        snapshot = self.request.app.state.search_results.get(self.params.get('result'))
        if not allow_import and snapshot and snapshot['params'] == (self.query, self.mode, self.limit):
            if snapshot['error'] is not None:
                raise snapshot['error']
            return self.localize_result(snapshot['result'])
        if self.mode == 'description':
            result = await services.semantic_search(self.store, self.query, limit=int(self.limit))
        else:
            search = services.MovieSearchService(
                self.store, self.catalog, self.request.app.state.wikidata)
            result = await search.search(self.query, limit=int(self.limit), allow_import=allow_import)
        return result if raw else self.localize_result(result)

    def localize_result(self, result):
        by_id = {m['id']: m for m in self.catalog}

        def localize(movie, movie_id=None):
            movie = by_id.get(movie_id if movie_id is not None else movie.get('id'), movie)
            if not isinstance(movie, dict) or not movie.get('title'):
                raise errors.MovieNotFoundError('unknown_id', id=movie_id)
            return engine_i18n.localize_movie(movie, self.lang)

        groups = []
        for group in result.get('groups', [result]):
            source = group['source']
            recommendations = [{**point, 'payload': localize(point['payload'], point['id'])}
                               for point in group['recommendations']]
            groups.append({'source': localize(source) if source is not None else None,
                           'recommendations': recommendations})
        messages = [errors.format_message(message, self.lang)
                    for message in result.get('messages', [])]
        return {'groups': groups, 'messages': messages}

    def language_switches(self):
        params = {'limit': self.limit, 'mode': self.mode}
        if 'q' in self.params:
            params['q'] = self.query
        if 'result' in self.params:
            params['result'] = self.params['result']
        return {language: str(self.request.url_for('index')) + '?' + urlencode({**params, 'lang': language})
                for language in engine_i18n.LANGUAGES}

    def gettext(self, message, **params):
        return engine_i18n.translate_message(message, self.lang, **params)

    def context(self, result, error):
        return {'query': self.query, 'mode': self.mode, 'result': result, 'error': error,
                'catalog': [engine_i18n.localize_movie(m, self.lang) for m in self.catalog], 'limit': self.limit,
                'lang': self.lang, 'switches': self.language_switches(), '_': self.gettext,
                'search_modes': web_constants.SEARCH_MODES, 'limit_options': web_constants.LIMIT_OPTIONS}

    def render_template(self, context):
        response = templates.TemplateResponse(request=self.request, name='index.html', context=context)
        return web_i18n.remember_language(response, self.lang)

    async def render(self):
        result, error = None, None
        try:
            result = await self.prepare_result()
        except Exception as exc:
            if not errors.is_expected_error(exc):
                raise
            error = errors.format_error(exc, self.lang)
        return self.render_template(self.context(result, error))
