from urllib.parse import urlencode

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

from engine.i18n import LANGUAGES
from web.dependencies import get_catalog, get_store
from web.i18n import remember_language, select_language
from web.services import IndexService


async def index(request: Request, catalog=Depends(get_catalog), store=Depends(get_store)):
    return await IndexService(request, catalog, store).render()


async def search(request: Request):
    form = await request.form()
    lang = form.get('lang')
    if lang not in LANGUAGES:
        lang = select_language(request)
    response = RedirectResponse(str(request.url_for('index')) + '?' + urlencode(dict(
        q=form.get('query', ''), limit=form.get('limit', '5'), lang=lang)), status_code=303)
    return remember_language(response, lang)
