import json
import math
import time

import httpx

from engine import constants
from engine.embeddings import spec as embedding_spec
from engine.embeddings import validators as embedding_validators
from evaluation.config import paths
from evaluation.config import settings


def main():
    with httpx.Client(base_url=settings.store_settings()['embedding_url'], timeout=constants.REQUEST_TIMEOUT) as client:
        response = client.get('/info')
        response.raise_for_status()
        info = response.json()
        assert info['model_id'] == embedding_spec.SPEC.model and info['model_sha'] == embedding_spec.SPEC.revision
        inputs = ['query: An astronaut survives on Mars.',
                  'query: Космонавт выживает на Марсе.']
        start = time.perf_counter()
        response = client.post('/embed', json={'inputs': inputs, 'normalize': True, 'truncate': False})
        response.raise_for_status()
        elapsed = time.perf_counter() - start
        vectors = response.json()
        embedding_validators.validate_vectors(vectors, len(inputs), embedding_spec.SPEC.dimensions)
        for vector in vectors:
            assert len(vector) == embedding_spec.SPEC.dimensions
            assert all(math.isfinite(x) for x in vector)
            assert abs(math.sqrt(sum(x*x for x in vector)) - 1) < 1e-5
        result = {'info': info, 'inputs': inputs, 'dimensions': [len(v) for v in vectors],
                  'batch_seconds': elapsed,
                  'cross_language_cosine': sum(x*y for x,y in zip(*vectors))}
        (paths.RESULTS_PATH / 'probe-latest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
