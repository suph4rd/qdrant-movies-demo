from fastapi import Request

from web.application.services import account, admin, auth, search


def get_settings(request: Request):
    return request.app.state.settings


def get_catalog(request: Request):
    return request.app.state.catalog


def get_store(request: Request):
    return request.app.state.movie_store


def get_auth_service(request: Request):
    return auth.AuthService(request.app.state.database.sessions)


def get_account_service(request: Request):
    state = request.app.state
    return account.AccountService(state.database.sessions, getattr(state, 'catalog', []),
                                  getattr(state, 'movie_cards', {}))


def get_admin_service(request: Request):
    return admin.AdminService(request.app.state.database.sessions, get_account_service(request))


def get_search_service(request: Request):
    state = request.app.state
    return search.SearchService(state.catalog, state.movie_store, state.wikidata, state.search_results)
