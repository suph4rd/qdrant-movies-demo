def annotate_error(error, key, **params):
    error._localization = (key, params)
    return error


def is_expected_error(error):
    return hasattr(error, '_localization')
