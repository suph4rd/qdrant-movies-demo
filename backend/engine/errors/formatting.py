from backend.engine import i18n as engine_i18n
from backend.engine.errors import metadata


def format_error(error, lang='en'):
    if not metadata.is_expected_error(error):
        return str(error)
    key, params = error._localization
    params = dict(params)
    if key == 'ambiguous':
        params['titles'] = ', '.join(
            engine_i18n.localize_movie(movie, lang)['title'] for movie in params.pop('movies'))
    return engine_i18n.translate(key, lang, **params)


def format_message(message, lang='en'):
    params = dict(message.get('params', {}))
    if 'error' in params:
        params['detail'] = format_error(params.pop('error'), lang)
    return engine_i18n.translate(message['key'], lang, **params)
