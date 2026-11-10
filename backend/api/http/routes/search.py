from fastapi import APIRouter, Depends, Request

from backend.engine import errors as engine_errors, i18n as engine_i18n
from backend.api.http import dependencies
from backend.api.http.adapters import context as request_context, security as authentication
from backend.api.http.transport import cookies, i18n, responses, schemas, security
from backend.api.presentation import api as presentation


router = APIRouter(prefix='/api')


@router.post('/search', dependencies=[Depends(security.check_api_csrf)])
async def submit_search(request: Request, body: schemas.SearchInput):
    params = body.model_dump()
    try:
        token = await dependencies.get_search_service(request).submit(params)
    except Exception as exc:
        if getattr(exc, '_localization', (None,))[0] != 'search_saved_only':
            raise
        guest = cookies.guest_token(request)
        user = await authentication.current_user(request)
        task, conflict = await dependencies.get_search_task_service(request).submit(
            params, user.id if user else None, guest)
        data = {'task_id': task.id, 'status': task.status}
        if conflict:
            data.update(code='external_search_in_progress', error=engine_i18n.translate_message(
                'An external search is already in progress. Local search is still available.',
                i18n.select_language(request)))
        result = responses.response(request, data, 409 if conflict else 202)
        cookies.guest_cookie(request, result, guest)
        return result
    return responses.response(request, {'token': token})


@router.get('/search')
async def read_search(request: Request):
    try:
        raw = await dependencies.get_search_service(request).search(request.query_params)
        user = await authentication.current_user(request)
        state = request.app.state
        result = presentation.search_result(raw, i18n.select_language(request), state.catalog,
                                            state.movie_cards if user else None)
    except Exception as exc:
        if not engine_errors.is_expected_error(exc):
            raise
        return responses.response(request, {'error': engine_errors.format_error(exc, i18n.select_language(request))}, 400)
    return responses.response(request, {'result': result, 'marks': await request_context.marks(request, user),
                              'movie_count': await request_context.movie_count(request)})
