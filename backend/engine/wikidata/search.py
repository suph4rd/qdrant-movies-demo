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
        names = WikidataSearch.entity_names(entity)
        if imports.normalize_title(title) not in {imports.normalize_title(name) for name in names}:
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
        messages, cache, seen, ranked = [], {}, set(), {}
        failures = []

        def record(exc):
            if not errors.is_expected_error(exc):
                raise exc
            failures.append(exc)
            key, params = exc._localization
            messages.append({'key': key, 'params': params})

        variants = list(dict.fromkeys([title, imports.normalize_title(title)]))
        for stage in range(len(variants) + 1):
            try:
                if stage < len(variants):
                    candidates = await self.entities.candidates(variants[stage])
                    for exc in getattr(candidates, 'failures', []):
                        record(exc)
                else:
                    candidates, source_failures = await self.entities.wikipedia_candidates(title)
                    for exc in source_failures:
                        record(exc)
            except Exception as exc:
                record(exc)
                continue
            candidates = [qid for qid in dict.fromkeys(candidates) if qid not in seen]
            seen.update(candidates)
            provider_failed = False
            # Batch the cards, but isolate malformed cards so valid peers survive.
            try:
                await self.entities.entities(candidates, cache)
            except Exception as exc:
                record(exc)
                if exc._localization[0] in ('wikidata_unavailable', 'wikidata_rate_limit'):
                    provider_failed = True
                    candidates = [qid for qid in candidates if qid in cache]
            exact = []
            for qid in candidates:
                try:
                    entity = (await self.entities.entities([qid], cache))[0]
                    # Do not traverse unrelated namesakes, or cards with a wrong year.
                    names = self.entity_names(entity)
                    score = max((imports.similarity(title, name) for name in names), default=0)
                    if score < 0.85:
                        continue
                    if year is not None:
                        try:
                            if parsing.year(entity) != year:
                                continue
                        except errors.InputValidationError:
                            pass
                    movie = await self.mapper.movie(qid, cache)
                    if movie is None or (year is not None and movie['year'] != year):
                        continue
                    ranked[qid] = (score, movie)
                    if score == 1:
                        exact.append(movie)
                except Exception as exc:
                    record(exc)
                    messages.append({'key': 'wikidata_skipped', 'params': {'id': qid}})
                    if exc._localization[0] in ('wikidata_unavailable', 'wikidata_rate_limit'):
                        provider_failed = True
                        break
            if exact:
                return {'movies': exact, 'messages': messages}
            if provider_failed:
                return {'movies': [], 'messages': messages}
            ordered = sorted(ranked.values(), key=lambda value: value[0], reverse=True)
            if ordered and ordered[0][0] >= 0.90 and (
                    len(ordered) == 1 or ordered[0][0] - ordered[1][0] >= 0.05):
                movie = ordered[0][1]
                messages.append({'key': 'wikidata_corrected', 'params': {'title': movie['title']}})
                return {'movies': [movie], 'messages': messages}
        if not seen and failures:
            raise failures[0]
        return {'movies': [], 'messages': messages}

    @staticmethod
    def entity_names(entity):
        names = [parsing.localized(entity, 'labels', language) for language in ('en', 'ru', 'mul')]
        aliases = entity.get('aliases', {})
        if not isinstance(aliases, dict):
            raise validators.invalid()
        for language in ('en', 'ru'):
            values = aliases.get(language, [])
            if not isinstance(values, list):
                raise validators.invalid()
            for alias in values:
                if not isinstance(alias, dict) or not isinstance(alias.get('value'), str):
                    raise validators.invalid()
                names.append(alias['value'])
        for original in parsing.values(entity, 'P1476'):
            if not isinstance(original, dict) or not isinstance(original.get('text'), str):
                raise validators.invalid()
            names.append(original['text'])
        return [name for name in names if name.strip()]
