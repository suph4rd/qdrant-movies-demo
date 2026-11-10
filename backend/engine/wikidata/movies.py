import re

from backend.engine import imports
from backend.engine.wikidata import parsing
from backend.engine.wikidata import validators


class MovieMapper:
    def __init__(self, entities, classify):
        self.entities = entities
        self.classify = classify

    async def movie(self, qid, cache=None):
        cache = {} if cache is None else cache
        entity = (await self.entities.entities([qid], cache))[0]
        roots = parsing.item_values(entity, 'P31')
        genres = parsing.item_values(entity, 'P136')
        classification = await self.classify(roots, cache)
        if classification is None:
            return None
        is_film, adult, television = classification
        if not is_film or adult or television:
            return None
        genre_classification = await self.classify(genres, cache)
        if genre_classification is None or genre_classification[1]:
            return None
        title = parsing.localized(entity, 'labels', 'en') or parsing.localized(entity, 'labels', 'mul')
        description = parsing.localized(entity, 'descriptions', 'en')
        genre_entities = await self.entities.entities(genres, cache)
        english_genres = [parsing.localized(genre, 'labels', 'en') for genre in genre_entities]
        if not title or not description or not english_genres or not all(english_genres):
            raise validators.invalid()
        russian_genres = [parsing.localized(genre, 'labels', 'ru') or english
                          for genre, english in zip(genre_entities, english_genres)]
        russian_description = parsing.localized(entity, 'descriptions', 'ru')
        originals = parsing.values(entity, 'P1476')
        for original in originals:
            if not isinstance(original, dict) or not isinstance(original.get('text'), str) or not original['text'].strip():
                raise validators.invalid()
        aliases = entity.get('aliases', {})
        if not isinstance(aliases, dict):
            raise validators.invalid()
        alternatives = []
        for language in ('en', 'ru'):
            language_aliases = aliases.get(language, [])
            if not isinstance(language_aliases, list):
                raise validators.invalid()
            for alias in language_aliases:
                if not isinstance(alias, dict) or not isinstance(alias.get('value'), str) or not alias['value'].strip():
                    raise validators.invalid()
                alternatives.append(alias['value'].strip())
        alternatives.extend(original['text'].strip() for original in originals)
        movie = {
            'id': imports.WIKIDATA_ID_BASE + int(qid[1:]), 'wikidata_id': qid, 'source': 'wikidata',
            'title': parsing.localized(entity, 'labels', 'ru') or title,
            'description': russian_description or description, 'genres': russian_genres,
            'year': parsing.year(entity), 'original_title': originals[0]['text'].strip() if originals else title,
            'description_language': 'ru' if russian_description else 'en', 'description_kind': 'short',
            'alternative_titles': sorted(set(alternatives)),
            'translations': {'en': {'title': title, 'description': description, 'genres': english_genres}},
        }
        external_ids = parsing.values(entity, 'P4947')
        if external_ids:
            value = external_ids[0]
            if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', value) or int(value) >= 2**32:
                raise validators.invalid()
            movie['tmdb_id'] = int(value)
        return imports.validate_movie(movie)
