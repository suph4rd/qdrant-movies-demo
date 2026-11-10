from web.http import i18n
from web.http import security


def finish(request, response, context):
    response.set_cookie(security.CSRF_COOKIE, context['csrf_token'], httponly=True,
                        secure=request.app.state.settings.cookie_secure, samesite='lax')
    return i18n.remember_language(response, context['lang'])


