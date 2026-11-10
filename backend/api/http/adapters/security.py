from backend.api.http import dependencies
from backend.api.http.transport import security


async def current_user(request):
    return await dependencies.get_auth_service(request).current_user(request.cookies.get(security.SESSION_COOKIE))


async def require_user(request):
    user = await current_user(request)
    if user is None:
        raise security.failure(request, 401, 'Authentication required')
    return user


async def require_admin(request):
    user = await require_user(request)
    if user.role != 'admin':
        raise security.failure(request, 403, 'Administrator access required')
    return user


