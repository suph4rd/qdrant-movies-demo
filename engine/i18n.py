"""Shared gettext messages, independent of Flask."""
import gettext
from functools import lru_cache
from pathlib import Path

LANGUAGES = ('en', 'ru')
TRANSLATIONS_PATH = Path(__file__).resolve().parent / 'translations'


def N_(message):
    return message


MESSAGES = {
    'http': N_('Qdrant HTTP %(status)s: %(detail)s'),
    'response': N_('Invalid Qdrant response.'),
    'connection': N_('Cannot connect to Qdrant (%(url)s): %(detail)s'),
    'schema': N_('Incompatible movies collection: one unnamed 10-dimensional vector with Cosine distance is required. Existing data is unchanged.'),
    'count': N_('The movies collection contains additional records; they are preserved. This demo expects 250.'),
    'unknown_id': N_('Unknown movie ID: %(id)s. See movies.json for IDs.'),
    'read': N_('Cannot read the movie catalog: %(detail)s'),
    'size': N_('JSON must contain exactly 250 movies.'),
    'object': N_('Each movie must be an object.'),
    'duplicate_id': N_('Invalid or duplicate ID: %(id)s'),
    'vector': N_('Movie %(id)s: a nonzero vector of 10 numbers in the range 0–1 is required.'),
    'metadata': N_('Movie %(id)s: title, description, and genres are required in both languages.'),
    'year': N_('Movie %(id)s: invalid year or genres.'),
    'id': N_('ID must be an integer from 0 to 2^64−1.'),
    'empty': N_('Enter a movie title or ID.'),
    'not_found': N_('Movie not found. Enter another title or ID.'),
    'ambiguous': N_('Multiple movies found. Please specify the title: %(titles)s.'),
    'limit': N_('The recommendation count must be an integer from 1 to 249.'),
    'web_limit': N_('Choose the number of similar movies: 5, 10, 20, or 50.'),
    'title': N_('Your next movie'),
    'eyebrow': N_('MOVIE CATALOG · 250 MOVIES'),
    'heading': N_('What to watch next?'),
    'intro': N_('Choose a familiar movie to find similar movies by mood and genre.'),
    'query': N_('Movie title or ID'),
    'placeholder': N_('For example, The Matrix or 1'),
    'submit': N_('Find similar movies'),
    'number': N_('Number of similar movies'),
    'invalid': N_('Invalid value: %(value)s'),
    'hint': N_('You can enter part of a title in English or Russian. Matching ignores case.'),
    'similar': N_('Similar to “%(title)s”'),
    'cosine': N_('Cosine similarity measures manually assigned vector similarity, not the probability that you will like a movie.'),
    'score': N_('Cosine similarity'),
    'no_results': N_('No similar movies yet.'),
    'initial': N_('Start with a favorite movie. Recommendations will appear here.'),
    'languages': N_('Interface language'),
    'loaded': N_('Loaded %(loaded)s movies. Total in movies: %(count)s.'),
    'error': N_('Error: %(detail)s'),
    'cli_description': N_('Validate and load the movie catalog into Qdrant.'),
    'cli_url': N_('Qdrant REST URL'),
    'cli_data': N_('Path to the JSON catalog of 250 movies'),
    'cli_lang': N_('Output language (default: en)'),
    'cli_help': N_('Show this help message and exit'),
    'usage': N_('usage: '),
    'options': N_('options'),
    'arg_unrecognized': N_('unrecognized arguments: %(value)s'),
    'arg_expected': N_('argument %(value)s: expected one argument'),
    'arg_ignored': N_('argument %(argument)s: ignored explicit argument %(value)s'),
    'arg_choice': N_('argument %(argument)s: invalid choice: %(value)s (choose from %(choices)s)'),
}


@lru_cache(maxsize=2)
def catalog(lang):
    if lang not in LANGUAGES:
        raise ValueError('Unsupported language: ' + lang)
    if lang == 'en':
        return gettext.NullTranslations()
    return gettext.translation('messages', localedir=TRANSLATIONS_PATH, languages=[lang])


def translate(key, lang='en', **params):
    return catalog(lang).gettext(MESSAGES[key]) % params


def localize_movie(movie, lang='en'):
    if lang == 'en':
        return {**movie, **movie.get('translations', {}).get('en', {})}
    return dict(movie)
