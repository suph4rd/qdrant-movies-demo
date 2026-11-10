import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend.api import config
from backend.engine import constants
from backend.engine.embeddings import constants as embedding_constants


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = config.Settings()
        self.assertEqual(settings.database_url, 'postgresql+psycopg://movies:movies@127.0.0.1:5432/movies')
        self.assertEqual(settings.kafka_bootstrap_servers, '127.0.0.1:19092')
        self.assertEqual(settings.kafka_search_topic, 'movie-search.requests.v1')
        self.assertEqual(settings.kafka_search_group, 'movie-search-workers-v1')
        self.assertFalse(settings.cookie_secure)
        self.assertEqual(settings.qdrant_url, constants.DEFAULT_URL)
        self.assertEqual(settings.movies_path, constants.DEFAULT_DATA_PATH)
        self.assertEqual(settings.embedding_url, constants.DEFAULT_EMBEDDING_URL)
        self.assertEqual(settings.movies_collection, constants.DEFAULT_COLLECTION)
        self.assertEqual(settings.embedding_cache, embedding_constants.DEFAULT_CACHE_PATH)

    def test_environment_overrides_and_unknown_settings(self):
        values = {'DATABASE_URL': 'postgresql+psycopg://custom/db',
                  'KAFKA_BOOTSTRAP_SERVERS': 'broker:9092', 'KAFKA_SEARCH_TOPIC': 'custom.topic',
                  'KAFKA_SEARCH_GROUP': 'custom-group', 'COOKIE_SECURE': 'true'}
        with patch.dict(os.environ, values, clear=True):
            settings = config.Settings()
            for key, value in values.items():
                self.assertEqual(getattr(settings, key.lower()), True if key == 'COOKIE_SECURE' else value)
            with self.assertRaises(ValidationError):
                config.Settings(unknown_setting='value')
