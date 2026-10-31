"""Автономные проверки движка."""
import contextlib
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import URLError

from engine import DEFAULT_DATA_PATH, services


DATA = DEFAULT_DATA_PATH


class ServiceTests(unittest.TestCase):
    def setUp(self):
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
                with self.subTest(mutation=mutate), patch.object(services, 'request') as api:
                    with self.assertRaises(services.DemoError):
                        services.load('endpoint', path)
                    api.assert_not_called()

    def test_limits(self):
        for limit in (1, 5, 10, 20, 50, 249):
            with self.subTest(limit=limit), patch.object(services, 'request', side_effect=[
                [{'payload': self.catalog[0]}], {'points': []},
            ]) as api:
                services.search('endpoint', '1', self.catalog, limit=limit)
                body = api.call_args.args[3]
                self.assertEqual(body['limit'], limit)
                self.assertEqual(body['filter']['must_not'], [{'has_id': [1]}])
        for limit in (0, -1, 250, True, False, 5.0, '5', None):
            for function, args in ((services.recommend, ('endpoint', 1)),
                                   (services.search, ('endpoint', '1', self.catalog))):
                with self.subTest(limit=limit, function=function), patch.object(services, 'request') as api:
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

    def test_exact_precedes_partial_and_ambiguity(self):
        catalog = [{'id': 1, 'title': 'Фильм'}, {'id': 2, 'title': 'Фильм второй'}]
        self.assertEqual(services.resolve_movie('фильм', catalog)['id'], 1)
        with self.assertRaisesRegex(services.DemoError, 'Уточните'):
            services.resolve_movie('фил', catalog)

    def test_search_same_id_and_title_without_output(self):
        source = self.catalog[0]
        responses = [[{'payload': source}], {'points': []}] * 2
        with patch.object(services, 'request', side_effect=responses) as api:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                by_id = services.search('endpoint', '1', self.catalog)
                by_title = services.search('endpoint', 'Матрица', self.catalog)
            self.assertEqual(by_id, by_title)
            self.assertEqual(output.getvalue(), '')
            query = api.call_args_list[1].args[3]
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
                services, 'request', side_effect=[
                    {'collections': [{'name': 'movies'}]},
                    {'config': {'params': {'vectors': vectors}}},
                ],
            ) as api:
                with self.assertRaisesRegex(services.DemoError, 'Несовместимая'):
                    services.load('endpoint', DATA)
                self.assertTrue(all(call.args[1] == 'GET' for call in api.call_args_list))

    def test_load_result_and_no_stdout(self):
        with patch.object(services, 'request', side_effect=[
            {'collections': []}, {},
            {'config': {'params': {'vectors': {'size': 10, 'distance': 'Cosine'}}}},
            {}, {'count': 250},
        ]) as api, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(services.load('endpoint', DATA), {'loaded': 250, 'count': 250})
            self.assertEqual(len(api.call_args_list[3].args[3]['points']), 250)
            self.assertEqual(output.getvalue(), '')

    def test_network_failure(self):
        with patch.object(services, 'urlopen', side_effect=URLError('offline')):
            with self.assertRaisesRegex(services.DemoError, 'Нет соединения'):
                services.recommend('http://127.0.0.1:6333', 1)

    def test_invalid_id_does_not_call_api(self):
        with patch.object(services, 'request') as api:
            with self.assertRaises(services.DemoError):
                services.recommend('endpoint', -1)
            api.assert_not_called()


if __name__ == '__main__':
    unittest.main()
