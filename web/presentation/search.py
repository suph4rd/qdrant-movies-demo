from urllib.parse import urlencode

from engine import errors
from engine import i18n as engine_i18n
from web.application import constants as web_constants
from web.http import dependencies
from web.http import i18n as web_i18n
from web.http import responses
from web.presentation import pages


class IndexPage:
    def __init__(self, request, catalog, store, params=None):
        self.request = request
        self.params = request.query_params if params is None else params
        self.catalog = catalog
        self.store = store
        self.lang = web_i18n.select_language(request)
        self.mode = self.params.get('mode', web_constants.DEFAULT_MODE)
        self.query = self.params.get('q', '')
        self.limit = self.params.get('limit', web_constants.DEFAULT_WEB_LIMIT)

    def localize_result(self, result):
        by_id = {m['id']: m for m in self.catalog}

        def localize(movie, movie_id=None):
            movie = by_id.get(movie_id if movie_id is not None else movie.get('id'), movie)
            if not isinstance(movie, dict) or not movie.get('title'):
                raise errors.MovieNotFoundError('unknown_id', id=movie_id)
            localized = engine_i18n.localize_movie(movie, self.lang)
            if getattr(self, 'shared_context', {}).get('user'):
                try:
                    localized['mark_reference'] = self.request.app.state.movie_cards.reference(self.catalog, movie)
                except Exception as exc:
                    if not errors.is_expected_error(exc):
                        raise
            return localized

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
        return pages.translate(message, self.lang, **params)

    def context(self, result, error):
        return {'query': self.query, 'mode': self.mode, 'result': result, 'error': error,
                'catalog': [engine_i18n.localize_movie(m, self.lang) for m in self.catalog], 'limit': self.limit,
                'lang': self.lang, 'switches': self.language_switches(), '_': self.gettext,
                'search_modes': web_constants.SEARCH_MODES, 'limit_options': web_constants.LIMIT_OPTIONS}

    def render_template(self, context):
        context.update({key: value for key, value in getattr(self, 'shared_context', {}).items()
                        if key != 'switches'})
        response = pages.templates.TemplateResponse(request=self.request, name='index.html', context=context)
        return responses.finish(self.request, response, context)

    async def render(self):
        self.shared_context = await pages.context(self.request)
        result, error = None, None
        try:
            raw = await dependencies.get_search_service(self.request).search(self.params)
            result = self.localize_result(raw) if raw is not None else None
        except Exception as exc:
            if not errors.is_expected_error(exc):
                raise
            error = errors.format_error(exc, self.lang)
        user = self.shared_context['user']
        marks = {}
        if user is not None:
            marks = await dependencies.get_account_service(self.request).all_marks(user.id)
        movie_count = None
        try:
            movie_count = await self.store.count_movies()
        except Exception as exc:
            if not errors.is_expected_error(exc):
                raise
        context = self.context(result, error)
        context['movie_count'] = movie_count
        context['marks'] = marks
        return self.render_template(context)
