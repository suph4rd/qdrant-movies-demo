import secrets

from backend.api.http import dependencies
from backend.api.http.adapters import context
from backend.api.http.transport import cookies, responses


async def auth_response(request, token=None):
    csrf = secrets.token_urlsafe(32)
    user = await dependencies.get_auth_service(request).current_user(token) if token else None
    result = responses.response(request, await context.context_data(request, user, csrf))
    cookies.session_cookie(request, result, token)
    cookies.csrf_cookie(request, result, csrf)
    return result

