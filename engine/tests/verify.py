import math
from unittest.mock import patch
from engine import DEFAULT_DATA_PATH, services as movies


def main():
    store = movies.QdrantMovieStore('http://127.0.0.1:6333')
    data = movies.read_movies(DEFAULT_DATA_PATH)
    assert store.request('POST', '/collections/movies/points/count', {'exact': True})['count'] == 250
    for movie_id in (1, 16, 21):
        for limit in (5, 10, 20, 50):
            results = store.recommend(movie_id, limit=limit)['recommendations']
            assert len(results) == limit and movie_id not in {p['id'] for p in results}
            source = next(m['vector'] for m in data if m['id'] == movie_id)
            def cosine(v):
                return sum(x*y for x,y in zip(source,v)) / math.sqrt(sum(x*x for x in source)*sum(x*x for x in v))
            scores = {m['id']: cosine(m['vector']) for m in data if m['id'] != movie_id}
            expected = sorted(scores.values(), reverse=True)[:limit]
            for point, score in zip(results, expected):
                assert abs(point['score'] - scores[point['id']]) < 1e-5
                assert abs(point['score'] - score) < 1e-5
    by_id = movies.search(store, '1', data)
    by_title = movies.search(store, '  мАтРиЦа  ', data)
    assert by_id == by_title
    assert len(by_id['recommendations']) == 5
    try:
        store.recommend(999)
    except movies.DemoError as exc:
        assert 'Неизвестный ID' in str(exc)
    else:
        raise AssertionError('Неизвестный ID принят')
    for vectors in ({'size': 3, 'distance': 'Cosine'}, {'size': 10, 'distance': 'Dot'}, {'named': {'size': 10, 'distance': 'Cosine'}}):
        with patch.object(store, 'request', side_effect=[{'collections': [{'name': 'movies'}]}, {'config': {'params': {'vectors': vectors}}}]) as api:
            try:
                store.load(DEFAULT_DATA_PATH)
            except movies.DemoError as exc:
                assert 'Несовместимая коллекция' in str(exc)
                assert all(c.args[0] == 'GET' for c in api.call_args_list)
            else:
                raise AssertionError('Несовместимая коллекция принята')
    print('OK: 250 записей, 5/10/20/50 результатов для трёх фильмов, cosine, исключение исходного ID, неизвестный ID, защита несовместимой коллекции.')


if __name__ == '__main__':
    main()
