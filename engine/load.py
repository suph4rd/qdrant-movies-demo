#!/usr/bin/env python3
"""Проверка каталога и загрузка 30 фильмов через REST Qdrant."""
import argparse
from pathlib import Path
import sys

from engine import DEFAULT_DATA_PATH, services
from engine.services import DemoError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:6333', help='REST URL Qdrant')
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA_PATH,
                        help='Путь к JSON с 30 фильмами')
    args = parser.parse_args()
    try:
        result = services.load(args.url, args.data)
        print(f'Загружено {result["loaded"]} фильмов. Всего в movies: {result["count"]}.')
    except (DemoError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f'Ошибка: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
