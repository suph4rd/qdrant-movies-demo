from engine.i18n import LANGUAGES


def select_language(request):
    explicit = request.query_params.get('lang')
    if explicit in LANGUAGES:
        return explicit
    saved = request.cookies.get('lang')
    if saved in LANGUAGES:
        return saved
    matches = []
    for index, part in enumerate(request.headers.get('accept-language', '').split(',')):
        tag, *parameters = part.strip().split(';')
        quality = 1.0
        try:
            for parameter in parameters:
                name, value = parameter.strip().split('=', 1)
                if name == 'q':
                    quality = float(value)
        except ValueError:
            continue
        language = tag.lower().split('-')[0]
        if language in LANGUAGES and 0 < quality <= 1:
            matches.append((quality, -index, language))
    return max(matches)[2] if matches else 'en'


def remember_language(response, lang):
    response.set_cookie('lang', lang, max_age=31536000, httponly=True, samesite='lax')
    response.headers['Vary'] = 'Cookie, Accept-Language'
    response.headers['Content-Language'] = lang
    return response
