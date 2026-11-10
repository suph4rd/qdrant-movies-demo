from fastapi import APIRouter, Depends, Request

from backend.api.http import dependencies
from backend.api.http.adapters import context as request_context, security as authentication
from backend.api.http.transport import i18n, pagination, responses, schemas, security
from backend.api.presentation import api as presentation


router = APIRouter(prefix='/api')


@router.get('/account')
async def account(request: Request):
    user = await authentication.require_user(request)
    lists = await dependencies.get_account_service(request).lists(
        user.id, request.query_params.get('list', 'watched'), pagination.page_number(request))
    return responses.response(request, {'lists': [presentation.movie_list(group, i18n.select_language(request))
                                       for group in lists], 'marks': await request_context.marks(request, user)})


@router.post('/account/marks', dependencies=[Depends(security.check_api_csrf)])
async def update_mark(request: Request, body: schemas.MarkInput):
    user = await authentication.require_user(request)
    await dependencies.get_account_service(request).update_mark(
        user.id, body.movie_id, body.flag, body.state, body.reference)
    return responses.response(request, {'marks': await request_context.marks(request, user)})
