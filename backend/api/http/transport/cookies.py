import secrets

from backend.api.application import constants
from backend.api.http.transport import security


def csrf_cookie(request, result, token):
    result.set_cookie(security.CSRF_COOKIE, token, httponly=True, samesite='lax',
                      secure=request.app.state.settings.cookie_secure)


def guest_token(request):
    value = request.cookies.get(security.GUEST_COOKIE, '')
    return value if len(value) == 43 and all(c.isalnum() or c in '-_' for c in value) else secrets.token_urlsafe(32)


def guest_cookie(request, result, token):
    result.set_cookie(security.GUEST_COOKIE, token, max_age=31536000, httponly=True,
                      samesite='lax', secure=request.app.state.settings.cookie_secure)


def session_cookie(request, result, token):
    options = {'httponly': True, 'samesite': 'lax', 'secure': request.app.state.settings.cookie_secure}
    if token:
        result.set_cookie(security.SESSION_COOKIE, token, max_age=constants.SESSION_SECONDS, **options)
    else:
        result.delete_cookie(security.SESSION_COOKIE, **options)
