import json
from pathlib import Path

from backend.engine import errors
from backend.engine import i18n as engine_i18n
from backend.engine import validators


def read_movies(path):
    try:
        movies = json.loads(Path(path).read_text(encoding='utf-8'))
    except OSError as exc:
        errors.annotate_error(exc, 'read', detail=exc)
        raise
    except json.JSONDecodeError as exc:
        errors.annotate_error(exc, 'read', detail=exc)
        raise
    except UnicodeDecodeError as exc:
        errors.annotate_error(exc, 'read', detail=exc)
        raise
    return validators.validate_catalog(movies)


def resolve_movie(query, catalog):
    query = query.strip()
    if not query:
        raise errors.InputValidationError('empty')
    movie_id = None
    if query.lstrip('+-').isdecimal():
        try:
            movie_id = int(query)
        except ValueError as exc:
            raise errors.InputValidationError('id') from exc
        validators.validate_id(movie_id)
        matches = [m for m in catalog if m['id'] == movie_id]
        if matches:
            return matches[0]
    title = query.casefold()
    matches = [m for m in catalog if any(t.casefold() == title for t in movie_titles(m))]
    if not matches:
        matches = [m for m in catalog if any(title in t.casefold() for t in movie_titles(m))]
    if not matches:
        if movie_id is not None:
            raise errors.MovieNotFoundError('unknown_id', id=movie_id)
        raise errors.MovieNotFoundError('not_found')
    if len(matches) > 1:
        raise errors.AmbiguousMovieError('ambiguous', movies=matches)
    return matches[0]


def movie_titles(movie):
    return [movie['title'], engine_i18n.localize_movie(movie, 'en')['title']]
