from fastapi import FastAPI

from backend.engine import catalog
from backend.engine import wikidata
from backend.engine.stores import factory
from backend.api import config
from backend.api.http import routes
from backend.api.http.transport import exception_handlers
from backend.api.infrastructure import database
from backend.api.infrastructure import snapshots


class ApplicationLifespan:
    def __init__(self, settings, app):
        self.settings = settings
        self.app = app
        self.store = None
        self.wikidata = None
        self.database = None

    async def __aenter__(self):
        self.app.state.catalog = catalog.read_movies(self.settings.movies_path)
        self.store = factory.create_store(
            self.settings.qdrant_url, self.settings.movies_collection,
            self.settings.embedding_url, self.settings.embedding_cache)
        try:
            self.database = database.Database(self.settings.database_url)
            self.app.state.database = self.database
            self.wikidata = wikidata.WikidataClient()
            self.app.state.wikidata = self.wikidata
            self.app.state.search_results = snapshots.SearchResults()
            self.app.state.movie_cards = snapshots.MovieCards()
            self.app.state.movie_store = self.store
        except BaseException:
            try:
                await self.store.close()
            finally:
                if self.database is not None:
                    await self.database.close()
            raise
        return None

    async def __aexit__(self, exc_type, exc_value, traceback):
        try:
            if self.wikidata is not None:
                await self.wikidata.close()
        finally:
            try:
                await self.store.close()
            finally:
                if self.database is not None:
                    await self.database.close()


def create_app(settings=None):
    settings = settings if isinstance(settings, config.Settings) else config.Settings(**(settings or {}))

    def lifespan(app):
        return ApplicationLifespan(settings, app)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    exception_handlers.register_exception_handlers(app)

    app.state.settings = settings
    app.include_router(routes.router)
    return app
