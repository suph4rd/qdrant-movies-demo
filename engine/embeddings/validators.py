import math

from engine import errors
from engine.embeddings import constants as embedding_constants


def validate_vectors(vectors, count, dimensions=embedding_constants.EMBEDDING_DIMENSIONS):
    if not isinstance(vectors, list) or len(vectors) != count:
        raise errors.EmbeddingResponseError('embedding_response')
    for vector in vectors:
        if (not isinstance(vector, list) or len(vector) != dimensions
                or not all(type(x) in (int, float) and math.isfinite(x) for x in vector)
                or not any(vector)):
            raise errors.EmbeddingResponseError('embedding_response')
        try:
            norm = math.hypot(*vector)
        except OverflowError as exc:
            raise errors.EmbeddingResponseError('embedding_response') from exc
        if not math.isfinite(norm) or norm == 0:
            raise errors.EmbeddingResponseError('embedding_response')
    return vectors

