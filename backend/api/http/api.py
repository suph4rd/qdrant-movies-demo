import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from backend.engine import errors as engine_errors
from backend.api.application import constants, errors
from backend.api.http import dependencies, i18n, security
from backend.api.presentation import api as presentation


router = APIRouter(prefix='/api')


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SearchInput(Input):
    q: StrictStr
    mode: StrictStr = constants.DEFAULT_MODE
    limit: StrictStr = constants.DEFAULT_WEB_LIMIT


class LoginInput(Input):
    email: StrictStr
    password: StrictStr


class RegistrationInput(LoginInput):
    password_repeat: StrictStr


class MarkInput(Input):
    movie_id: StrictStr
    flag: StrictStr
    state: StrictBool
    reference: StrictStr = ''


class AdminInput(Input):
    action: StrictStr
    confirmation_email: StrictStr = ''


def response(request, data, status=200):
    result = JSONResponse(jsonable_encoder(data), status_code=status)
    result.headers['Cache-Control'] = 'no-store'
    return i18n.remember_language(result, i18n.select_language(request))


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


def csrf_cookie(request, result, token):
    result.set_cookie(security.CSRF_COOKIE, token, httponly=True, samesite='lax',
                      secure=request.app.state.settings.cookie_secure)


@router.get('/context')
async def context(request: Request):
    token = security.csrf_token(request)
    result = response(request, await context_data(request, await security.current_user(request), token))
    csrf_cookie(request, result, token)
    return result


@router.post('/search', dependencies=[Depends(security.check_api_csrf)])
async def submit_search(request: Request, body: SearchInput):
    token = await dependencies.get_search_service(request).submit(body.model_dump())
    return response(request, {'token': token})


@router.get('/search')
async def read_search(request: Request):
    try:
        raw = await dependencies.get_search_service(request).search(request.query_params)
        user = await security.current_user(request)
        state = request.app.state
        result = presentation.search_result(raw, i18n.select_language(request), state.catalog,
                                            state.movie_cards if user else None)
    except Exception as exc:
        if not engine_errors.is_expected_error(exc):
            raise
        return response(request, {'error': engine_errors.format_error(exc, i18n.select_language(request))}, 400)
    return response(request, {'result': result, 'marks': await marks(request, user),
                              'movie_count': await movie_count(request)})


async def auth_response(request, token=None):
    csrf = secrets.token_urlsafe(32)
    user = await dependencies.get_auth_service(request).current_user(token) if token else None
    result = response(request, await context_data(request, user, csrf))
    options = {'httponly': True, 'samesite': 'lax', 'secure': request.app.state.settings.cookie_secure}
    if token:
        result.set_cookie(security.SESSION_COOKIE, token, max_age=constants.SESSION_SECONDS, **options)
    else:
        result.delete_cookie(security.SESSION_COOKIE, **options)
    csrf_cookie(request, result, csrf)
    return result


@router.post('/register', dependencies=[Depends(security.check_api_csrf)])
async def register(request: Request, body: RegistrationInput):
    token = await dependencies.get_auth_service(request).register(
        body.email, body.password, body.password_repeat, request.cookies.get(security.SESSION_COOKIE))
    return await auth_response(request, token)


@router.post('/login', dependencies=[Depends(security.check_api_csrf)])
async def login(request: Request, body: LoginInput):
    token = await dependencies.get_auth_service(request).login(
        body.email, body.password, request.cookies.get(security.SESSION_COOKIE))
    return await auth_response(request, token)


@router.post('/logout', dependencies=[Depends(security.check_api_csrf)])
async def logout(request: Request):
    await dependencies.get_auth_service(request).logout(request.cookies.get(security.SESSION_COOKIE))
    return await auth_response(request)


def page_number(request):
    raw = request.query_params.get('page', '1')
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 7 or not 1 <= int(raw) <= 1000000:
        raise errors.ScenarioError('Invalid page number.')
    return int(raw)


@router.get('/account')
async def account(request: Request):
    user = await security.require_user(request)
    lists = await dependencies.get_account_service(request).lists(
        user.id, request.query_params.get('list', 'watched'), page_number(request))
    return response(request, {'lists': [presentation.movie_list(group, i18n.select_language(request))
                                       for group in lists], 'marks': await marks(request, user)})


@router.post('/account/marks', dependencies=[Depends(security.check_api_csrf)])
async def update_mark(request: Request, body: MarkInput):
    user = await security.require_user(request)
    await dependencies.get_account_service(request).update_mark(
        user.id, body.movie_id, body.flag, body.state, body.reference)
    return response(request, {'marks': await marks(request, user)})


@router.get('/admin/users')
async def users(request: Request):
    await security.require_admin(request)
    page = page_number(request)
    result = await dependencies.get_admin_service(request).list_users(
        request.query_params.get('q', '').strip()[:254], request.query_params.get('role', ''),
        request.query_params.get('state', ''), page)
    return response(request, {'users': result.users, 'has_next': result.has_next, 'page': page})


@router.get('/admin/users/{user_id}')
async def user_detail(request: Request, user_id: int):
    await security.require_admin(request)
    page = page_number(request)
    detail = await dependencies.get_admin_service(request).detail(user_id, page)
    lists = [presentation.movie_list(group, i18n.select_language(request)) for group in detail.lists]
    return response(request, {'user': detail.user, 'lists': lists, 'page': page,
                              'has_next': any(group['has_next'] for group in lists)})


@router.post('/admin/users/{user_id}', dependencies=[Depends(security.check_api_csrf)])
async def change_user(request: Request, user_id: int, body: AdminInput):
    await security.require_admin(request)
    await dependencies.get_admin_service(request).change_user(
        request.cookies.get(security.SESSION_COOKIE, ''), user_id, body.action, body.confirmation_email)
    return response(request, {'ok': True})
