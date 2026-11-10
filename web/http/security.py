import secrets

from fastapi import HTTPException

from engine import i18n as engine_i18n
from web.application import errors
from web.http import dependencies
from web.http import i18n


def failure(request, status, message):
    return HTTPException(status, engine_i18n.translate_message(message, i18n.select_language(request)))


SESSION_COOKIE = 'movie_session'
CSRF_COOKIE = 'movie_csrf'


async def current_user(request):
    return await dependencies.get_auth_service(request).current_user(request.cookies.get(SESSION_COOKIE))


async def require_user(request):
    user = await current_user(request)
    if user is None:
        raise failure(request, 401, 'Authentication required')
    return user


async def require_admin(request):
    user = await require_user(request)
    if user.role != 'admin':
        raise failure(request, 403, 'Administrator access required')
    return user


def csrf_token(request):
    return request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)


async def check_csrf(request):
    form = await request.form()
    cookie = request.cookies.get(CSRF_COOKIE, '')
    supplied = form.get('csrf_token', '')
    if not cookie or not isinstance(supplied, str) or not secrets.compare_digest(cookie, supplied):
        raise failure(request, 403, 'Invalid CSRF token')
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise failure(request, 403, 'Invalid origin')
    return form


def scenario_failure(request, exc):
    status = 400
    if isinstance(exc, errors.AuthenticationRequired):
        status = 401
    elif isinstance(exc, errors.AdministratorRequired):
        status = 403
    elif isinstance(exc, errors.UserNotFound):
        status = 404
    return HTTPException(status, engine_i18n.translate_message(
        exc.message, i18n.select_language(request), **exc.params))
