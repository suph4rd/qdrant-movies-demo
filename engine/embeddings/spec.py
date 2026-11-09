from dataclasses import asdict, dataclass

from engine.embeddings import constants as embedding_constants


@dataclass(frozen=True)
class EmbeddingSpec:
    model: str = 'intfloat/multilingual-e5-small'
    revision: str = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
    text_version: str = 'movie-en-v1'
    dimensions: int = embedding_constants.EMBEDDING_DIMENSIONS
    pooling: str = 'mean'
    dtype: str = 'float32'
    normalize: bool = True

    def metadata(self):
        return asdict(self)


SPEC = EmbeddingSpec()

