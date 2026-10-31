"""Движок каталога и рекомендаций без сторонних зависимостей."""
from pathlib import Path


DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / 'movies.json'
