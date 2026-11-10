import re

from backend.engine import errors
from backend.engine.imports import constants


def valid_tmdb_id(value):
    return type(value) is int and 0 < value < 2**32


def wikidata_number(value):
    if not isinstance(value, str) or not re.fullmatch(r'Q[1-9][0-9]{0,11}', value):
        raise errors.InputValidationError('wikidata_invalid')
    number = int(value[1:])
    if number >= constants.WIKIDATA_ID_LIMIT:
        raise errors.InputValidationError('wikidata_invalid')
    return number
