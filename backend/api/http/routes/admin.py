from fastapi import APIRouter, Depends, Request

from backend.api.http import dependencies
from backend.api.http.adapters import security as authentication
from backend.api.http.transport import i18n, pagination, responses, schemas, security
from backend.api.presentation import api as presentation


router = APIRouter(prefix='/api')


@router.get('/admin/users')
async def users(request: Request):
    await authentication.require_admin(request)
    page = pagination.page_number(request)
    result = await dependencies.get_admin_service(request).list_users(
        request.query_params.get('q', '').strip()[:254], request.query_params.get('role', ''),
        request.query_params.get('state', ''), page)
    return responses.response(request, {'users': result.users, 'has_next': result.has_next, 'page': page})


@router.get('/admin/users/{user_id}')
async def user_detail(request: Request, user_id: int):
    await authentication.require_admin(request)
    page = pagination.page_number(request)
    detail = await dependencies.get_admin_service(request).detail(user_id, page)
    lists = [presentation.movie_list(group, i18n.select_language(request)) for group in detail.lists]
    return responses.response(request, {'user': detail.user, 'lists': lists, 'page': page,
                              'has_next': any(group['has_next'] for group in lists)})


@router.post('/admin/users/{user_id}', dependencies=[Depends(security.check_api_csrf)])
async def change_user(request: Request, user_id: int, body: schemas.AdminInput):
    await authentication.require_admin(request)
    await dependencies.get_admin_service(request).change_user(
        request.cookies.get(security.SESSION_COOKIE, ''), user_id, body.action, body.confirmation_email)
    return responses.response(request, {'ok': True})
