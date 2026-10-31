"""Локальный веб-интерфейс рекомендаций."""
import os

from flask import Flask, redirect, render_template, request, url_for

from engine import DEFAULT_DATA_PATH, services


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        QDRANT_URL=os.environ.get('QDRANT_URL', 'http://127.0.0.1:6333'),
        MOVIES_PATH=DEFAULT_DATA_PATH,
    )
    if test_config is not None:
        app.config.update(test_config)

    @app.get('/')
    def index():
        query = request.args.get('q', '')
        result, error, catalog = None, None, []
        try:
            catalog = services.read_movies(app.config['MOVIES_PATH'])
            if 'q' in request.args:
                result = services.search(app.config['QDRANT_URL'], query, catalog)
        except services.DemoError as exc:
            error = str(exc)
        return render_template('index.html', query=query, result=result,
                               error=error, catalog=catalog)

    @app.post('/search')
    def search():
        return redirect(url_for('index', q=request.form.get('query', '')), code=303)

    return app
