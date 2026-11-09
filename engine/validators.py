import math

from engine import constants
from engine import errors


def validate_catalog(movies):
    if not isinstance(movies, list) or len(movies) != constants.MOVIE_COUNT:
        raise errors.CatalogValidationError('size')
    ids = set()
    for m in movies:
        if not isinstance(m, dict):
            raise errors.CatalogValidationError('object')
        i, v = m.get('id'), m.get('vector')
        if type(i) is not int or not 0 <= i < 2**64 or i in ids:
            raise errors.CatalogValidationError('duplicate_id', id=i)
        ids.add(i)
        if (not isinstance(v, list) or len(v) != constants.VECTOR_DIMENSIONS or
            not all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in v)
            or not any(v)):
            raise errors.CatalogValidationError('vector', id=i)
        translations = m.get('translations')
        english = translations.get('en') if isinstance(translations, dict) else None
        if not valid_metadata(m) or not valid_metadata(english):
            raise errors.CatalogValidationError('metadata', id=i)
        if type(m.get('year')) is not int:
            raise errors.CatalogValidationError('year', id=i)
    return movies


def validate_id(movie_id):
    if type(movie_id) is not int or not 0 <= movie_id < 2**64:
        raise errors.InputValidationError('id')


def validate_limit(limit):
    if type(limit) is not int or not 1 <= limit < constants.MOVIE_COUNT:
        raise errors.InputValidationError('limit')


def valid_metadata(movie):
    return (isinstance(movie, dict)
            and all(isinstance(movie.get(k), str) and movie[k].strip()
                    for k in ('title', 'description'))
            and isinstance(movie.get('genres'), list) and bool(movie['genres'])
            and all(isinstance(g, str) and g.strip() for g in movie['genres']))
