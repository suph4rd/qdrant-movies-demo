from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from engine import catalog
from engine import wikidata
from engine.stores import factory
from web import config
from web.http import router as web_router
from web.http import exception_handlers
from web.infrastructure import database
from web.infrastructure import snapshots
from web.presentation import pages


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
    app.mount('/static', StaticFiles(directory=pages.STATIC_PATH), name='static')
    app.include_router(web_router.router)
    return app
