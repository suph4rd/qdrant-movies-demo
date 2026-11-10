from dataclasses import asdict

from backend.engine import errors
from backend.engine import i18n
from backend.api.application.services import account


MOVIE_FIELDS = ('id', 'title', 'year', 'genres', 'description', 'original_title',
                'wikidata_id', 'tmdb_id', 'description_language')


def movie(movie, lang, catalog=(), cards=None):
    localized = i18n.localize_movie(movie, lang)
    result = {key: localized[key] for key in MOVIE_FIELDS if key in localized}
    result['id'] = str(movie['id'])
    if cards is not None:
        try:
            result['mark_reference'] = cards.reference(catalog, movie)
        except Exception as exc:
            if not errors.is_expected_error(exc):
                raise
    return result


def search_result(result, lang, catalog, cards=None):
    if result is None:
        return None
    by_id = {str(item['id']): item for item in catalog}

    def resolve(value, movie_id=None):
        identifier = movie_id if movie_id is not None else value.get('id')
        original = by_id.get(str(identifier), value)
        if not isinstance(original, dict) or not original.get('title'):
            raise errors.MovieNotFoundError('unknown_id', id=identifier)
        return movie(original, lang, catalog, cards)

    return {'groups': [
        {'source': resolve(group['source']) if group['source'] is not None else None,
         'recommendations': [{'id': str(point['id']), 'score': point['score'],
                              'payload': resolve(point['payload'], point['id'])}
                             for point in group['recommendations']]}
        for group in result.get('groups', [result])],
        'messages': [errors.format_message(message, lang) for message in result.get('messages', [])]}


def movie_list(listing, lang):
    return {'flag': listing.flag, 'label': i18n.translate_message(account.LABELS[listing.flag], lang),
            'page': listing.page, 'total': listing.total,
            'has_next': listing.page * account.PAGE_SIZE < listing.total,
            'movies': [{'movie': movie(item, lang), 'mark': asdict(mark)}
                       for item, mark in listing.movies]}
