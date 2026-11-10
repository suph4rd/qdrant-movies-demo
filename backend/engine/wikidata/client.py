from backend.engine.wikidata import classification
from backend.engine.wikidata import entities
from backend.engine.wikidata import parsing
from backend.engine.wikidata import movies
from backend.engine.wikidata import search
from backend.engine.wikidata import transport


class WikidataClient:
    def __init__(self, client=None):
        self._transport = transport.WikidataTransport(client)
        self.client = self._transport.client
        self._owns_client = self._transport._owns_client
        self._entities = entities.EntityRepository(self)
        self._classifier = classification.EntityClassifier(self)
        self._mapper = movies.MovieMapper(self, lambda roots, cache: self.classification(roots, cache))
        self._search = search.WikidataSearch(self, self)

    async def close(self):
        await self._transport.close()

    async def movie(self, qid, cache=None):
        return await self._mapper.movie(qid, cache)

    async def search(self, title, year=None):
        return await self._search.search(title, year)

    async def request(self, **params):
        return await self._transport.request(**params)

    async def candidates(self, title):
        return await self._entities.candidates(title)

    async def entities(self, qids, cache):
        return await self._entities.entities(qids, cache)

    async def classification(self, roots, cache):
        return await self._classifier.classify(roots, cache)

    @staticmethod
    def year(entity):
        return parsing.year(entity)

    @staticmethod
    def matches_entity(entity, title, year):
        return search.WikidataSearch.matches_entity(entity, title, year)
