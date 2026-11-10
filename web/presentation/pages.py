from pathlib import Path
from urllib.parse import urlencode

from fastapi.templating import Jinja2Templates

from engine import i18n as engine_i18n
from web.http import i18n
from web.http import responses
from web.http import security


PACKAGE_PATH = Path(__file__).resolve().parents[1]
TEMPLATES_PATH = PACKAGE_PATH / 'templates'
STATIC_PATH = PACKAGE_PATH / 'static'

templates = Jinja2Templates(directory=TEMPLATES_PATH)


def translate(message, lang, **params):
    return engine_i18n.translate_message(message, lang, **params)


async def context(request):
    lang = i18n.select_language(request)
    return {'lang': lang, 'user': await security.current_user(request),
            'return_url': request.url.path + ('?' + request.url.query if request.url.query else ''),
            'csrf_token': security.csrf_token(request),
            '_': lambda message, **params: translate(message, lang, **params),
            'switches': {language: str(request.url.replace(query=urlencode(
                {**dict(request.query_params), 'lang': language}))) for language in ('en', 'ru')}}


async def render(request, template, values=None, status_code=200):
    data = {**await context(request), **(values or {})}
    return responses.finish(request, templates.TemplateResponse(request=request, name=template,
                  context=data, status_code=status_code), data)
