#!/usr/bin/env python3
import asyncio
import sys

from engine import store as movie_store
from engine.i18n import translate
from engine.parser import parse_args
from engine.errors import DemoError


async def load_catalog(url, path):
    store = movie_store.QdrantMovieStore(url)
    try:
        return await store.load(path)
    finally:
        await store.close()


def main():
    args = parse_args(sys.argv[1:])
    try:
        result = asyncio.run(load_catalog(args.url, args.data))
        print(translate('loaded', args.lang, **result))
    except (DemoError, ValueError, OSError, KeyError, TypeError) as exc:
        detail = exc.format(args.lang) if isinstance(exc, DemoError) else str(exc)
        print(translate('error', args.lang, detail=detail), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
