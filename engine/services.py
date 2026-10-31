"""Каталог и рекомендации через REST Qdrant, без вывода в консоль."""
import json
import math
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DemoError(Exception):
    pass


def request(base, method, path, body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = Request(base.rstrip('/') + path, data=data, method=method,
                  headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=15) as response:
            return json.load(response)['result']
    except (ValueError, KeyError, TypeError) as exc:
        raise DemoError('Некорректный ответ Qdrant.') from exc
    except HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise DemoError(f'Qdrant HTTP {exc.code}: {detail}') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DemoError(f'Нет соединения с Qdrant ({base}): {exc}') from exc


def read_movies(path):
    try:
        movies = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise DemoError(f'Не удалось прочитать каталог фильмов: {exc}') from exc
    if not isinstance(movies, list) or len(movies) != 250:
        raise DemoError('В JSON должно быть ровно 250 фильмов.')
    ids = set()
    for m in movies:
        if not isinstance(m, dict):
            raise DemoError('Каждый фильм должен быть объектом.')
        i, v = m.get('id'), m.get('vector')
        if type(i) is not int or not 0 <= i < 2**64 or i in ids:
            raise DemoError(f'Некорректный или повторяющийся ID: {i}')
        ids.add(i)
        if (not isinstance(v, list) or len(v) != 10 or
            not all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in v)
            or not any(v)):
            raise DemoError(f'Фильм {i}: нужен ненулевой вектор из 10 чисел в диапазоне 0–1.')
        if not all(isinstance(m.get(k), str) and m[k].strip() for k in ('title', 'description')):
            raise DemoError(f'Фильм {i}: нужны название и описание.')
        if type(m.get('year')) is not int or not isinstance(m.get('genres'), list) or not m['genres'] or not all(isinstance(g, str) and g.strip() for g in m['genres']):
            raise DemoError(f'Фильм {i}: некорректные год или жанры.')
    return movies


def load(base, path):
    movies = read_movies(path)
    collections = request(base, 'GET', '/collections')['collections']
    if not any(c['name'] == 'movies' for c in collections):
        request(base, 'PUT', '/collections/movies', {'vectors': {'size': 10, 'distance': 'Cosine'}})
    info = request(base, 'GET', '/collections/movies')
    vectors = info['config']['params']['vectors']
    if not isinstance(vectors, dict) or vectors.get('size') != 10 or vectors.get('distance') != 'Cosine' or vectors.get('multivector_config'):
        raise DemoError('Несовместимая коллекция movies: требуется один безымянный вектор размерности 10, метрика Cosine. Существующие данные не изменены.')
    points = [{'id': m['id'], 'vector': m['vector'], 'payload': {k: v for k, v in m.items() if k != 'vector'}} for m in movies]
    request(base, 'PUT', '/collections/movies/points?wait=true', {'points': points})
    count = request(base, 'POST', '/collections/movies/points/count', {'exact': True})['count']
    if count != 250:
        raise DemoError('В movies есть дополнительные записи; они сохранены. Для демо ожидается 250.')

    return {'loaded': len(points), 'count': count}


def recommend(base, movie_id, limit=5):
    validate_limit(limit)
    validate_id(movie_id)
    points = request(base, 'POST', '/collections/movies/points', {'ids': [movie_id], 'with_payload': True})
    if not points:
        raise DemoError(f'Неизвестный ID фильма: {movie_id}. Посмотрите ID в movies.json.')
    result = request(base, 'POST', '/collections/movies/points/query', {
        'query': movie_id, 'filter': {'must_not': [{'has_id': [movie_id]}]},
        'limit': limit, 'with_payload': True, 'params': {'exact': True}})['points']
    return {'source': points[0]['payload'], 'recommendations': result}


def validate_id(movie_id):
    if type(movie_id) is not int or not 0 <= movie_id < 2**64:
        raise DemoError('ID должен быть целым числом от 0 до 2^64−1.')


def resolve_movie(query, catalog):
    query = query.strip()
    if not query:
        raise DemoError('Введите название или ID фильма.')
    if query.lstrip('+-').isdecimal():
        try:
            movie_id = int(query)
        except ValueError as exc:
            raise DemoError('ID должен быть целым числом от 0 до 2^64−1.') from exc
        validate_id(movie_id)
        matches = [m for m in catalog if m['id'] == movie_id]
        if not matches:
            raise DemoError(f'Неизвестный ID фильма: {movie_id}. Посмотрите ID в movies.json.')
    else:
        title = query.casefold()
        matches = [m for m in catalog if m['title'].casefold() == title]
        if not matches:
            matches = [m for m in catalog if title in m['title'].casefold()]
        if not matches:
            raise DemoError('Фильм не найден. Введите другое название или ID.')
    if len(matches) > 1:
        raise DemoError('Найдено несколько фильмов. Уточните название: ' +
                        ', '.join(m['title'] for m in matches) + '.')
    return matches[0]


def validate_limit(limit):
    if type(limit) is not int or not 1 <= limit <= 249:
        raise DemoError('Количество рекомендаций должно быть целым числом от 1 до 249.')


def search(base, query, catalog, limit=5):
    validate_limit(limit)
    return recommend(base, resolve_movie(query, catalog)['id'], limit=limit)
