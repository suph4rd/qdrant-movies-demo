"""Check HTTP availability of the web home page."""

import sys
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def main():
    try:
        with urlopen('http://127.0.0.1:5000/', timeout=3) as response:
            return 0 if response.status == 200 else 1
    except HTTPError as error:
        error.close()
        return 1
    except (OSError, URLError):
        return 1


if __name__ == '__main__':
    sys.exit(main())
