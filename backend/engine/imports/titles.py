import re
import unicodedata

from backend.engine import errors


def normalize_title(value):
    value = unicodedata.normalize('NFKC', value).casefold().replace('ё', 'е')
    return ' '.join(''.join(char if char.isalnum() else ' ' for char in value).split())


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


def similarity(left, right):
    left, right = normalize_title(left), normalize_title(right)
    if left == right:
        return 1.0
    if min(len(left), len(right)) < 5:
        return 0.0
    previous = list(range(len(right) + 1))
    for row, char in enumerate(left, 1):
        current = [row]
        for column, other in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[column] + 1,
                               previous[column - 1] + (char != other)))
        previous = current
    return 1 - previous[-1] / max(len(left), len(right))


def select_similar(movies, title, year=None):
    eligible = [movie for movie in movies if year is None or movie.get('year') == year]
    exact = [movie for movie in eligible if matches(movie, title, year)]
    if exact:
        return exact
    ranked = sorted(((max((similarity(title, name) for name in titles(movie)), default=0), movie)
                     for movie in eligible), key=lambda value: value[0], reverse=True)
    if ranked and ranked[0][0] >= 0.90 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.05):
        return [ranked[0][1]]
    return []
