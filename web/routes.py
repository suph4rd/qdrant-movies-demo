from flask import current_app, make_response, redirect, render_template, request, url_for

from engine import services
from engine.i18n import LANGUAGES, localize_movie


def select_language():
    explicit = request.args.get('lang')
    if explicit in LANGUAGES:
        return explicit
    saved = request.cookies.get('lang')
    if saved in LANGUAGES:
        return saved
    matches = [(quality, -index, tag.lower().split('-')[0])
               for index, (tag, quality) in enumerate(request.accept_languages)
               if quality > 0 and tag.lower().split('-')[0] in LANGUAGES]
    return max(matches)[2] if matches else 'en'


def remember_language(response, lang):
    response.set_cookie('lang', lang, max_age=31536000, httponly=True,
                        samesite='Lax')
    response.vary.add('Cookie')
    response.vary.add('Accept-Language')
    return response


def index():
    lang = select_language()
    query = request.args.get('q', '')
    limit = request.args.get('limit', '5')
    result, error, catalog = None, None, []
    try:
        catalog = services.read_movies(current_app.config['MOVIES_PATH'])
        if limit not in ('5', '10', '20', '50'):
            raise services.DemoError('web_limit')
        if 'q' in request.args:
            result = services.search(current_app.extensions['movie_store'], query, catalog, limit=int(limit))
            by_id = {m['id']: localize_movie(m, lang) for m in catalog}
            source_id = services.resolve_movie(query, catalog)['id']
            recommendations = []
            for point in result['recommendations']:
                if point['id'] not in by_id:
                    raise services.DemoError('unknown_id', id=point['id'])
                recommendations.append({**point, 'payload': by_id[point['id']]})
            result = {'source': by_id[source_id], 'recommendations': recommendations}
    except services.DemoError as exc:
        result = None
        error = exc.format(lang)
    switch_params = {'limit': limit}
    if 'q' in request.args:
        switch_params['q'] = query
    switches = {language: url_for('index', lang=language, **switch_params)
                for language in LANGUAGES}
    response = make_response(render_template(
        'index.html', query=query, result=result, error=error,
        catalog=[localize_movie(m, lang) for m in catalog], limit=limit,
        lang=lang, switches=switches))
    response.headers['Content-Language'] = lang
    return remember_language(response, lang)


def search():
    lang = request.form.get('lang')
    if lang not in LANGUAGES:
        lang = select_language()
    response = redirect(url_for('index', q=request.form.get('query', ''),
                                limit=request.form.get('limit', '5'), lang=lang), code=303)
    return remember_language(response, lang)
