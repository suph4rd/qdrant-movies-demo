from backend.engine import errors
from backend.engine import imports


def valid_qid(value):
    try:
        imports.wikidata_number(value)
    except errors.InputValidationError:
        return False
    return True


def invalid():
    return errors.InputValidationError('wikidata_invalid')
