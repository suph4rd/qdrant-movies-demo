import contextlib
import hashlib
import io
import json
import sys
import unittest
from unittest.mock import patch

from backend.engine import catalog as movie_catalog
from backend.engine import constants
from backend.engine import errors
from backend.engine import i18n as engine_i18n
from backend.engine import load
from backend.engine.stores import semantic
from backend.engine.tests import helpers
from backend.api import app as web_app


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = movie_catalog.read_movies(constants.DEFAULT_DATA_PATH)

    def test_complete_catalog_and_original_data(self):
        original = [{k: v for k, v in m.items() if k != 'translations'} for m in self.catalog]
        fingerprint = hashlib.sha256(json.dumps(original, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.assertEqual(fingerprint, 'a4f20447ef99e7081abf9d2eb3199ea5a2e45b150c64a658dd72695971568df2')
        for movie in self.catalog:
            english = engine_i18n.localize_movie(movie, 'en')
            self.assertEqual(english['id'], movie['id'])
            self.assertEqual(english['year'], movie['year'])
            self.assertEqual(english['vector'], movie['vector'])
            self.assertEqual(len(english['genres']), len(movie['genres']))
            for text in [english['title'], english['description'], *english['genres']]:
                self.assertTrue(text.strip())
                self.assertFalse(any('\u0400' <= c <= '\u04ff' for c in text))
        for messages in engine_i18n.MESSAGES.values():
            self.assertIsInstance(messages, str)
            self.assertTrue(all(messages))

    def test_every_title_in_both_languages(self):
        for movie in self.catalog:
            for lang in engine_i18n.LANGUAGES:
                title = engine_i18n.localize_movie(movie, lang)['title']
                with self.subTest(id=movie['id'], lang=lang):
                    self.assertEqual(movie_catalog.resolve_movie(' ' + title.swapcase() + ' ', self.catalog)['id'], movie['id'])
        self.assertEqual(movie_catalog.resolve_movie('the matr', self.catalog)['id'], 1)
        self.assertEqual(movie_catalog.resolve_movie('матри', self.catalog)['id'], 1)
        self.assertEqual(movie_catalog.resolve_movie('1917', self.catalog)['id'], 77)

    def test_cross_language_exact_match_and_deduplication(self):
        catalog = [
            {'id': 1, 'title': 'Test', 'translations': {'en': {'title': 'Test'}}},
            {'id': 2, 'title': 'Test sequel', 'translations': {'en': {'title': 'Another'}}},
        ]
        self.assertEqual(movie_catalog.resolve_movie('test', catalog)['id'], 1)
        self.assertEqual(movie_catalog.resolve_movie('another', catalog)['id'], 2)
        with helpers.expected_error(self) as raised:
            movie_catalog.resolve_movie('Harry Potter', self.catalog)
        self.assertEqual(raised.exception._localization[0], 'ambiguous')
        self.assertIn('Harry Potter', errors.format_error(raised.exception, 'en'))
        self.assertIn('Гарри Поттер', errors.format_error(raised.exception, 'ru'))
        self.assertNotIn('Harry Potter', errors.format_error(raised.exception, 'ru'))

    def test_loader_languages_help_and_argument_errors(self):
        for lang in engine_i18n.LANGUAGES:
            for arguments in (['--lang', lang], ['--lang=' + lang]):
                with patch.object(semantic.SemanticMovieStore, 'load', return_value={'loaded': 250, 'count': 250}), patch.object(sys, 'argv', ['loader'] + arguments), contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(load.main(), 0)
                    self.assertEqual(out.getvalue().strip(), engine_i18n.translate('loaded', lang, loaded=250, count=250))
            for arguments, code, key in (
                (['--help'], 0, 'cli_data'),
                (['--unknown'], 2, 'error'),
                (['--url'], 2, 'error'),
                (['--lang', 'de'], 2, 'error'),
                (['--help=extra'], 2, 'error'),
            ):
                with patch.object(sys, 'argv', ['loader', '--lang', lang] + arguments), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as raised:
                    load.main()
                self.assertEqual(raised.exception.code, code)
                text = out.getvalue() + err.getvalue()
                self.assertIn(engine_i18n.translate('usage', lang), text)
                self.assertIn(engine_i18n.translate(key, lang, detail='').strip(), text)
                if lang == 'ru':
                    for fragment in ('unrecognized arguments', 'expected one argument', 'invalid choice', 'ignored explicit argument', 'options:'):
                        self.assertNotIn(fragment, text)
            with patch.object(sys, 'argv', ['loader', '--lang', lang]), patch.object(semantic.SemanticMovieStore, 'load', side_effect=errors.IndexStateError('response')), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(load.main(), 1)
                self.assertIn(engine_i18n.translate('response', lang), err.getvalue())

    def test_gettext_catalog_integrity(self):
        from babel.messages.pofile import read_po
        from babel.messages.mofile import write_mo
        with (engine_i18n.TRANSLATIONS_PATH / 'ru/LC_MESSAGES/messages.po').open('rb') as source:
            catalog = read_po(source)
        self.assertFalse(catalog.fuzzy)
        for message in catalog:
            if message.id:
                self.assertTrue(message.string)
                self.assertFalse(message.fuzzy)
                self.assertEqual(list(message.check()), [])
        for message in engine_i18n.MESSAGES.values():
            self.assertIn(message, catalog)
        compiled = io.BytesIO()
        write_mo(compiled, catalog)
        self.assertEqual(compiled.getvalue(),
                         (engine_i18n.TRANSLATIONS_PATH / 'ru/LC_MESSAGES/messages.mo').read_bytes())

    def test_engine_does_not_import_flask(self):
        import subprocess
        subprocess.run([sys.executable, '-c',
                        "import backend.engine.services, backend.engine.load; import sys; "
                        "assert 'flask' not in sys.modules"], check=True)

    def test_web_locale_is_request_scoped(self):
        from fastapi.testclient import TestClient
        with patch('backend.engine.stores.semantic.SemanticMovieStore.count_movies', return_value=250), TestClient(web_app.create_app()) as client:
            for lang in ('en', 'ru', 'en'):
                response = client.get('/api/context?lang=' + lang)
                self.assertEqual(response.json()['lang'], lang)
                self.assertEqual(response.json()['catalog'][0]['title'],
                                 engine_i18n.localize_movie(client.app.state.catalog[0], lang)['title'])


class SharedLocalizationTests(unittest.TestCase):
    def test_source_translation_matches_key_translation(self):
        for lang in engine_i18n.LANGUAGES:
            self.assertEqual(
                engine_i18n.translate_message(engine_i18n.MESSAGES['import_added'], lang, title='Solaris'),
                engine_i18n.translate('import_added', lang, title='Solaris'))

    def test_structured_messages_localize_nested_errors_without_mutation(self):
        error = errors.InputValidationError('import_invalid')
        message = {'key': 'import_failed', 'params': {'title': 'Solaris', 'error': error}}
        for lang in engine_i18n.LANGUAGES:
            self.assertEqual(errors.format_message(message, lang), engine_i18n.translate(
                'import_failed', lang, title='Solaris', detail=errors.format_error(error, lang)))
        self.assertIs(message['params']['error'], error)
        self.assertNotIn('detail', message['params'])

    def test_description_language_and_original_movie_are_preserved(self):
        movie = {'title': 'Фильм', 'description': 'Описание', 'description_language': 'ru',
                 'translations': {'en': {'title': 'Movie', 'description': 'Description'}}}
        english = engine_i18n.localize_movie(movie, 'en')
        self.assertEqual(english['description_language'], 'en')
        self.assertEqual(movie['description_language'], 'ru')
        self.assertEqual(engine_i18n.localize_movie(movie, 'ru'), movie)
        fallback = {**movie, 'description_language': 'en'}
        self.assertEqual(engine_i18n.localize_movie(fallback, 'ru')['description_language'], 'en')
