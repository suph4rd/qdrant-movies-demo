import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.engine import constants
from backend.engine import i18n as engine_i18n
from backend.engine import parser


class ParserTests(unittest.TestCase):
    @patch.dict('os.environ', {}, clear=True)
    def test_defaults_and_options(self):
        args = parser.parse_args([])
        self.assertEqual((args.lang, args.url, args.data),
                         ('en', 'http://127.0.0.1:6333', constants.DEFAULT_DATA_PATH))
        args = parser.parse_args(['--url', 'http://test', '--data', 'custom.json', '--lang=ru'])
        self.assertEqual((args.lang, args.url, args.data), ('ru', 'http://test', Path('custom.json')))
        self.assertEqual(parser.parse_args(['--lang', 'ru', '--lang=en']).lang, 'en')
        self.assertEqual(parser.argument_language(['--lang=ru', '--', '--lang=en']), 'ru')

    def test_localized_help_and_errors(self):
        for lang in ('en', 'ru'):
            for arguments, code in ((['--help'], 0), (['--unknown'], 2),
                                    (['--url'], 2), (['--lang=xx'], 2),
                                    (['--', '--url'], 2)):
                with self.subTest(lang=lang, arguments=arguments):
                    output, errors = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                        with self.assertRaises(SystemExit) as raised:
                            parser.parse_args(['--lang', lang] + arguments)
                    self.assertEqual(raised.exception.code, code)
                    if code == 0:
                        self.assertIn(engine_i18n.translate('cli_description', lang), output.getvalue())
                        self.assertEqual(errors.getvalue(), '')
                    else:
                        self.assertIn(engine_i18n.translate('usage', lang), errors.getvalue())
                        self.assertEqual(output.getvalue(), '')

    def test_environment_defaults_and_cli_overrides(self):
        with patch.dict('os.environ', {'QDRANT_URL':'http://db', 'EMBEDDING_URL':'http://model',
                                     'MOVIES_COLLECTION':'semantic_v2', 'EMBEDDING_CACHE':'cache-v2'}):
            args=parser.parse_args([])
            self.assertEqual((args.url,args.embedding_url,args.collection,args.cache),
                             ('http://db','http://model','semantic_v2',Path('cache-v2')))
            args=parser.parse_args(['--url','http://other','--embedding-url','http://other-model',
                             '--collection','movies','--cache','other-cache'])
            self.assertEqual((args.url,args.embedding_url,args.collection,args.cache),
                             ('http://other','http://other-model','movies',Path('other-cache')))
