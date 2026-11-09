from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic_settings import BaseSettings, SettingsConfigDict

from engine import catalog
from engine import constants
from engine import wikidata
from engine.embeddings import constants as embedding_constants
from engine.stores import factory
from web import constants as web_constants
from web import router as web_router


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra='forbid')
    qdrant_url: str = constants.DEFAULT_URL
    movies_path: Path = constants.DEFAULT_DATA_PATH
    embedding_url: str = constants.DEFAULT_EMBEDDING_URL
    movies_collection: str = constants.DEFAULT_COLLECTION
    embedding_cache: Path = embedding_constants.DEFAULT_CACHE_PATH


class ApplicationLifespan:
    def __init__(self, settings, app):
        self.settings = settings
        self.app = app
        self.store = None
        self.wikidata = None

    async def __aenter__(self):
        self.app.state.catalog = catalog.read_movies(self.settings.movies_path)
        self.store = factory.create_store(
            self.settings.qdrant_url, self.settings.movies_collection,
            self.settings.embedding_url, self.settings.embedding_cache)
        try:
            self.wikidata = wikidata.WikidataClient()
            self.app.state.wikidata = self.wikidata
            self.app.state.search_results = OrderedDict()
            self.app.state.movie_store = self.store
        except BaseException:
            await self.store.close()
            raise
        return None

    async def __aexit__(self, exc_type, exc_value, traceback):
        try:
            if self.wikidata is not None:
                await self.wikidata.close()
        finally:
            await self.store.close()


def create_app(settings=None):
    settings = settings if isinstance(settings, Settings) else Settings(**(settings or {}))

    def lifespan(app):
        return ApplicationLifespan(settings, app)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.mount('/static', StaticFiles(directory=web_constants.STATIC_PATH), name='static')
    app.include_router(web_router.router)
    return app
