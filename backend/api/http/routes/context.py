from fastapi import APIRouter, Request

from backend.api.http.adapters import context as request_context, security as authentication
from backend.api.http.transport import cookies, responses, security


router = APIRouter(prefix='/api')


@router.get('/context')
async def context(request: Request):
    token = security.csrf_token(request)
    result = responses.response(request, await request_context.context_data(request, await authentication.current_user(request), token))
    cookies.csrf_cookie(request, result, token)
    cookies.guest_cookie(request, result, cookies.guest_token(request))
    return result
