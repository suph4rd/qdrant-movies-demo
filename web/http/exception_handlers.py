from starlette.exceptions import HTTPException

from web.application import errors
from web.http import security
from web.presentation import pages


async def render_error(request, exc):
    response = await pages.render(request, 'error.html', {'error': exc.detail}, status_code=exc.status_code)
    response.headers.update(exc.headers or {})
    return response


async def render_scenario_error(request, exc):
    return await render_error(request, security.scenario_failure(request, exc))


def register_exception_handlers(app):
    app.add_exception_handler(HTTPException, render_error)
    app.add_exception_handler(errors.ScenarioError, render_scenario_error)
