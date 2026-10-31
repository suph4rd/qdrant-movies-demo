import contextlib
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import requests

from engine import DEFAULT_DATA_PATH, services


DATA = DEFAULT_DATA_PATH


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = services.QdrantMovieStore('http://test:6333/')
        self.catalog = services.read_movies(DATA)

    def test_catalog(self):
        self.assertEqual(len(self.catalog), 250)
        self.assertEqual({m['id'] for m in self.catalog}, set(range(1, 251)))
        self.assertEqual(len({(m['title'].casefold(), m['year']) for m in self.catalog}), 250)
        for movie in self.catalog:
            self.assertTrue(1888 <= movie['year'] <= 2026)
            self.assertTrue(movie['title'].strip())
            self.assertTrue(movie['description'].strip())
            self.assertTrue(all(g.strip() for g in movie['genres']))

    def test_invalid_catalog(self):
        mutations = (
            lambda data: data.pop(),
            lambda data: data[1].update(id=1),
            lambda data: data[0].update(title=''),
            lambda data: data[0].update(description=' '),
            lambda data: data[0].update(year='1999'),
            lambda data: data[0].update(genres=[]),
            lambda data: data[0].update(vector=[0] * 10),
            lambda data: data[0].update(vector=[1] * 9),
            lambda data: data[0].update(vector=[float('nan')] * 10),
            lambda data: data[0].update(vector=[1.1] * 10),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'movies.json'
            for mutate in mutations:
                data = json.loads(DATA.read_text())
                mutate(data)
                path.write_text(json.dumps(data))
                with self.subTest(mutation=mutate), patch.object(self.store, 'request') as api:
                    with self.assertRaises(services.DemoError):
                        self.store.load(path)
                    api.assert_not_called()

    def test_limits(self):
        for limit in (1, 5, 10, 20, 50, 249):
            with self.subTest(limit=limit), patch.object(self.store, 'request', side_effect=[
                [{'payload': self.catalog[0]}], {'points': []},
            ]) as api:
                services.search(self.store, '1', self.catalog, limit=limit)
                body = api.call_args.args[2]
                self.assertEqual(body['limit'], limit)
                self.assertEqual(body['filter']['must_not'], [{'has_id': [1]}])
        for limit in (0, -1, 250, True, False, 5.0, '5', None):
            for function, args in ((self.store.recommend, (1,)),
                                   (services.search, (self.store, '1', self.catalog))):
                with self.subTest(limit=limit, function=function), patch.object(self.store, 'request') as api:
                    with self.assertRaisesRegex(services.DemoError, 'Количество'):
                        function(*args, limit=limit)
                    api.assert_not_called()

    def test_resolve(self):
        for query in ('1', 'Матрица', '  мАтРиЦа  ', 'матри'):
            self.assertEqual(services.resolve_movie(query, self.catalog)['id'], 1)
        for query, message in (
            ('', 'Введите'), ('  ', 'Введите'), ('999', 'Неизвестный ID'),
            ('-1', 'ID должен'), (str(2**64), 'ID должен'),
            ('несуществующий фильм', 'не найден'), (' ', 'Введите'),
        ):
            with self.subTest(query=query), self.assertRaisesRegex(services.DemoError, message):
                services.resolve_movie(query, self.catalog)

    def test_numeric_title(self):
        for query in ('1917', ' 1917 ', '77'):
            with self.subTest(query=query):
                self.assertEqual(services.resolve_movie(query, self.catalog)['id'], 77)
        with patch.object(self.store, 'recommend', return_value={}) as recommend:
            services.search(self.store, '1917', self.catalog)
            recommend.assert_called_once_with(77, limit=5)

    def test_exact_precedes_partial_and_ambiguity(self):
        catalog = [{'id': 1, 'title': 'Фильм'}, {'id': 2, 'title': 'Фильм второй'}]
        self.assertEqual(services.resolve_movie('фильм', catalog)['id'], 1)
        with self.assertRaisesRegex(services.DemoError, 'Уточните'):
            services.resolve_movie('фил', catalog)

    def test_search_same_id_and_title_without_output(self):
        source = self.catalog[0]
        responses = [[{'payload': source}], {'points': []}] * 2
        with patch.object(self.store, 'request', side_effect=responses) as api:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                by_id = services.search(self.store, '1', self.catalog)
                by_title = services.search(self.store, 'Матрица', self.catalog)
            self.assertEqual(by_id, by_title)
            self.assertEqual(output.getvalue(), '')
            query = api.call_args_list[1].args[2]
            self.assertEqual(query['filter']['must_not'], [{'has_id': [1]}])
            self.assertEqual(query['limit'], 5)
            self.assertTrue(query['params']['exact'])

    def test_schema_rejected_before_writes(self):
        for vectors in (
            {'size': 3, 'distance': 'Cosine'}, {'size': 10, 'distance': 'Dot'},
            {'named': {'size': 10, 'distance': 'Cosine'}},
            {'size': 10, 'distance': 'Cosine', 'multivector_config': {'comparator': 'max_sim'}},
        ):
            with self.subTest(vectors=vectors), patch.object(
                self.store, 'request', side_effect=[
                    {'collections': [{'name': 'movies'}]},
                    {'config': {'params': {'vectors': vectors}}},
                ],
            ) as api:
                with self.assertRaisesRegex(services.DemoError, 'Несовместимая'):
                    self.store.load(DATA)
                self.assertTrue(all(call.args[0] == 'GET' for call in api.call_args_list))

    def test_load_result_and_no_stdout(self):
        with patch.object(self.store, 'request', side_effect=[
            {'collections': []}, {},
            {'config': {'params': {'vectors': {'size': 10, 'distance': 'Cosine'}}}},
            {}, {'count': 250},
        ]) as api, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(self.store.load(DATA), {'loaded': 250, 'count': 250})
            self.assertEqual(len(api.call_args_list[3].args[2]['points']), 250)
            self.assertEqual(output.getvalue(), '')

    def test_network_failure(self):
        for error in (requests.exceptions.ConnectionError('offline'),
                      requests.exceptions.ConnectTimeout('timed out'),
                      requests.exceptions.ReadTimeout('timed out')):
            with self.subTest(error=error), patch.object(
                services.requests, 'request', side_effect=error,
            ):
                with self.assertRaisesRegex(services.DemoError, 'Нет соединения'):
                    self.store.recommend(1)

    def test_http_error(self):
        response = requests.Response()
        response.status_code = 503
        response.encoding = 'utf-8'
        response._content = 'недоступно'.encode('utf-8')
        with patch.object(services.requests, 'request', return_value=response):
            with self.assertRaisesRegex(services.DemoError, 'Qdrant HTTP 503: недоступно'):
                self.store.recommend(1)

    def test_request_and_malformed_responses(self):
        for body in (b'invalid', b'{}', b'null', b'[]'):
            response = requests.Response()
            response.status_code = 200
            response._content = body
            with self.subTest(body=body), patch.object(
                services.requests, 'request', return_value=response,
            ):
                with self.assertRaisesRegex(services.DemoError, 'Некорректный ответ'):
                    self.store.request('GET', '/collections')
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"result": {}}'
        for method, body in (('POST', {'exact': True}), ('GET', None)):
            with self.subTest(method=method), patch.object(
                services.requests, 'request', return_value=response,
            ) as api:
                self.assertEqual(self.store.request(method, '/collections', body), {})
                api.assert_called_once_with(
                    method, 'http://test:6333/collections', json=body,
                    headers={'Content-Type': 'application/json'}, timeout=15)

    def test_unknown_id(self):
        with patch.object(self.store, 'request', return_value=[]) as api:
            with self.assertRaisesRegex(services.DemoError, 'Неизвестный ID'):
                self.store.recommend(999)
            api.assert_called_once()

    def test_invalid_id_does_not_call_api(self):
        with patch.object(self.store, 'request') as api:
            with self.assertRaises(services.DemoError):
                self.store.recommend(-1)
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
