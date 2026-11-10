import argparse
import os
from pathlib import Path
import re
import sys

from backend.engine import constants
from backend.engine import i18n as engine_i18n
from backend.engine.embeddings import constants as embedding_constants


class LocalizedParser(argparse.ArgumentParser):
    def __init__(self, lang):
        self.lang = lang
        super().__init__(description=engine_i18n.translate('cli_description', lang), add_help=False,
                         allow_abbrev=False)
        self._optionals.title = engine_i18n.translate('options', lang)
        self.add_argument('-h', '--help', action='help', help=engine_i18n.translate('cli_help', lang))

    def format_usage(self):
        return super().format_usage().replace('usage: ', engine_i18n.translate('usage', self.lang), 1)

    def format_help(self):
        return super().format_help().replace('usage: ', engine_i18n.translate('usage', self.lang), 1)

    def error(self, message):
        if message.startswith('unrecognized arguments: '):
            message = engine_i18n.translate('arg_unrecognized', self.lang, value=message.split(': ', 1)[1])
        else:
            expected = re.fullmatch(r'argument (.+): expected one argument', message)
            choice = re.fullmatch(r'argument (.+): invalid choice: (.+) \(choose from (.+)\)', message)
            ignored = re.fullmatch(r'argument (.+): ignored explicit argument (.+)', message)
            if ignored:
                message = engine_i18n.translate('arg_ignored', self.lang, argument=ignored[1], value=ignored[2])
            elif expected:
                message = engine_i18n.translate('arg_expected', self.lang, value=expected[1])
            elif choice:
                message = engine_i18n.translate('arg_choice', self.lang, argument=choice[1],
                                    value=choice[2], choices=choice[3])
        self.print_usage(sys.stderr)
        self.exit(2, f'{self.prog}: {engine_i18n.translate("error", self.lang, detail=message)}\n')


def argument_language(arguments):
    lang = 'en'
    for i, value in enumerate(arguments):
        if value == '--':
            break
        candidate = None
        if value.startswith('--lang='):
            candidate = value.split('=', 1)[1]
        elif value == '--lang' and i + 1 < len(arguments):
            candidate = arguments[i + 1]
        if candidate in engine_i18n.LANGUAGES:
            lang = candidate
    return lang


def parse_args(arguments):
    lang = argument_language(arguments)
    parser = LocalizedParser(lang)
    parser.add_argument('--lang', choices=engine_i18n.LANGUAGES, default='en', help=engine_i18n.translate('cli_lang', lang))
    parser.add_argument('--url', default=os.environ.get('QDRANT_URL', constants.DEFAULT_URL), help=engine_i18n.translate('cli_url', lang))
    parser.add_argument('--data', type=Path, default=constants.DEFAULT_DATA_PATH,
                        help=engine_i18n.translate('cli_data', lang))
    parser.add_argument('--embedding-url', default=os.environ.get('EMBEDDING_URL', constants.DEFAULT_EMBEDDING_URL),
                        help=engine_i18n.translate('cli_embedding_url', lang))
    parser.add_argument('--collection', default=os.environ.get('MOVIES_COLLECTION', constants.DEFAULT_COLLECTION),
                        help=engine_i18n.translate('cli_collection', lang))
    parser.add_argument('--cache', type=Path, default=Path(os.environ.get('EMBEDDING_CACHE', str(embedding_constants.DEFAULT_CACHE_PATH))),
                        help=engine_i18n.translate('cli_cache', lang))
    return parser.parse_args(arguments)
