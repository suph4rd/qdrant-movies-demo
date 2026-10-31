import contextlib
import hashlib
import io
import json
import sys
import unittest
from unittest.mock import patch

from engine import DEFAULT_DATA_PATH, load, services
from engine.i18n import LANGUAGES, MESSAGES, localize_movie, translate


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.catalog = services.read_movies(DEFAULT_DATA_PATH)

    def test_complete_catalog_and_original_data(self):
        original = [{k: v for k, v in m.items() if k != 'translations'} for m in self.catalog]
        fingerprint = hashlib.sha256(json.dumps(original, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.assertEqual(fingerprint, 'a4f20447ef99e7081abf9d2eb3199ea5a2e45b150c64a658dd72695971568df2')
        for movie in self.catalog:
            english = localize_movie(movie, 'en')
            self.assertEqual(english['id'], movie['id'])
            self.assertEqual(english['year'], movie['year'])
            self.assertEqual(english['vector'], movie['vector'])
            self.assertEqual(len(english['genres']), len(movie['genres']))
            for text in [english['title'], english['description'], *english['genres']]:
                self.assertTrue(text.strip())
                self.assertFalse(any('\u0400' <= c <= '\u04ff' for c in text))
        for messages in MESSAGES.values():
            self.assertIsInstance(messages, str)
            self.assertTrue(all(messages))

    def test_every_title_in_both_languages(self):
        for movie in self.catalog:
            for lang in LANGUAGES:
                title = localize_movie(movie, lang)['title']
                with self.subTest(id=movie['id'], lang=lang):
                    self.assertEqual(services.resolve_movie(' ' + title.swapcase() + ' ', self.catalog)['id'], movie['id'])
        self.assertEqual(services.resolve_movie('the matr', self.catalog)['id'], 1)
        self.assertEqual(services.resolve_movie('матри', self.catalog)['id'], 1)
        self.assertEqual(services.resolve_movie('1917', self.catalog)['id'], 77)

    def test_cross_language_exact_match_and_deduplication(self):
        catalog = [
            {'id': 1, 'title': 'Test', 'translations': {'en': {'title': 'Test'}}},
            {'id': 2, 'title': 'Test sequel', 'translations': {'en': {'title': 'Another'}}},
        ]
        self.assertEqual(services.resolve_movie('test', catalog)['id'], 1)
        self.assertEqual(services.resolve_movie('another', catalog)['id'], 2)
        with self.assertRaises(services.DemoError) as raised:
            services.resolve_movie('Harry Potter', self.catalog)
        self.assertEqual(raised.exception.key, 'ambiguous')
        self.assertIn('Harry Potter', raised.exception.format('en'))
        self.assertIn('Гарри Поттер', raised.exception.format('ru'))
        self.assertNotIn('Harry Potter', raised.exception.format('ru'))

    def test_loader_languages_help_and_argument_errors(self):
        for lang in LANGUAGES:
            for arguments in (['--lang', lang], ['--lang=' + lang]):
                with patch.object(services.QdrantMovieStore, 'load', return_value={'loaded': 250, 'count': 250}), patch.object(sys, 'argv', ['loader'] + arguments), contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(load.main(), 0)
                    self.assertEqual(out.getvalue().strip(), translate('loaded', lang, loaded=250, count=250))
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
                self.assertIn(translate('usage', lang), text)
                self.assertIn(translate(key, lang, detail='').strip(), text)
                if lang == 'ru':
                    for fragment in ('unrecognized arguments', 'expected one argument', 'invalid choice', 'ignored explicit argument', 'options:'):
                        self.assertNotIn(fragment, text)
            with patch.object(sys, 'argv', ['loader', '--lang', lang]), patch.object(services.QdrantMovieStore, 'load', side_effect=services.DemoError('response')), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(load.main(), 1)
                self.assertIn(translate('response', lang), err.getvalue())

    def test_gettext_catalog_integrity(self):
        from babel.messages.pofile import read_po
        from babel.messages.mofile import write_mo
        from engine.i18n import TRANSLATIONS_PATH
        with (TRANSLATIONS_PATH / 'ru/LC_MESSAGES/messages.po').open('rb') as source:
            catalog = read_po(source)
        self.assertFalse(catalog.fuzzy)
        for message in catalog:
            if message.id:
                self.assertTrue(message.string)
                self.assertFalse(message.fuzzy)
                self.assertEqual(list(message.check()), [])
        for message in MESSAGES.values():
            self.assertIn(message, catalog)
        compiled = io.BytesIO()
        write_mo(compiled, catalog)
        self.assertEqual(compiled.getvalue(),
                         (TRANSLATIONS_PATH / 'ru/LC_MESSAGES/messages.mo').read_bytes())

    def test_engine_does_not_import_flask(self):
        import subprocess
        subprocess.run([sys.executable, '-c',
                        "import engine.services, engine.load; import sys; "
                        "assert 'flask' not in sys.modules"], check=True)

    def test_web_locale_is_request_scoped(self):
        from web.app import create_app
        with create_app({'TESTING': True}).test_client() as client:
            for lang in ('en', 'ru', 'en'):
                response = client.get('/?lang=' + lang)
                self.assertIn(translate('heading', lang), response.text)
