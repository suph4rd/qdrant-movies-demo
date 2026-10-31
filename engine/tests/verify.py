import math
from unittest.mock import patch
from markupsafe import escape
from engine import DEFAULT_DATA_PATH, services as movies
from engine.i18n import localize_movie
from web.app import create_app


def main():
    store = movies.QdrantMovieStore('http://127.0.0.1:6333')
    data = movies.read_movies(DEFAULT_DATA_PATH)
    for _ in range(2):
        assert store.load(DEFAULT_DATA_PATH) == {'loaded': 250, 'count': 250}
        assert store.request('POST', '/collections/movies/points/count', {'exact': True})['count'] == 250
    payload = store.request('POST', '/collections/movies/points', {'ids': [1], 'with_payload': True})[0]['payload']
    assert payload['translations'] == data[0]['translations']
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
    assert by_id == by_title == movies.search(store, 'The Matrix', data)
    assert len(by_id['recommendations']) == 5
    try:
        store.recommend(999)
    except movies.DemoError as exc:
        assert exc.key == 'unknown_id'
    else:
        raise AssertionError('Unknown ID accepted')
    for vectors in ({'size': 3, 'distance': 'Cosine'}, {'size': 10, 'distance': 'Dot'}, {'named': {'size': 10, 'distance': 'Cosine'}}):
        with patch.object(store, 'request', side_effect=[{'collections': [{'name': 'movies'}]}, {'config': {'params': {'vectors': vectors}}}]) as api:
            try:
                store.load(DEFAULT_DATA_PATH)
            except movies.DemoError as exc:
                assert exc.key == 'schema'
                assert all(c.args[0] == 'GET' for c in api.call_args_list)
            else:
                raise AssertionError('Incompatible collection accepted')
    legacy = {'source': {k: v for k, v in by_id['source'].items() if k != 'translations'},
              'recommendations': [{**p, 'payload': {k: v for k, v in p['payload'].items() if k != 'translations'}}
                                  for p in by_id['recommendations']]}
    app = create_app({'TESTING': True})
    app.extensions['movie_store'] = store
    for lang in ('en', 'ru'):
        with patch.object(store, 'recommend', return_value=legacy):
            page = app.test_client().get('/', query_string={'q': 'The Matrix', 'lang': lang}).text
        assert localize_movie(data[0], lang)['title'] in page
        assert page.count('<article>') == 5
        for point in legacy['recommendations']:
            movie = next(m for m in data if m['id'] == point['id'])
            assert str(escape(localize_movie(movie, lang)['title'])) in page
    print('OK: two loads retain 250 records; translations, 5/10/20/50 results, cosine ranking, source exclusion, unknown IDs, schema protection, and legacy payload localization.')


if __name__ == '__main__':
    main()
