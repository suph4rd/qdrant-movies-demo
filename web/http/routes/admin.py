from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from web.application import errors
from web.http import dependencies
from web.http import i18n
from web.http import security
from web.presentation import admin as presentation
from web.presentation import pages


router = APIRouter()


def page_number(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise errors.ScenarioError('Invalid page.') from None
    if not 1 <= value <= 1000000:
        raise errors.ScenarioError('Invalid page.')
    return value


@router.get('/admin/users', name='admin_users')
async def users(request: Request):
    try:
        await security.require_admin(request)
        query = request.query_params.get('q', '').strip()[:254]
        role = request.query_params.get('role', '')
        state = request.query_params.get('state', '')
        page = page_number(request.query_params.get('page', '1'))
        result = await dependencies.get_admin_service(request).list_users(query, role, state, page)
        return await pages.render(request, 'admin_users.html', {
            'users': result.users, 'q': query, 'role_filter': role, 'state_filter': state,
            'previous_url': presentation.page_url(request, page - 1) if page > 1 else None,
            'next_url': presentation.page_url(request, page + 1) if result.has_next else None,
            'state_name': presentation.state_name})
    except errors.ScenarioError as exc:
        raise security.scenario_failure(request, exc) from exc


@router.get('/admin/users/{user_id}', name='admin_user')
async def user_detail(request: Request, user_id: int):
    try:
        await security.require_admin(request)
        page = page_number(request.query_params.get('page', '1'))
        result = await dependencies.get_admin_service(request).detail(user_id, page)
        return await pages.render(request, 'admin_user.html',
            presentation.user_detail(request, result, page, i18n.select_language(request)))
    except errors.ScenarioError as exc:
        raise security.scenario_failure(request, exc) from exc


@router.post('/admin/users/{user_id}', name='admin_change_user')
async def update_user(request: Request, user_id: int):
    try:
        await security.require_admin(request)
        form = await security.check_csrf(request)
        await dependencies.get_admin_service(request).change_user(
            request.cookies.get(security.SESSION_COOKIE, ''), user_id,
            form.get('action', ''), form.get('confirmation_email', ''))
        lang = i18n.select_language(request)
        return i18n.remember_language(RedirectResponse(
            str(request.url_for('admin_user', user_id=user_id)) + '?' + urlencode({'lang': lang}),
            status_code=303), lang)
    except errors.ScenarioError as exc:
        raise security.scenario_failure(request, exc) from exc
