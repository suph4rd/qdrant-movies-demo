from backend.engine.wikidata import validators


class EntityRepository:
    def __init__(self, transport):
        self.transport = transport

    async def candidates(self, title):
        candidates = {}
        for language in ('en', 'ru'):
            offset, seen = None, set()
            while True:
                params = {'action': 'wbsearchentities', 'search': title, 'language': language,
                          'uselang': language, 'type': 'item', 'limit': 50}
                if offset is not None:
                    params['continue'] = offset
                response = await self.transport.request(**params)
                results = response.get('search')
                if not isinstance(results, list):
                    raise validators.invalid()
                for candidate in results:
                    if not isinstance(candidate, dict) or not validators.valid_qid(candidate.get('id')):
                        raise validators.invalid()
                    candidates[candidate['id']] = None
                if 'search-continue' not in response:
                    break
                next_offset = response['search-continue']
                if (type(next_offset) is not int or next_offset <= 0
                        or next_offset in seen or (offset is not None and next_offset <= offset)):
                    raise validators.invalid()
                seen.add(next_offset)
                offset = next_offset
        return list(candidates)

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
