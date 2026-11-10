from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from backend.engine import i18n as engine_i18n
from backend.api.application import errors
from backend.api.http.transport import i18n, security


def error_response(request, status, message, headers=None):
    response = JSONResponse({'error': message}, status_code=status, headers=headers)
    response.headers['Cache-Control'] = 'no-store'
    return i18n.remember_language(response, i18n.select_language(request))


async def render_error(request, exc):
    return error_response(request, exc.status_code, str(exc.detail), exc.headers)


async def render_scenario_error(request, exc):
    failure = security.scenario_failure(request, exc)
    if isinstance(exc, errors.EmailRegistered):
        failure.status_code = 409
    return await render_error(request, failure)


async def render_validation_error(request, exc):
    message = engine_i18n.translate_message('Invalid request.', i18n.select_language(request))
    return error_response(request, 422, message)


def register_exception_handlers(app):
    app.add_exception_handler(HTTPException, render_error)
    app.add_exception_handler(errors.ScenarioError, render_scenario_error)
    app.add_exception_handler(RequestValidationError, render_validation_error)
