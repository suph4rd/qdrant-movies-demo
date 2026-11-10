from pathlib import Path



DEFAULT_URL = 'http://127.0.0.1:6333'
DEFAULT_EMBEDDING_URL = 'http://127.0.0.1:18080'
DEFAULT_COLLECTION = 'movies_semantic_v1'
DEFAULT_DATA_PATH = Path(__file__).resolve().parents[1] / 'api' / 'movies.json'
DEFAULT_LIMIT = 5
MOVIE_COUNT = 250
VECTOR_DIMENSIONS = 10
REQUEST_TIMEOUT = 15
