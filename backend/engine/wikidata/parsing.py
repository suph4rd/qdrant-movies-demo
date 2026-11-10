from datetime import date
import re

from backend.engine.wikidata import validators


def values(entity, property_id):
    claims = entity.get('claims', {})
    if not isinstance(claims, dict):
        raise validators.invalid()
    statements = claims.get(property_id, [])
    if not isinstance(statements, list):
        raise validators.invalid()
    result = []
    for statement in statements:
        if not isinstance(statement, dict):
            raise validators.invalid()
        if statement.get('rank') == 'deprecated':
            continue
        snak = statement.get('mainsnak')
        if not isinstance(snak, dict):
            raise validators.invalid()
        if snak.get('snaktype') in ('novalue', 'somevalue'):
            continue
        data = snak.get('datavalue')
        if snak.get('snaktype') != 'value' or not isinstance(data, dict) or 'value' not in data:
            raise validators.invalid()
        result.append(data['value'])
    return result


def item_values(entity, property_id):
    result = []
    for value in values(entity, property_id):
        if not isinstance(value, dict) or not validators.valid_qid(value.get('id')):
            raise validators.invalid()
        result.append(value['id'])
    return result


def localized(entity, field, language):
    mapping = entity.get(field, {})
    if not isinstance(mapping, dict):
        raise validators.invalid()
    value = mapping.get(language)
    if value is None:
        return ''
    if not isinstance(value, dict) or not isinstance(value.get('value'), str):
        raise validators.invalid()
    return value['value'].strip()


def year(entity):
    years = []
    for value in values(entity, 'P577'):
        if not isinstance(value, dict):
            raise validators.invalid()
        timestamp, precision = value.get('time'), value.get('precision')
        if (not isinstance(timestamp, str) or type(precision) is not int or precision < 9
                or not re.fullmatch(r'\+[0-9]{4}-[0-9]{2}-[0-9]{2}T00:00:00Z', timestamp)):
            raise validators.invalid()
        year, month, day = map(int, timestamp[1:11].split('-'))
        if not 1800 <= year <= 9999:
            raise validators.invalid()
        try:
            date(year, month if precision >= 10 else 1, day if precision >= 11 else 1)
        except ValueError as exc:
            raise validators.invalid() from exc
        years.append(year)
    if not years:
        raise validators.invalid()
    # Different countries can have later release dates; use the earliest release.
    return min(years)
