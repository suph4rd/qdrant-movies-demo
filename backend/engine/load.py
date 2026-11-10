#!/usr/bin/env python3
import asyncio
import sys

from backend.engine import constants
from backend.engine import errors
from backend.engine import i18n as engine_i18n
from backend.engine import parser
from backend.engine.stores import factory


async def load_catalog(url, path, collection_name=constants.DEFAULT_COLLECTION,
                       embedding_url=constants.DEFAULT_EMBEDDING_URL, cache_path=None):
    store = factory.create_store(url, collection_name, embedding_url, cache_path)
    try:
        return await store.load(path)
    finally:
        await store.close()


def main():
    args = parser.parse_args(sys.argv[1:])
    try:
        result = asyncio.run(load_catalog(args.url, args.data, args.collection, args.embedding_url, args.cache))
        print(engine_i18n.translate('loaded', args.lang, **result))
    except Exception as exc:
        if not errors.is_expected_error(exc):
            raise
        detail = errors.format_error(exc, args.lang)
        print(engine_i18n.translate('error', args.lang, detail=detail), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
