from engine import constants
from engine.embeddings import constants as embedding_constants
from engine.stores import semantic


def create_store(base_url, collection_name=constants.DEFAULT_COLLECTION,
                 embedding_url=constants.DEFAULT_EMBEDDING_URL, cache_path=None):
    return semantic.SemanticMovieStore(
        base_url, collection_name=collection_name, embedding_url=embedding_url,
        cache_path=cache_path if cache_path is not None else embedding_constants.DEFAULT_CACHE_PATH)
