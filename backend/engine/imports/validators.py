from backend.engine import errors
from backend.engine import validators
from backend.engine.imports import constants
from backend.engine.imports import identity


def validate_movie(movie):
    if not isinstance(movie, dict):
        raise errors.InputValidationError('wikidata_invalid')
    source = movie.get('source')
    key = 'import_invalid' if source == 'tmdb' else 'wikidata_invalid'
    if source == 'tmdb':
        external_id = movie.get('tmdb_id')
        identity_valid = identity.valid_tmdb_id(external_id) and movie.get('id') == constants.TMDB_ID_BASE + external_id
    elif source == 'wikidata':
        number = identity.wikidata_number(movie.get('wikidata_id'))
        identity_valid = (movie.get('id') == constants.WIKIDATA_ID_BASE + number
                          and ('tmdb_id' not in movie or identity.valid_tmdb_id(movie['tmdb_id'])))
    else:
        identity_valid = False
    translations = movie.get('translations')
    if (not identity_valid or type(movie.get('id')) is not int
            or type(movie.get('year')) is not int or not 1800 <= movie['year'] <= 9999
            or not validators.valid_metadata(movie)
            or not isinstance(translations, dict)
            or not validators.valid_metadata(translations.get('en'))
            or not isinstance(movie.get('original_title'), str) or not movie['original_title'].strip()
            or movie.get('description_language') not in ('en', 'ru')
            or not isinstance(movie.get('alternative_titles'), list)
            or not all(isinstance(t, str) and t.strip() for t in movie['alternative_titles'])):
        raise errors.InputValidationError(key)
    return movie
