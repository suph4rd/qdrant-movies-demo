from engine import i18n as engine_i18n
from engine.errors import metadata


def format_error(error, lang='en'):
    if not metadata.is_expected_error(error):
        return str(error)
    key, params = error._localization
    params = dict(params)
    if key == 'ambiguous':
        params['titles'] = ', '.join(
            engine_i18n.localize_movie(movie, lang)['title'] for movie in params.pop('movies'))
    return engine_i18n.translate(key, lang, **params)
