from urllib.parse import urlencode

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

from engine import i18n as engine_i18n
from web import constants as web_constants
from web import dependencies
from web import i18n as web_i18n
from web import services as web_services


async def index(request: Request, catalog=Depends(dependencies.get_catalog), store=Depends(dependencies.get_store)):
    return await web_services.IndexService(request, catalog, store).render()


async def search(request: Request):
    form = await request.form()
    lang = form.get('lang')
    if lang not in engine_i18n.LANGUAGES:
        lang = web_i18n.select_language(request)
    response = RedirectResponse(str(request.url_for('index')) + '?' + urlencode({
        'q': form.get('query', ''), 'mode': form.get('mode', web_constants.DEFAULT_MODE),
        'limit': form.get('limit', web_constants.DEFAULT_WEB_LIMIT), 'lang': lang}), status_code=303)
    return web_i18n.remember_language(response, lang)
