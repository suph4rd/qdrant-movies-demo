from urllib.parse import urlencode

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

from engine import i18n as engine_i18n
from web.application import constants as web_constants
from web.http import dependencies
from web.http import i18n as web_i18n
from web.http import security
from web.presentation import search as presentation


async def index(request: Request, catalog=Depends(dependencies.get_catalog), store=Depends(dependencies.get_store)):
    return await presentation.IndexPage(request, catalog, store).render()


async def search(request: Request):
    form = await security.check_csrf(request)
    lang = form.get('lang')
    if lang not in engine_i18n.LANGUAGES:
        lang = web_i18n.select_language(request)
    params = {'q': form.get('query', ''), 'mode': form.get('mode', web_constants.DEFAULT_MODE),
              'limit': form.get('limit', web_constants.DEFAULT_WEB_LIMIT), 'lang': lang}
    token = await dependencies.get_search_service(request).submit(params)
    params['result'] = token
    response = RedirectResponse(str(request.url_for('index')) + '?' + urlencode(params), status_code=303)
    return web_i18n.remember_language(response, lang)
