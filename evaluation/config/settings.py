import os

from engine import constants


def store_settings():
    return {
        'base_url': os.environ.get('QDRANT_URL', constants.DEFAULT_URL),
        'embedding_url': os.environ.get('EMBEDDING_URL', constants.DEFAULT_EMBEDDING_URL),
        'collection_name': os.environ.get('MOVIES_COLLECTION', constants.DEFAULT_COLLECTION),
    }
