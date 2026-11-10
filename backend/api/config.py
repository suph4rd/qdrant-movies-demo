from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.api import constants as api_constants
from backend.engine import constants as engine_constants
from backend.engine.embeddings import constants as embedding_constants


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra='forbid')
    database_url: str = api_constants.DEFAULT_DATABASE_URL
    cookie_secure: bool = False
    qdrant_url: str = engine_constants.DEFAULT_URL
    movies_path: Path = engine_constants.DEFAULT_DATA_PATH
    embedding_url: str = engine_constants.DEFAULT_EMBEDDING_URL
    movies_collection: str = engine_constants.DEFAULT_COLLECTION
    embedding_cache: Path = embedding_constants.DEFAULT_CACHE_PATH
    kafka_bootstrap_servers: str = api_constants.DEFAULT_KAFKA_BOOTSTRAP_SERVERS
    kafka_search_topic: str = api_constants.DEFAULT_KAFKA_SEARCH_TOPIC
    kafka_search_group: str = api_constants.DEFAULT_KAFKA_SEARCH_GROUP
