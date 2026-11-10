from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from web.application import errors
from web.http import dependencies
from web.http import i18n
from web.http import security
from web.presentation import account as presentation
from web.presentation import pages


router = APIRouter()


@router.get('/account', name='account')
async def account(request: Request):
    try:
        user = await security.require_user(request)
        lang = i18n.select_language(request)
        flag = request.query_params.get('list', 'watched')
        page = presentation.page_number(request.query_params.get('page', '1'))
        if page is None:
            raise errors.ScenarioError('Invalid page number.')
        lists = await dependencies.get_account_service(request).lists(user.id, flag, page)
        return await pages.render(request, 'account.html', {
            'lists': [presentation.movie_list(listing, lang) for listing in lists]})
    except errors.ScenarioError as exc:
        raise security.scenario_failure(request, exc) from exc


@router.post('/account/marks', name='account_mark')
async def update_mark(request: Request):
    try:
        user = await security.require_user(request)
        form = await security.check_csrf(request)
        flag, state = form.get('flag'), form.get('state')
        if state not in ('true', 'false'):
            raise errors.ScenarioError('Invalid movie mark.')
        await dependencies.get_account_service(request).update_mark(
            user.id, form.get('movie_id', ''), flag, state == 'true', form.get('reference', ''))
        lang = form.get('lang')
        if lang not in ('en', 'ru'):
            lang = i18n.select_language(request)
        response = RedirectResponse(presentation.mark_return_url(form.get('return_url'), flag, lang), status_code=303)
        return i18n.remember_language(response, lang)
    except errors.ScenarioError as exc:
        raise security.scenario_failure(request, exc) from exc
