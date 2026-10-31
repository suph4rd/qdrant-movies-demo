#!/usr/bin/env python3
"""Учебные рекомендации через REST Qdrant; только стандартная библиотека."""
import argparse
import json
import math
from pathlib import Path
import sys
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
    except HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise DemoError(f'Qdrant HTTP {exc.code}: {detail}') from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DemoError(f'Нет соединения с Qdrant ({base}): {exc}') from exc


def read_movies(path):
    movies = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(movies, list) or len(movies) != 30:
        raise DemoError('В JSON должно быть ровно 30 фильмов.')
    ids = set()
    for m in movies:
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
    print(f'Загружено {len(points)} фильмов. Всего в movies: {count}.')
    if count != 30:
        raise DemoError('В movies есть дополнительные записи; они сохранены. Для демо ожидается 30.')


def recommend(base, movie_id):
    points = request(base, 'POST', '/collections/movies/points', {'ids': [movie_id], 'with_payload': True})
    if not points:
        raise DemoError(f'Неизвестный ID фильма: {movie_id}. Посмотрите ID в movies.json.')
    result = request(base, 'POST', '/collections/movies/points/query', {
        'query': movie_id, 'filter': {'must_not': [{'has_id': [movie_id]}]},
        'limit': 5, 'with_payload': True, 'params': {'exact': True}})['points']
    print(f'Похожие на «{points[0]["payload"]["title"]}» (ID {movie_id}):')
    for p in result:
        print(f'{p["id"]:2d}  {p["payload"]["title"]} ({p["payload"]["year"]}) — {p["score"]:.4f}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:6333', help='REST URL Qdrant')
    sub = parser.add_subparsers(dest='command', required=True)
    loader = sub.add_parser('load', help='Проверить JSON и загрузить 30 фильмов')
    loader.add_argument('--data', type=Path, default=Path(__file__).with_name('movies.json'))
    rec = sub.add_parser('recommend', help='Найти пять похожих фильмов')
    rec.add_argument('id', type=int)
    args = parser.parse_args()
    try:
        if args.command == 'load':
            load(args.url, args.data)
        else:
            if not 0 <= args.id < 2**64:
                raise DemoError('ID должен быть целым числом от 0 до 2^64−1.')
            recommend(args.url, args.id)
    except (DemoError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
