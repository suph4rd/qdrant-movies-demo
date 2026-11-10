from backend.engine import errors


def freeze(value):
    if isinstance(value, Exception):
        if errors.is_expected_error(value):
            key, params = value._localization
            return {'__search_error__': {'key': key, 'params': freeze(params)}}
        return str(value)
    if isinstance(value, dict):
        return {key: freeze(item) for key, item in value.items()
                if key != 'vector' and not key.startswith('_')}
    if isinstance(value, (list, tuple)):
        return [freeze(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def thaw(value):
    if isinstance(value, dict):
        if '__search_error__' in value:
            data = value['__search_error__']
            return errors.DomainError(data['key'], **thaw(data['params']))
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, list):
        return [thaw(item) for item in value]
    return value
