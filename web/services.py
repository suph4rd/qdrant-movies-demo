from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

from engine import catalog as movie_catalog
from engine import errors
from engine import i18n as engine_i18n
from engine import services
from web import constants as web_constants
from web import i18n as web_i18n


templates = Jinja2Templates(directory=web_constants.TEMPLATES_PATH)


class IndexService:
    def __init__(self, request, catalog, store):
        self.request = request
        self.catalog = catalog
        self.store = store
        self.lang = web_i18n.select_language(request)
        self.translator = engine_i18n.catalog(self.lang)
        self.mode = request.query_params.get('mode', web_constants.DEFAULT_MODE)
        self.query = request.query_params.get('q', '')
        self.limit = request.query_params.get('limit', web_constants.DEFAULT_WEB_LIMIT)

    async def prepare_result(self):
        if self.mode not in web_constants.SEARCH_MODES:
            raise errors.InputValidationError('search_mode')
        if self.limit not in web_constants.LIMIT_OPTIONS:
            raise errors.InputValidationError('web_limit')
        if 'q' not in self.request.query_params:
            return None
        if self.mode == 'description':
            result = await services.semantic_search(self.store, self.query, limit=int(self.limit))
        else:
            result = await services.search(self.store, self.query, self.catalog, limit=int(self.limit))
        return self.localize_result(result)

    def localize_result(self, result):
        by_id = {m['id']: engine_i18n.localize_movie(m, self.lang) for m in self.catalog}
        source_id = movie_catalog.resolve_movie(self.query, self.catalog)['id'] if self.mode == 'movie' else None
        recommendations = []
        for point in result['recommendations']:
            if point['id'] not in by_id:
                raise errors.MovieNotFoundError('unknown_id', id=point['id'])
            recommendations.append({**point, 'payload': by_id[point['id']]})
        return {'source': by_id[source_id] if source_id is not None else None, 'recommendations': recommendations}

    def language_switches(self):
        params = {'limit': self.limit, 'mode': self.mode}
        if 'q' in self.request.query_params:
            params['q'] = self.query
        return {language: str(self.request.url_for('index')) + '?' + urlencode({**params, 'lang': language})
                for language in engine_i18n.LANGUAGES}

    def gettext(self, message, **params):
        return self.translator.gettext(message) % params

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
