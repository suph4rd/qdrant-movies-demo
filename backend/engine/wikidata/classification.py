from backend.engine.wikidata import constants
from backend.engine.wikidata import parsing


class EntityClassifier:
    def __init__(self, entities):
        self.entities = entities

    async def classify(self, roots, cache):
        pending, seen = set(roots), set()
        film, adult, television = False, False, False
        for _ in range(8):
            film = film or constants.FILM in pending
            adult = adult or bool(constants.ADULT_TYPES & pending)
            television = television or constants.TELEVISION_SERIES in pending
            pending -= {constants.FILM, constants.TELEVISION_SERIES, *constants.ADULT_TYPES}
            pending -= seen
            if not pending:
                return film, adult, television
            seen.update(pending)
            if len(seen) > 64:
                return None
            nodes = await self.entities.entities(sorted(pending), cache)
            pending = {parent for node in nodes for parent in parsing.item_values(node, 'P279')}
        return None
