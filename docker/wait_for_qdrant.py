"""Wait for Qdrant readiness before running the separate catalog loader."""

import os
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


def wait_for_qdrant(url=None, timeout=60):
    if url is None:
        url = os.environ.get('QDRANT_URL', 'http://qdrant:6333').rstrip('/') + '/readyz'
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            with urlopen(url, timeout=min(2, remaining)) as response:
                if response.status == 200:
                    return True
        except (OSError, URLError):
            pass
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    return False


if __name__ == '__main__':
    if not wait_for_qdrant():
        print('Qdrant readiness timeout (60 s). / '
              'Время ожидания готовности Qdrant истекло (60 с).', file=sys.stderr)
        sys.exit(1)
