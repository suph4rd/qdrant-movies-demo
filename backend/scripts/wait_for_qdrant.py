import os
import sys
import time

import httpx


def wait_for_qdrant(url=None, timeout=60):
    if url is None:
        url = os.environ.get('QDRANT_URL', 'http://qdrant:6333').rstrip('/') + '/readyz'
    deadline = time.monotonic() + timeout
    with httpx.Client(follow_redirects=True) as client:
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                response = client.get(url, timeout=min(2, remaining))
                if response.status_code == 200:
                    return True
            except (httpx.RequestError, OSError):
                pass
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    return False


if __name__ == '__main__':
    if not wait_for_qdrant():
        print('Qdrant readiness timeout (60 s). / '
              'Время ожидания готовности Qdrant истекло (60 с).', file=sys.stderr)
        sys.exit(1)
