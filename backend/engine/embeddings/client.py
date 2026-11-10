import json

import httpx

from backend.engine import constants
from backend.engine import errors
from backend.engine.embeddings import spec as embedding_spec
from backend.engine.embeddings import texts as embedding_texts
from backend.engine.embeddings import validators as embedding_validators


class EmbeddingClient:
    def __init__(self, base_url=constants.DEFAULT_EMBEDDING_URL, client=None, spec=embedding_spec.SPEC):
        self.base_url = base_url.rstrip('/')
        self.spec = spec
        self.client = client if client is not None else httpx.AsyncClient(timeout=constants.REQUEST_TIMEOUT)
        self._owns_client = client is None

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def request(self, method, path, **kwargs):
        try:
            response = await self.client.request(method, self.base_url + path, timeout=constants.REQUEST_TIMEOUT, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            errors.annotate_error(exc, 'embedding_unavailable', url=self.base_url)
            raise
        except OSError as exc:
            errors.annotate_error(exc, 'embedding_unavailable', url=self.base_url)
            raise
        except json.JSONDecodeError as exc:
            errors.annotate_error(exc, 'embedding_response')
            raise

    async def check_model(self):
        info = await self.request('GET', '/info')
        if not isinstance(info, dict):
            raise errors.EmbeddingResponseError('embedding_response')
        if (info.get('model_id') != self.spec.model or info.get('model_sha') != self.spec.revision
                or info.get('model_dtype') != self.spec.dtype
                or info.get('model_type') != {'embedding': {'pooling': self.spec.pooling}}):
            raise errors.EmbeddingModelError('embedding_model')
        return info

    async def encode(self, texts):
        if not texts:
            return []
        await self.check_model()
        vectors = await self.request('POST', '/embed', json={
            'inputs': texts, 'normalize': self.spec.normalize, 'truncate': False})
        return embedding_validators.validate_vectors(vectors, len(texts), self.spec.dimensions)

    async def encode_documents(self, movies):
        return await self.encode([embedding_texts.document_text(movie) for movie in movies])

    async def encode_query(self, query):
        return (await self.encode([embedding_texts.query_text(query)]))[0]
