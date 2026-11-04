from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings, SettingsConfigDict

from engine import DEFAULT_DATA_PATH, catalog, store as movie_store
from web.router import router

PACKAGE_PATH = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra='forbid')
    qdrant_url: str = 'http://127.0.0.1:6333'
    movies_path: Path = DEFAULT_DATA_PATH


def create_app(settings=None):
    settings = settings if isinstance(settings, Settings) else Settings(**(settings or {}))

    @asynccontextmanager
    async def lifespan(app):
        app.state.catalog = catalog.read_movies(settings.movies_path)
        store = movie_store.QdrantMovieStore(settings.qdrant_url)
        app.state.movie_store = store
        try:
            yield
        finally:
            await store.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.mount('/static', StaticFiles(directory=PACKAGE_PATH / 'static'), name='static')
    app.include_router(router)
    return app
