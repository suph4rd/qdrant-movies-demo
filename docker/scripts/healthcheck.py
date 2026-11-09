import sys

import httpx


def main():
    try:
        with httpx.Client(follow_redirects=True) as client:
            response = client.get('http://127.0.0.1:18000/', timeout=3)
            return 0 if response.status_code == 200 else 1
    except (httpx.RequestError, OSError):
        return 1


if __name__ == '__main__':
    sys.exit(main())
