from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from pydantic import ValidationError
import httpx

from engine.catalog import read_movies
from engine.errors import DemoError
from engine.validators import validate_id, validate_limit


class QdrantMovieStore:
    def __init__(self, base_url, client=None):
        self.base_url = base_url
        self.client = client if client is not None else AsyncQdrantClient(
            url=base_url, prefer_grpc=False, timeout=15, check_compatibility=False)
        self._owns_client = client is None

    async def close(self):
        if self._owns_client:
            await self.client.close()

    async def request(self, method, **kwargs):
        try:
            return await getattr(self.client, method)(**kwargs)
        except UnexpectedResponse as exc:
            raise DemoError('http', status=exc.status_code,
                            detail=exc.content.decode('utf-8', errors='replace')) from exc
        except (ValidationError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise DemoError('response') from exc
        except ResponseHandlingException as exc:
            if isinstance(exc.source, (ValidationError, ValueError, KeyError, TypeError)):
                raise DemoError('response') from exc
            raise DemoError('connection', url=self.base_url, detail=exc) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise DemoError('connection', url=self.base_url, detail=exc) from exc

    async def load(self, path):
        movies = read_movies(path)
        collections = (await self.request('get_collections')).collections
        if not any(c.name == 'movies' for c in collections):
            await self.request('create_collection', collection_name='movies',
                               vectors_config=models.VectorParams(size=10, distance=models.Distance.COSINE))
        info = await self.request('get_collection', collection_name='movies')
        vectors = info.config.params.vectors
        if (not isinstance(vectors, models.VectorParams) or vectors.size != 10
                or vectors.distance != models.Distance.COSINE or vectors.multivector_config is not None):
            raise DemoError('schema')
        points = [models.PointStruct(id=m['id'], vector=m['vector'],
                  payload={k: v for k, v in m.items() if k != 'vector'}) for m in movies]
        await self.request('upsert', collection_name='movies', points=points, wait=True)
        count = (await self.request('count', collection_name='movies', exact=True)).count
        if count != 250:
            raise DemoError('count')
        return {'loaded': len(points), 'count': count}

    async def recommend(self, movie_id, limit=5):
        validate_limit(limit)
        validate_id(movie_id)
        points = await self.request('retrieve', collection_name='movies', ids=[movie_id], with_payload=True)
        if not points:
            raise DemoError('unknown_id', id=movie_id)
        result = await self.request('query_points', collection_name='movies', query=movie_id,
            query_filter=models.Filter(must_not=[models.HasIdCondition(has_id=[movie_id])]),
            limit=limit, with_payload=True, search_params=models.SearchParams(exact=True))
        return {'source': points[0].payload,
                'recommendations': [{'id': p.id, 'score': p.score, 'payload': p.payload} for p in result.points]}
