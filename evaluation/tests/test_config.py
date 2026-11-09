import importlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import constants
from evaluation.config import paths
from evaluation.config import settings


class EvaluationConfigTests(unittest.TestCase):
    def test_paths_and_imports_are_independent_of_working_directory(self):
        original = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                with patch('httpx.Client', side_effect=AssertionError('network client')), patch(
                        'engine.stores.semantic.AsyncQdrantClient',
                        side_effect=AssertionError('network client')):
                    importlib.import_module('evaluation.runners.probe')
                    importlib.import_module('evaluation.runners.run')
                self.assertTrue(paths.PACKAGE_PATH.is_absolute())
                self.assertEqual(len(json.loads((paths.DATA_PATH / 'queries.json').read_text())['queries']), 20)
                self.assertTrue((paths.DATA_PATH / 'legacy.json').is_file())
                self.assertTrue((paths.RESULTS_PATH / 'probe.json').is_file())
        finally:
            os.chdir(original)

    def test_engine_defaults_and_environment(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(settings.store_settings(), {
                'base_url': constants.DEFAULT_URL, 'embedding_url': constants.DEFAULT_EMBEDDING_URL,
                'collection_name': constants.DEFAULT_COLLECTION,
            })
        with patch.dict(os.environ, {'QDRANT_URL': 'http://qdrant', 'EMBEDDING_URL': 'http://tei',
                                     'MOVIES_COLLECTION': 'custom'}):
            self.assertEqual(settings.store_settings(), {
                'base_url': 'http://qdrant', 'embedding_url': 'http://tei',
                'collection_name': 'custom',
            })
