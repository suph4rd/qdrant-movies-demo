from engine.errors import metadata


class DomainError(Exception):
    def __init__(self, key, **params):
        super().__init__(key)
        metadata.annotate_error(self, key, **params)


class CatalogValidationError(DomainError, ValueError):
    pass


class InputValidationError(DomainError, ValueError):
    pass


class EmbeddingResponseError(DomainError, ValueError):
    pass


class EmbeddingModelError(DomainError, ValueError):
    pass


class MovieLookupError(DomainError, LookupError):
    pass


class MovieNotFoundError(MovieLookupError):
    pass


class AmbiguousMovieError(MovieLookupError):
    pass


class IndexStateError(DomainError, RuntimeError):
    pass


class SemanticSchemaError(IndexStateError):
    pass


class CollectionCountError(IndexStateError):
    pass
