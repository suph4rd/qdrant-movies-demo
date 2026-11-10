from fastapi import APIRouter, Depends, Request

from backend.api.http import dependencies
from backend.api.http.adapters import responses as authentication_responses
from backend.api.http.transport import schemas, security


router = APIRouter(prefix='/api')


@router.post('/register', dependencies=[Depends(security.check_api_csrf)])
async def register(request: Request, body: schemas.RegistrationInput):
    token = await dependencies.get_auth_service(request).register(
        body.email, body.password, body.password_repeat, request.cookies.get(security.SESSION_COOKIE))
    return await authentication_responses.auth_response(request, token)


@router.post('/login', dependencies=[Depends(security.check_api_csrf)])
async def login(request: Request, body: schemas.LoginInput):
    token = await dependencies.get_auth_service(request).login(
        body.email, body.password, request.cookies.get(security.SESSION_COOKIE))
    return await authentication_responses.auth_response(request, token)


@router.post('/logout', dependencies=[Depends(security.check_api_csrf)])
async def logout(request: Request):
    await dependencies.get_auth_service(request).logout(request.cookies.get(security.SESSION_COOKIE))
    return await authentication_responses.auth_response(request)
