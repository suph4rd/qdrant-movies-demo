from urllib.parse import urlencode, urlsplit

from engine import i18n as engine_i18n
from web.application.services import account


def page_number(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 1000000 else None


def mark_return_url(value, flag, lang):
    fallback = '/account?' + urlencode({'list': flag, 'lang': lang})
    if not isinstance(value, str) or not value.startswith('/'):
        return fallback
    if '\\' in value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        return fallback
    try:
        parsed = urlsplit(value)
    except ValueError:
        return fallback
    if parsed.scheme or parsed.netloc or parsed.path not in ('/', '/account'):
        return fallback
    return value


def movie_list(listing, lang):
    return {'flag': listing.flag, 'label': account.LABELS[listing.flag],
            'page': listing.page, 'total': listing.total,
            'has_multiple_pages': listing.total > account.PAGE_SIZE,
            'has_next': listing.page * account.PAGE_SIZE < listing.total,
            'movies': [{'movie': engine_i18n.localize_movie(movie, lang), 'mark': mark}
                       for movie, mark in listing.movies],
            'previous_url': '/account?' + urlencode({'list': listing.flag,
                'page': max(1, listing.page - 1), 'lang': lang}),
            'next_url': '/account?' + urlencode({'list': listing.flag,
                'page': listing.page + 1, 'lang': lang})}
