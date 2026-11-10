from backend.engine import errors
from backend.engine.wikidata import validators


class EntityRepository:
    def __init__(self, transport):
        self.transport = transport

    async def candidates(self, title):
        candidates, failures = {}, []
        for language in ('en', 'ru'):
            try:
                response = await self.transport.request(
                    action='wbsearchentities', search=title, language=language,
                    uselang=language, type='item', limit=50)
                results = response.get('search')
                if not isinstance(results, list):
                    raise validators.invalid()
                for candidate in results[:50]:
                    if not isinstance(candidate, dict) or not validators.valid_qid(candidate.get('id')):
                        raise validators.invalid()
                    candidates[candidate['id']] = None
            except Exception as exc:
                if not errors.is_expected_error(exc):
                    raise
                failures.append(exc)
        if failures and not candidates:
            raise failures[0]
        return CandidateList(candidates, failures)

    async def wikipedia_candidates(self, title):
        candidates = {}
        failures = []
        for language in ('en', 'ru'):
            try:
                response = await self.transport.request(
                    _endpoint=f'https://{language}.wikipedia.org/w/api.php',
                    action='query', generator='search', gsrsearch=title, gsrlimit=50,
                    gsrnamespace=0, prop='pageprops', ppprop='wikibase_item')
                query = response.get('query', {})
                if not isinstance(query, dict):
                    raise validators.invalid()
                pages = query.get('pages', {})
                if not isinstance(pages, dict):
                    raise validators.invalid()
                for page in list(pages.values())[:50]:
                    if not isinstance(page, dict):
                        raise validators.invalid()
                    properties = page.get('pageprops', {})
                    if not isinstance(properties, dict):
                        raise validators.invalid()
                    qid = properties.get('wikibase_item')
                    if qid is not None:
                        if not validators.valid_qid(qid):
                            raise validators.invalid()
                        candidates[qid] = None
            except Exception as exc:
                if not errors.is_expected_error(exc):
                    raise
                failures.append(exc)
        return list(candidates), failures

    async def entities(self, qids, cache):
        missing = list(dict.fromkeys(qid for qid in qids if qid not in cache))
        for start in range(0, len(missing), 50):
            batch = missing[start:start + 50]
            if not all(validators.valid_qid(qid) for qid in batch):
                raise validators.invalid()
            response = await self.transport.request(action='wbgetentities', ids='|'.join(batch),
                                                    props='labels|descriptions|aliases|claims', languages='en|ru|mul')
            entities = response.get('entities')
            if not isinstance(entities, dict):
                raise validators.invalid()
            for qid in batch:
                entity = entities.get(qid)
                if (not isinstance(entity, dict) or entity.get('id') != qid
                        or 'missing' in entity or entity.get('type') != 'item'):
                    raise validators.invalid()
                cache[qid] = entity
        return [cache[qid] for qid in qids]


class CandidateList(list):
    def __init__(self, candidates, failures):
        super().__init__(candidates)
        self.failures = failures
