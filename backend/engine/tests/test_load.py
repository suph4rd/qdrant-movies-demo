import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from backend.engine import catalog as movie_catalog
from backend.engine import constants
from backend.engine import errors as engine_errors
from backend.engine import load
from backend.engine.embeddings import constants as embedding_constants
from backend.engine.stores import factory
from backend.engine.stores import semantic
from backend.engine.tests import helpers


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            'QDRANT_URL':'http://127.0.0.1:6333', 'EMBEDDING_URL':'http://127.0.0.1:18080',
            'MOVIES_COLLECTION':'movies_semantic_v1', 'EMBEDDING_CACHE':str(embedding_constants.DEFAULT_CACHE_PATH)}))

    def run_loader(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with patch('sys.argv', ['backend.engine.load'] + arguments), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = load.main()
        return code, output.getvalue(), errors.getvalue()

    def test_success_and_default_path_from_other_directory(self):
        original = os.getcwd()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            semantic.SemanticMovieStore, 'load', return_value={'loaded': 250, 'count': 250}
        ) as loader:
            try:
                os.chdir(directory)
                code, output, errors = self.run_loader([])
                self.assertEqual(len(movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)), 250)
            finally:
                os.chdir(original)
        loader.assert_called_once_with(constants.DEFAULT_DATA_PATH)
        self.assertEqual(code, 0)
        self.assertEqual(output, 'Loaded 250 movies. Total in collection: 250.\n')
        self.assertEqual(errors, '')

    def test_connection_and_data_options(self):
        with patch.object(factory, 'create_store') as store_class:
            store_class.return_value.load = AsyncMock()
            store_class.return_value.close = AsyncMock()
            store_class.return_value.load.return_value = {'loaded': 250, 'count': 250}
            self.assertEqual(self.run_loader(['--url', 'http://test:6333', '--data', 'custom.json'])[0], 0)
        store_class.assert_called_once_with('http://test:6333', 'movies_semantic_v1', 'http://127.0.0.1:18080', embedding_constants.DEFAULT_CACHE_PATH)
        store_class.return_value.load.assert_called_once_with(Path('custom.json'))

    def test_errors(self):
        for error in (engine_errors.IndexStateError('response'), engine_errors.InputValidationError('id')):
            with self.subTest(error=error), patch.object(semantic.SemanticMovieStore, 'load', side_effect=error):
                code, output, errors = self.run_loader([])
                self.assertEqual(code, 1)
                self.assertEqual(output, '')
                self.assertIn('Error:', errors)
                self.assertIn(engine_errors.format_error(error), errors)

    def test_programming_errors_propagate(self):
        for error in (ValueError('bug'), KeyError('count'), TypeError('bug'), AttributeError('bug')):
            with self.subTest(error=error), patch.object(semantic.SemanticMovieStore, 'load', side_effect=error):
                with self.assertRaises(type(error)) as raised:
                    self.run_loader([])
                self.assertIs(raised.exception, error)

    def test_invalid_arguments(self):
        with patch.object(semantic.SemanticMovieStore, 'load') as loader:
            for arguments in (['recommend', '1'], ['--url'], ['--unknown']):
                with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as raised:
                    self.run_loader(arguments)
                self.assertEqual(raised.exception.code, 2)
            loader.assert_not_called()

    def test_module_entrypoint_exit_code(self):
        result = subprocess.run(
            [sys.executable, '-m', 'backend.engine.load', '--data', 'missing-catalog.json'],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('Error: Cannot read the movie catalog', result.stderr)
        self.assertEqual(result.stdout, '')


class LoaderResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_closes_store_on_success_and_failure(self):
        for error in (None, engine_errors.IndexStateError('response')):
            store = AsyncMock()
            store.load.side_effect = error
            with patch.object(factory, 'create_store', return_value=store):
                if error:
                    with helpers.expected_error(self):
                        await load.load_catalog('http://test', constants.DEFAULT_DATA_PATH)
                else:
                    await load.load_catalog('http://test', constants.DEFAULT_DATA_PATH)
            store.close.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
