import json

import httpx

from backend.engine import constants
from backend.engine import errors
from backend.engine.wikidata import constants as wikidata_constants
from backend.engine.wikidata import validators


class WikidataTransport:
    def __init__(self, client=None):
        self.client = client if client is not None else httpx.AsyncClient(
            timeout=constants.REQUEST_TIMEOUT, follow_redirects=False)
        self._owns_client = client is None

    async def close(self):
        if self._owns_client:
            await self.client.aclose()

    async def request(self, **params):
        try:
            response = await self.client.get(
                wikidata_constants.API_URL, params={'format': 'json', 'maxlag': 5, **params},
                headers={'User-Agent': wikidata_constants.USER_AGENT, 'Accept': 'application/json'},
                timeout=constants.REQUEST_TIMEOUT)
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPStatusError as exc:
            errors.annotate_error(exc, 'wikidata_rate_limit' if exc.response.status_code == 429
                                  else 'wikidata_unavailable')
            raise
        except httpx.RequestError as exc:
            errors.annotate_error(exc, 'wikidata_unavailable')
            raise
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            errors.annotate_error(exc, 'wikidata_invalid')
            raise
        if not isinstance(result, dict):
            raise validators.invalid()
        if 'error' in result:
            error = result['error']
            if not isinstance(error, dict):
                raise validators.invalid()
            code = error.get('code')
            if code in ('maxlag', 'ratelimited'):
                raise errors.IndexStateError('wikidata_rate_limit')
            if code in ('readonly', 'internal_api_error_DBConnectionError'):
                raise errors.IndexStateError('wikidata_unavailable')
            raise validators.invalid()
        return result
