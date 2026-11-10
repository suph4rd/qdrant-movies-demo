from fastapi import APIRouter, Depends, Request, WebSocket

from backend.api.http import dependencies
from backend.api.http.adapters import context, notifications as search_notifications, search_task_helpers
from backend.api.http.transport import i18n, responses, security
from backend.api.presentation import search_tasks as presentation


router = APIRouter(prefix='/api')


@router.get('/search-tasks')
async def list_tasks(request: Request):
    user, guest = await search_task_helpers.identity(request)
    tasks = await dependencies.get_search_task_service(request).list(user.id if user else None, guest)
    return responses.response(request, {'tasks': [presentation.summary(task) for task in tasks]})


@router.get('/search-tasks/{task_id}')
async def read_task(request: Request, task_id: str):
    user, task = await search_task_helpers.owned_task(request, task_id)
    state = request.app.state
    detail = presentation.detail(task, i18n.select_language(request), state.catalog,
                                 state.movie_cards if user else None)
    return responses.response(request, {'task': detail, 'marks': await context.marks(request, user),
                                 'movie_count': await context.movie_count(request)})


@router.post('/search-tasks/{task_id}/read', dependencies=[Depends(security.check_api_csrf)])
async def mark_read(request: Request, task_id: str):
    await search_task_helpers.owned_task(request, task_id, read=True)
    return responses.response(request, {'ok': True})


@router.websocket('/notifications/ws')
async def notifications(websocket: WebSocket):
    await search_notifications.SearchNotifications(websocket).run()
