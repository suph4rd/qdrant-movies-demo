from pathlib import Path



DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[3] / '.cache' / 'embeddings'
EMBEDDING_DIMENSIONS = 384
DOCUMENT_BATCH_SIZE = 32
