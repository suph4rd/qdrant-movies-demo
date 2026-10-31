from flask import current_app, redirect, render_template, request, url_for

from engine import services


def index():
    query = request.args.get('q', '')
    limit = request.args.get('limit', '5')
    result, error, catalog = None, None, []
    try:
        catalog = services.read_movies(current_app.config['MOVIES_PATH'])
        if limit not in ('5', '10', '20', '50'):
            raise services.DemoError('Выберите количество похожих фильмов: 5, 10, 20 или 50.')
        if 'q' in request.args:
            result = services.search(current_app.extensions['movie_store'], query, catalog, limit=int(limit))
    except services.DemoError as exc:
        error = str(exc)
    return render_template('index.html', query=query, result=result,
                           error=error, catalog=catalog, limit=limit)


def search():
    return redirect(url_for('index', q=request.form.get('query', ''),
                            limit=request.form.get('limit', '5')), code=303)

