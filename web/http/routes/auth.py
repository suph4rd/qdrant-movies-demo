from urllib.parse import urlencode
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from web.application import constants
from web.application import credential_validation
from web.application import errors
from web.http import dependencies
from web.http import i18n
from web.http import security
from web.presentation import auth as presentation


router = APIRouter()


def redirect(request, path):
    lang = i18n.select_language(request)
    response = RedirectResponse(path + '?' + urlencode({'lang': lang}), status_code=303)
    return i18n.remember_language(response, lang)


def issue_cookie(request, response, token):
    response.set_cookie(security.SESSION_COOKIE, token, max_age=constants.SESSION_SECONDS,
                        httponly=True, samesite='lax',
                        secure=request.app.state.settings.cookie_secure)
    # Rotate the CSRF token when authentication changes.
    response.set_cookie(security.CSRF_COOKIE, secrets.token_urlsafe(32), httponly=True,
                        samesite='lax', secure=request.app.state.settings.cookie_secure)
    return response


@router.get('/register', name='register')
async def register_form(request: Request):
    return await presentation.render_form(request, registration=True)


@router.get('/login', name='login')
async def login_form(request: Request):
    return await presentation.render_form(request)


@router.post('/register')
async def register(request: Request):
    form = await security.check_csrf(request)
    email = form.get('email', '')
    try:
        token = await dependencies.get_auth_service(request).register(
            email, form.get('password', ''), form.get('password_repeat', ''),
            request.cookies.get(security.SESSION_COOKIE))
    except errors.ScenarioError as exc:
        status = 409 if isinstance(exc, errors.EmailRegistered) else 400
        shown_email = credential_validation.normalize_email(email) if status == 409 else email
        return await presentation.render_form(request, True, str(exc), shown_email, status)
    return issue_cookie(request, redirect(request, '/account'), token)


@router.post('/login')
async def login(request: Request):
    form = await security.check_csrf(request)
    email = form.get('email', '')
    try:
        token = await dependencies.get_auth_service(request).login(
            email, form.get('password', ''), request.cookies.get(security.SESSION_COOKIE))
    except errors.ScenarioError as exc:
        return await presentation.render_form(request, False, str(exc), email, 400)
    return issue_cookie(request, redirect(request, '/account'), token)


@router.post('/logout', name='logout')
async def logout(request: Request):
    await security.check_csrf(request)
    await dependencies.get_auth_service(request).logout(request.cookies.get(security.SESSION_COOKIE))
    response = redirect(request, '/')
    response.delete_cookie(security.SESSION_COOKIE, httponly=True, samesite='lax',
                           secure=request.app.state.settings.cookie_secure)
    response.set_cookie(security.CSRF_COOKIE, secrets.token_urlsafe(32), httponly=True,
                        samesite='lax', secure=request.app.state.settings.cookie_secure)
    return response
