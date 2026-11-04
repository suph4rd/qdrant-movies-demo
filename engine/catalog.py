import json
from pathlib import Path

from engine.errors import DemoError
from engine.i18n import localize_movie
from engine.validators import validate_catalog, validate_id


def read_movies(path):
    try:
        movies = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise DemoError('read', detail=exc) from exc
    return validate_catalog(movies)


def resolve_movie(query, catalog):
    query = query.strip()
    if not query:
        raise DemoError('empty')
    movie_id = None
    if query.lstrip('+-').isdecimal():
        try:
            movie_id = int(query)
        except ValueError as exc:
            raise DemoError('id') from exc
        validate_id(movie_id)
        matches = [m for m in catalog if m['id'] == movie_id]
        if matches:
            return matches[0]
    title = query.casefold()
    matches = [m for m in catalog if any(t.casefold() == title for t in movie_titles(m))]
    if not matches:
        matches = [m for m in catalog if any(title in t.casefold() for t in movie_titles(m))]
    if not matches:
        if movie_id is not None:
            raise DemoError('unknown_id', id=movie_id)
        raise DemoError('not_found')
    if len(matches) > 1:
        raise DemoError('ambiguous', movies=matches)
    return matches[0]


def movie_titles(movie):
    return [movie['title'], localize_movie(movie, 'en')['title']]
