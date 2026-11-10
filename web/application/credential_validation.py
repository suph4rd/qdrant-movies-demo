import re
import unicodedata

from web.application import errors


def normalize_email(value):
    if not isinstance(value, str):
        raise errors.ScenarioError('Enter a valid email address.')
    email = unicodedata.normalize('NFKC', value).strip().casefold()
    if (len(email) > 254 or any(unicodedata.category(char).startswith('C') for char in email)
            or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email)):
        raise errors.ScenarioError('Enter a valid email address.')
    return email


def validate_password(password, repeated):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise errors.ScenarioError('Password must contain 12–128 characters.')
    if password != repeated:
        raise errors.ScenarioError('Passwords do not match.')


