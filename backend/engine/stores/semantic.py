import asyncio
import hashlib
import json
import uuid

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from pydantic import ValidationError
import httpx

from backend.engine import catalog as movie_catalog
from backend.engine import constants
from backend.engine import errors
from backend.engine import imports
from backend.engine import validators
from backend.engine.embeddings import cache as embedding_cache
from backend.engine.embeddings import client as embedding_client
from backend.engine.embeddings import constants as embedding_constants
from backend.engine.embeddings import spec as embedding_spec
from backend.engine.embeddings import texts as embedding_texts
from backend.engine.embeddings import validators as embedding_validators


VECTOR_NAME = 'semantic'


class SemanticMovieStore:
    def __init__(self, base_url, client=None, embeddings=None, embedding_url=constants.DEFAULT_EMBEDDING_URL,
                 collection_name=constants.DEFAULT_COLLECTION, cache_path=embedding_constants.DEFAULT_CACHE_PATH):
        if not collection_name or collection_name == 'movies':
            raise errors.SemanticSchemaError('semantic_schema')
        if embeddings is not None and embeddings.spec != embedding_spec.SPEC:
            raise errors.EmbeddingModelError('embedding_model')
        self.base_url = base_url
        self.client = client if client is not None else AsyncQdrantClient(
            url=base_url, prefer_grpc=False, timeout=constants.REQUEST_TIMEOUT, check_compatibility=False)
        self._owns_client = client is None

        self.collection_name = collection_name
        self.embeddings = embeddings if embeddings is not None else embedding_client.EmbeddingClient(embedding_url)
        self._owns_embeddings = embeddings is None
        self.spec = self.embeddings.spec
        self.cache = embedding_cache.EmbeddingCache(cache_path, self.spec)
        self._import_lock = asyncio.Lock()

    async def close(self):
        try:
            if self._owns_embeddings:
                await self.embeddings.close()
        finally:
            if self._owns_client:
                await self.client.close()

    async def request(self, method, **kwargs):
        try:
            return await getattr(self.client, method)(**kwargs)
        except UnexpectedResponse as exc:
            errors.annotate_error(exc, 'http', status=exc.status_code,
                                  detail=exc.content.decode('utf-8', errors='replace'))
            raise
        except ResponseHandlingException as exc:
            if isinstance(exc.source, (ValidationError, json.JSONDecodeError)):
                errors.annotate_error(exc, 'response')
                raise
            if isinstance(exc.source, (httpx.HTTPError, OSError)):
                errors.annotate_error(exc, 'connection', url=self.base_url, detail=exc)
                raise
            raise
        except httpx.HTTPError as exc:
            errors.annotate_error(exc, 'connection', url=self.base_url, detail=exc)
            raise
        except OSError as exc:
            errors.annotate_error(exc, 'connection', url=self.base_url, detail=exc)
            raise

    async def count_movies(self):
        result = await self.request('count', collection_name=self.collection_name, exact=True)
        return result.count

    async def check_index(self):
        try:
            info = await self.request('get_collection', collection_name=self.collection_name)
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                raise errors.SemanticSchemaError('semantic_schema') from exc
            raise
        vectors = info.config.params.vectors
        if (not isinstance(vectors, dict) or set(vectors) != {VECTOR_NAME}
                or not isinstance(vectors[VECTOR_NAME], models.VectorParams)
                or vectors[VECTOR_NAME].size != self.spec.dimensions
                or vectors[VECTOR_NAME].distance != models.Distance.COSINE
                or vectors[VECTOR_NAME].multivector_config is not None
                or info.config.params.sparse_vectors):
            raise errors.SemanticSchemaError('semantic_schema')
        if (info.config.metadata or {}).get('embedding') != self.spec.metadata():
            raise errors.SemanticSchemaError('semantic_schema')

    async def load(self, path):
        movies = movie_catalog.read_movies(path)
        exists = any(c.name == self.collection_name for c in
                     (await self.request('get_collections')).collections)
        if exists:
            await self.check_index()
        texts = [embedding_texts.document_text(movie) for movie in movies]
        vectors = [self.cache.get(text) for text in texts]
        missing = [i for i, vector in enumerate(vectors) if vector is None]
        for start in range(0, len(missing), embedding_constants.DOCUMENT_BATCH_SIZE):
            indices = missing[start:start + embedding_constants.DOCUMENT_BATCH_SIZE]
            batch = await self.embeddings.encode_documents([movies[i] for i in indices])
            embedding_validators.validate_vectors(batch, len(indices), self.spec.dimensions)
            for i, vector in zip(indices, batch):
                vectors[i] = vector
                self.cache.put(texts[i], vector)
        embedding_validators.validate_vectors(vectors, len(movies), self.spec.dimensions)
        points = [models.PointStruct(
            id=movie['id'], vector={VECTOR_NAME: vector},
            payload={**{k: v for k, v in movie.items() if k != 'vector'},
                     '_embedding': {**self.spec.metadata(),
                                    'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}})
                  for movie, text, vector in zip(movies, texts, vectors)]
        # No Qdrant writes until the complete dataset is available and valid.
        if not exists:
            await self.request('create_collection', collection_name=self.collection_name,
                               vectors_config={VECTOR_NAME: models.VectorParams(
                                   size=self.spec.dimensions, distance=models.Distance.COSINE)},
                               metadata={'embedding': self.spec.metadata()})
        await self.check_index()
        await self.request('upsert', collection_name=self.collection_name, points=points, wait=True)
        count = (await self.request('count', collection_name=self.collection_name, exact=True)).count
        records = await self.request('retrieve', collection_name=self.collection_name,
                                     ids=[movie['id'] for movie in movies], with_payload=False)
        if count < len(movies) or {record.id for record in records} != {m['id'] for m in movies}:
            raise errors.CollectionCountError('count')
        return {'loaded': len(points), 'count': count}

    async def find_movies(self, title, year=None):
        await self.check_index()
        matches = []
        offset = None
        seen_offsets = set()
        while True:
            records, next_offset = await self.request(
                'scroll', collection_name=self.collection_name, offset=offset,
                limit=256, with_payload=True, with_vectors=False)
            for record in records:
                payload = record.payload or {}
                if year is None or payload.get('year') == year:
                    matches.append({**payload, 'id': record.id})
            if next_offset is None:
                return imports.select_similar(matches, title, year)
            if next_offset in seen_offsets:
                raise errors.IndexStateError('response')
            seen_offsets.add(next_offset)
            offset = next_offset

    async def import_movie(self, movie, catalog):
        imports.validate_movie(movie)
        for original in catalog:
            if original['year'] == movie['year'] and imports.titles(original) & imports.titles(movie):
                return {'movie': original, 'created': False}
        async with self._import_lock:
            await self.check_index()
            records = await self.request('retrieve', collection_name=self.collection_name,
                                         ids=[movie['id']], with_payload=True)
            if records:
                return {'movie': self._owned_import(records[0], movie), 'created': False}
            if movie['source'] == 'wikidata' and 'tmdb_id' in movie:
                legacy_id = imports.TMDB_ID_BASE + movie['tmdb_id']
                legacy_records = await self.request('retrieve', collection_name=self.collection_name,
                                                    ids=[legacy_id], with_payload=True)
                if legacy_records:
                    legacy = {'id': legacy_id, 'source': 'tmdb', 'tmdb_id': movie['tmdb_id']}
                    return {'movie': self._owned_import(legacy_records[0], legacy), 'created': False}
            batch = await self.embeddings.encode_documents([movie])
            embedding_validators.validate_vectors(batch, 1, self.spec.dimensions)
            text = embedding_texts.document_text(movie)
            operation_id = uuid.uuid4().hex
            payload = {**movie, '_import_operation': operation_id,
                       '_embedding': {**self.spec.metadata(),
                                      'text_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}}
            # Insert-only is atomic in Qdrant, including between application processes.
            await self.request('upsert', collection_name=self.collection_name,
                               points=[models.PointStruct(id=movie['id'],
                                   vector={VECTOR_NAME: batch[0]}, payload=payload)],
                               wait=True, ordering=models.WriteOrdering.STRONG,
                               update_mode=models.UpdateMode.INSERT_ONLY)
            records = await self.request('retrieve', collection_name=self.collection_name,
                                         ids=[movie['id']], with_payload=True)
            if not records:
                raise errors.IndexStateError('response')
            saved = self._owned_import(records[0], movie)
            return {'movie': saved, 'created': saved.get('_import_operation') == operation_id}

    @staticmethod
    def _owned_import(record, movie):
        payload = record.payload or {}
        source = movie['source']
        external_key = 'wikidata_id' if source == 'wikidata' else 'tmdb_id'
        if (record.id != movie['id'] or payload.get('source') != source
                or payload.get(external_key) != movie[external_key]
                or type(payload.get(external_key)) is not type(movie[external_key])
                or payload.get('id') != movie['id']):
            raise errors.IndexStateError('import_conflict', id=movie['id'])
        imports.validate_movie(payload)
        return payload

    async def recommend(self, movie_id, limit=constants.DEFAULT_LIMIT, exclude_ids=None):
        validators.validate_limit(limit)
        validators.validate_id(movie_id)
        await self.check_index()
        points = await self.request('retrieve', collection_name=self.collection_name,
                                    ids=[movie_id], with_payload=True)
        if not points:
            raise errors.MovieNotFoundError('unknown_id', id=movie_id)
        excluded = sorted(set([movie_id, *(exclude_ids or [])]))
        for excluded_id in excluded:
            validators.validate_id(excluded_id)
        result = await self.request(
            'query_points', collection_name=self.collection_name, query=movie_id, using=VECTOR_NAME,
            query_filter=models.Filter(must_not=[models.HasIdCondition(has_id=excluded)]),
            limit=limit, with_payload=True, search_params=models.SearchParams(exact=True,
                quantization=models.QuantizationSearchParams(ignore=True)))
        return {'source': points[0].payload, 'recommendations': self.results(result)}

    async def semantic_search(self, query, limit=constants.DEFAULT_LIMIT):
        validators.validate_limit(limit)
        embedding_texts.query_text(query)
        await self.check_index()
        vector = await self.embeddings.encode_query(query)
        embedding_validators.validate_vectors([vector], 1, self.spec.dimensions)
        result = await self.request(
            'query_points', collection_name=self.collection_name, query=vector, using=VECTOR_NAME,
            limit=limit, with_payload=True, search_params=models.SearchParams(exact=True,
                quantization=models.QuantizationSearchParams(ignore=True)))
        return {'source': None, 'recommendations': self.results(result)}

    @staticmethod
    def results(result):
        return [{'id': point.id, 'score': point.score, 'payload': point.payload}
                for point in result.points]
