from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.engine import constants
from backend.engine.embeddings import constants as embedding_constants


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra='forbid')
    database_url: str = 'postgresql+psycopg://movies:movies@127.0.0.1:5432/movies'
    cookie_secure: bool = False
    qdrant_url: str = constants.DEFAULT_URL
    movies_path: Path = constants.DEFAULT_DATA_PATH
    embedding_url: str = constants.DEFAULT_EMBEDDING_URL
    movies_collection: str = constants.DEFAULT_COLLECTION
    embedding_cache: Path = embedding_constants.DEFAULT_CACHE_PATH


