from backend.api.http import dependencies
from backend.api.http.adapters import security as authentication
from backend.api.http.transport import security


async def identity(request):
    user = await authentication.current_user(request)
    return user, request.cookies.get(security.GUEST_COOKIE)


async def owned_task(request, task_id, read=False):
    user, guest = await identity(request)
    task = await dependencies.get_search_task_service(request).get(
        task_id, user.id if user else None, guest, read=read)
    if task is None:
        raise security.failure(request, 404, 'Search task not found.')
    return user, task

