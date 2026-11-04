from fastapi import Request


def get_settings(request: Request):
    return request.app.state.settings


def get_catalog(request: Request):
    return request.app.state.catalog


def get_store(request: Request):
    return request.app.state.movie_store
