import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from engine import DEFAULT_DATA_PATH, load, services


class LoaderTests(unittest.TestCase):
    def run_loader(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['engine.load'] + arguments), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = load.main()
        return code, output.getvalue(), errors.getvalue()

    def test_success_and_default_path_from_other_directory(self):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            services.QdrantMovieStore, 'load', return_value={'loaded': 250, 'count': 250}
        ) as loader:
            try:
                os.chdir(directory)
                code, output, errors = self.run_loader([])
                self.assertEqual(len(services.read_movies(DEFAULT_DATA_PATH)), 250)
            finally:
                os.chdir(original)
        loader.assert_called_once_with(DEFAULT_DATA_PATH)
        self.assertEqual(code, 0)
        self.assertEqual(output, 'Загружено 250 фильмов. Всего в movies: 250.\n')
        self.assertEqual(errors, '')

    def test_connection_and_data_options(self):
        with patch.object(services, 'QdrantMovieStore') as store_class:
            store_class.return_value.load.return_value = {'loaded': 250, 'count': 250}
            self.assertEqual(self.run_loader(['--url', 'http://test:6333', '--data', 'custom.json'])[0], 0)
        store_class.assert_called_once_with('http://test:6333')
        store_class.return_value.load.assert_called_once_with(Path('custom.json'))

    def test_errors(self):
        for error in (services.DemoError('Нет соединения'), ValueError('данные'), OSError('файл'), KeyError('count'), TypeError('ответ')):
            with self.subTest(error=error), patch.object(services.QdrantMovieStore, 'load', side_effect=error):
                code, output, errors = self.run_loader([])
                self.assertEqual(code, 1)
                self.assertEqual(output, '')
                self.assertIn('Ошибка:', errors)
                self.assertIn(str(error), errors)

    def test_invalid_arguments(self):
        with patch.object(services.QdrantMovieStore, 'load') as loader:
            for arguments in (['recommend', '1'], ['--url'], ['--unknown']):
                with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as raised:
                    self.run_loader(arguments)
                self.assertEqual(raised.exception.code, 2)
            loader.assert_not_called()

    def test_module_entrypoint_exit_code(self):
        result = subprocess.run(
            [sys.executable, '-m', 'engine.load', '--data', 'missing-catalog.json'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('Ошибка: Не удалось прочитать каталог', result.stderr)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
