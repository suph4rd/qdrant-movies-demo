import re
import unicodedata

from engine import errors


def normalize_title(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def parse_query(query):
    if not isinstance(query, str) or not query.strip():
        raise errors.InputValidationError('empty')
    query = query.strip()
    match = re.fullmatch(r'(.+?)\s*\((\d{4})\)', query)
    return (match[1].strip(), int(match[2])) if match else (query, None)


def titles(movie):
    values = [movie.get('title', ''), movie.get('original_title', '')]
    values.extend(movie.get('alternative_titles', []))
    values.append(movie.get('translations', {}).get('en', {}).get('title', ''))
    return {normalize_title(v) for v in values if isinstance(v, str) and v.strip()}


def matches(movie, title, year=None):
    return normalize_title(title) in titles(movie) and (year is None or movie.get('year') == year)
