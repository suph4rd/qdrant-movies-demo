import contextlib
import io
from pathlib import Path
import unittest

from engine import DEFAULT_DATA_PATH
from engine.i18n import translate
from engine.parser import argument_language, parse_args


class ParserTests(unittest.TestCase):
    def test_defaults_and_options(self):
        args = parse_args([])
        self.assertEqual((args.lang, args.url, args.data),
                         ('en', 'http://127.0.0.1:6333', DEFAULT_DATA_PATH))
        args = parse_args(['--url', 'http://test', '--data', 'custom.json', '--lang=ru'])
        self.assertEqual((args.lang, args.url, args.data), ('ru', 'http://test', Path('custom.json')))
        self.assertEqual(parse_args(['--lang', 'ru', '--lang=en']).lang, 'en')
        self.assertEqual(argument_language(['--lang=ru', '--', '--lang=en']), 'ru')

    def test_localized_help_and_errors(self):
        for lang in ('en', 'ru'):
            for arguments, code in ((['--help'], 0), (['--unknown'], 2),
                                    (['--url'], 2), (['--lang=xx'], 2),
                                    (['--', '--url'], 2)):
                with self.subTest(lang=lang, arguments=arguments):
                    output, errors = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                        with self.assertRaises(SystemExit) as raised:
                            parse_args(['--lang', lang] + arguments)
                    self.assertEqual(raised.exception.code, code)
                    if code == 0:
                        self.assertIn(translate('cli_description', lang), output.getvalue())
                        self.assertEqual(errors.getvalue(), '')
                    else:
                        self.assertIn(translate('usage', lang), errors.getvalue())
                        self.assertEqual(output.getvalue(), '')
