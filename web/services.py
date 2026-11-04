from pathlib import Path
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

from engine import services
from engine.catalog import resolve_movie
from engine.errors import DemoError
from engine.i18n import LANGUAGES, catalog as translation_catalog, localize_movie
from web.i18n import remember_language, select_language


templates = Jinja2Templates(directory=Path(__file__).resolve().parent / 'templates')


class IndexService:
    def __init__(self, request, catalog, store):
        self.request = request
        self.catalog = catalog
        self.store = store
        self.lang = select_language(request)
        self.translator = translation_catalog(self.lang)
        self.query = request.query_params.get('q', '')
        self.limit = request.query_params.get('limit', '5')

    async def prepare_result(self):
        if self.limit not in ('5', '10', '20', '50'):
            raise DemoError('web_limit')
        if 'q' not in self.request.query_params:
            return None
        result = await services.search(self.store, self.query, self.catalog, limit=int(self.limit))
        return self.localize_result(result)

    def localize_result(self, result):
        by_id = {m['id']: localize_movie(m, self.lang) for m in self.catalog}
        source_id = resolve_movie(self.query, self.catalog)['id']
        recommendations = []
        for point in result['recommendations']:
            if point['id'] not in by_id:
                raise DemoError('unknown_id', id=point['id'])
            recommendations.append({**point, 'payload': by_id[point['id']]})
        return {'source': by_id[source_id], 'recommendations': recommendations}

    def language_switches(self):
        params = {'limit': self.limit}
        if 'q' in self.request.query_params:
            params['q'] = self.query
        return {language: str(self.request.url_for('index')) + '?' + urlencode(dict(params, lang=language))
                for language in LANGUAGES}

    def gettext(self, message, **params):
        return self.translator.gettext(message) % params

    def context(self, result, error):
        return dict(query=self.query, result=result, error=error,
                    catalog=[localize_movie(m, self.lang) for m in self.catalog], limit=self.limit,
                    lang=self.lang, switches=self.language_switches(), _=self.gettext)

    def render_template(self, context):
        response = templates.TemplateResponse(request=self.request, name='index.html', context=context)
        return remember_language(response, self.lang)

    async def render(self):
        result, error = None, None
        try:
            result = await self.prepare_result()
        except DemoError as exc:
            error = exc.format(self.lang)
        return self.render_template(self.context(result, error))
