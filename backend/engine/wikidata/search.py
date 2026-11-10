from backend.engine import errors
from backend.engine import imports
from backend.engine.wikidata import parsing
from backend.engine.wikidata import validators


class WikidataSearch:
    def __init__(self, entities, mapper):
        self.entities = entities
        self.mapper = mapper

    @staticmethod
    def matches_entity(entity, title, year):
        names = {parsing.localized(entity, 'labels', language) for language in ('en', 'ru', 'mul')}
        aliases = entity.get('aliases', {})
        if not isinstance(aliases, dict):
            raise validators.invalid()
        for language in ('en', 'ru'):
            language_aliases = aliases.get(language, [])
            if not isinstance(language_aliases, list):
                raise validators.invalid()
            for alias in language_aliases:
                if not isinstance(alias, dict) or not isinstance(alias.get('value'), str):
                    raise validators.invalid()
                names.add(alias['value'])
        for original in parsing.values(entity, 'P1476'):
            if not isinstance(original, dict) or not isinstance(original.get('text'), str):
                raise validators.invalid()
            names.add(original['text'])
        if imports.normalize_title(title) not in {imports.normalize_title(name) for name in names if name.strip()}:
            return False
        if year is None:
            return True
        try:
            return parsing.year(entity) == year
        except errors.InputValidationError:
            # Non-film namesakes may have no release date. Validate required
            # movie dates only after the entity has been classified as a film.
            return True

    async def search(self, title, year=None):
        title, parsed_year = imports.parse_query(title)
        year = parsed_year if year is None else year
        # Finish both search paginations before any card can be imported.
        candidates = await self.entities.candidates(title)
        movies, messages, cache = [], [], {}
        for qid in candidates:
            try:
                entity = (await self.entities.entities([qid], cache))[0]
                if not self.matches_entity(entity, title, year):
                    continue
                movie = await self.mapper.movie(qid, cache)
            except Exception as exc:
                if not errors.is_expected_error(exc):
                    raise
                key, params = exc._localization
                messages.append({'key': 'wikidata_skipped', 'params': {'id': qid}})
                messages.append({'key': key, 'params': params})
                if key in ('wikidata_rate_limit', 'wikidata_unavailable'):
                    break
                continue
            if movie is not None and imports.matches(movie, title, year):
                movies.append(movie)
        return {'movies': movies, 'messages': messages}
