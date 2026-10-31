import os

from flask import Flask

from engine import DEFAULT_DATA_PATH, services
from web.router import register_routes


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        QDRANT_URL=os.environ.get('QDRANT_URL', 'http://127.0.0.1:6333'),
        MOVIES_PATH=DEFAULT_DATA_PATH,
    )
    if test_config is not None:
        app.config.update(test_config)

    app.extensions['movie_store'] = services.QdrantMovieStore(app.config['QDRANT_URL'])
    register_routes(app)

    return app
