import json
import math
from pathlib import Path
import requests

from engine.i18n import localize_movie, translate


class DemoError(Exception):
    def __init__(self, key, **params):
        self.key = key
        self.params = params
        super().__init__(key)

    def format(self, lang='en'):
        params = dict(self.params)
        if self.key == 'ambiguous':
            params['titles'] = ', '.join(localize_movie(m, lang)['title'] for m in params.pop('movies'))
        return translate(self.key, lang, **params)

    def __str__(self):
        return self.format()


class QdrantMovieStore:
    def __init__(self, base_url):
        self.base_url = base_url

    def request(self, method, path, body=None):
        try:
            response = requests.request(
                method, self.base_url.rstrip('/') + path, json=body,
                headers={'Content-Type': 'application/json'}, timeout=15)
            response.raise_for_status()
            return response.json()['result']
        except requests.exceptions.HTTPError as exc:
            raise DemoError('http', status=exc.response.status_code, detail=exc.response.text) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise DemoError('response') from exc
        except (requests.exceptions.RequestException, OSError) as exc:
            raise DemoError('connection', url=self.base_url, detail=exc) from exc

    def load(self, path):
        movies = read_movies(path)
        collections = self.request('GET', '/collections')['collections']
        if not any(c['name'] == 'movies' for c in collections):
            self.request('PUT', '/collections/movies', {'vectors': {'size': 10, 'distance': 'Cosine'}})
        info = self.request('GET', '/collections/movies')
        vectors = info['config']['params']['vectors']
        if not isinstance(vectors, dict) or vectors.get('size') != 10 or vectors.get('distance') != 'Cosine' or vectors.get('multivector_config'):
            raise DemoError('schema')
        points = [{'id': m['id'], 'vector': m['vector'], 'payload': {k: v for k, v in m.items() if k != 'vector'}} for m in movies]
        self.request('PUT', '/collections/movies/points?wait=true', {'points': points})
        count = self.request('POST', '/collections/movies/points/count', {'exact': True})['count']
        if count != 250:
            raise DemoError('count')

        return {'loaded': len(points), 'count': count}

    def recommend(self, movie_id, limit=5):
        validate_limit(limit)
        validate_id(movie_id)
        points = self.request('POST', '/collections/movies/points', {'ids': [movie_id], 'with_payload': True})
        if not points:
            raise DemoError('unknown_id', id=movie_id)
        result = self.request('POST', '/collections/movies/points/query', {
            'query': movie_id, 'filter': {'must_not': [{'has_id': [movie_id]}]},
            'limit': limit, 'with_payload': True, 'params': {'exact': True}})['points']
        return {'source': points[0]['payload'], 'recommendations': result}


def read_movies(path):
    try:
        movies = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise DemoError('read', detail=exc) from exc
    if not isinstance(movies, list) or len(movies) != 250:
        raise DemoError('size')
    ids = set()
    for m in movies:
        if not isinstance(m, dict):
            raise DemoError('object')
        i, v = m.get('id'), m.get('vector')
        if type(i) is not int or not 0 <= i < 2**64 or i in ids:
            raise DemoError('duplicate_id', id=i)
        ids.add(i)
        if (not isinstance(v, list) or len(v) != 10 or
            not all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in v)
            or not any(v)):
            raise DemoError('vector', id=i)
        translations = m.get('translations')
        english = translations.get('en') if isinstance(translations, dict) else None
        if not valid_metadata(m) or not valid_metadata(english):
            raise DemoError('metadata', id=i)
        if type(m.get('year')) is not int:
            raise DemoError('year', id=i)
    return movies


def validate_id(movie_id):
    if type(movie_id) is not int or not 0 <= movie_id < 2**64:
        raise DemoError('id')


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


def validate_limit(limit):
    if type(limit) is not int or not 1 <= limit <= 249:
        raise DemoError('limit')


def search(store, query, catalog, limit=5):
    validate_limit(limit)
    return store.recommend(resolve_movie(query, catalog)['id'], limit=limit)


def valid_metadata(movie):
    return (isinstance(movie, dict)
            and all(isinstance(movie.get(k), str) and movie[k].strip()
                    for k in ('title', 'description'))
            and isinstance(movie.get('genres'), list) and bool(movie['genres'])
            and all(isinstance(g, str) and g.strip() for g in movie['genres']))


def movie_titles(movie):
    return [movie['title'], localize_movie(movie, 'en')['title']]
