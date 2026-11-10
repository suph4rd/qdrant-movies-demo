from backend.engine import errors as engine_errors
from backend.api.application import constants
from backend.api.http import dependencies
from backend.api.http.transport import i18n
from backend.api.presentation import api as presentation


async def marks(request, user):
    return await dependencies.get_account_service(request).all_marks(user.id) if user else {}


async def movie_count(request):
    try:
        return await request.app.state.movie_store.count_movies()
    except Exception as exc:
        if not engine_errors.is_expected_error(exc):
            raise
        return None


async def context_data(request, user, csrf):
    lang = i18n.select_language(request)
    state = request.app.state
    count = await movie_count(request)
    return {'user': user, 'lang': lang, 'csrf_token': csrf,
            'catalog': [presentation.movie(item, lang) for item in state.catalog],
            'search_modes': constants.SEARCH_MODES, 'limit_options': constants.LIMIT_OPTIONS,
            'default_mode': constants.DEFAULT_MODE, 'default_limit': constants.DEFAULT_WEB_LIMIT,
            'movie_count': count, 'marks': await marks(request, user)}

