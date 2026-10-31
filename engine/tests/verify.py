"""Интеграционная проверка текущей коллекции movies; данные не изменяет."""
import math
from unittest.mock import patch
from engine import DEFAULT_DATA_PATH, services as movies


def main():
    base = 'http://127.0.0.1:6333'
    data = movies.read_movies(DEFAULT_DATA_PATH)
    assert movies.request(base, 'POST', '/collections/movies/points/count', {'exact': True})['count'] == 30
    for movie_id in (1, 16, 21):
        results = movies.recommend(base, movie_id)['recommendations']
        assert len(results) == 5 and movie_id not in {p['id'] for p in results}
        source = next(m['vector'] for m in data if m['id'] == movie_id)
        def cosine(v):
            return sum(x*y for x,y in zip(source,v)) / math.sqrt(sum(x*x for x in source)*sum(x*x for x in v))
        scores = {m['id']: cosine(m['vector']) for m in data if m['id'] != movie_id}
        expected = sorted(scores.values(), reverse=True)[:5]
        for point, score in zip(results, expected):
            assert abs(point['score'] - scores[point['id']]) < 1e-5
            assert abs(point['score'] - score) < 1e-5
    by_id = movies.search(base, '1', data)
    by_title = movies.search(base, '  мАтРиЦа  ', data)
    assert by_id == by_title
    assert len(by_id['recommendations']) == 5
    try:
        movies.recommend(base, 999)
    except movies.DemoError as exc:
        assert 'Неизвестный ID' in str(exc)
    else:
        raise AssertionError('Неизвестный ID принят')
    for vectors in ({'size': 3, 'distance': 'Cosine'}, {'size': 10, 'distance': 'Dot'}, {'named': {'size': 10, 'distance': 'Cosine'}}):
        with patch.object(movies, 'request', side_effect=[{'collections': [{'name': 'movies'}]}, {'config': {'params': {'vectors': vectors}}}]) as api:
            try:
                movies.load(base, DEFAULT_DATA_PATH)
            except movies.DemoError as exc:
                assert 'Несовместимая коллекция' in str(exc)
                assert all(c.args[1] == 'GET' for c in api.call_args_list)
            else:
                raise AssertionError('Несовместимая коллекция принята')
    print('OK: 30 записей, три жанра, cosine, исключение исходного ID, неизвестный ID, защита несовместимой коллекции.')


if __name__ == '__main__':
    main()
