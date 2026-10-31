#!/usr/bin/env python3
"""Validate and upsert the bilingual movie catalog."""
import argparse
from pathlib import Path
import re
import sys

from engine import DEFAULT_DATA_PATH, services
from engine.i18n import LANGUAGES, translate
from engine.services import DemoError


class LocalizedParser(argparse.ArgumentParser):
    def __init__(self, lang):
        self.lang = lang
        super().__init__(description=translate('cli_description', lang), add_help=False,
                         allow_abbrev=False)
        self._optionals.title = translate('options', lang)
        self.add_argument('-h', '--help', action='help', help=translate('cli_help', lang))

    def format_usage(self):
        return super().format_usage().replace('usage: ', translate('usage', self.lang), 1)

    def format_help(self):
        return super().format_help().replace('usage: ', translate('usage', self.lang), 1)

    def error(self, message):
        if message.startswith('unrecognized arguments: '):
            message = translate('arg_unrecognized', self.lang, value=message.split(': ', 1)[1])
        else:
            expected = re.fullmatch(r'argument (.+): expected one argument', message)
            choice = re.fullmatch(r'argument (.+): invalid choice: (.+) \(choose from (.+)\)', message)
            ignored = re.fullmatch(r'argument (.+): ignored explicit argument (.+)', message)
            if ignored:
                message = translate('arg_ignored', self.lang, argument=ignored[1], value=ignored[2])
            elif expected:
                message = translate('arg_expected', self.lang, value=expected[1])
            elif choice:
                message = translate('arg_choice', self.lang, argument=choice[1],
                                    value=choice[2], choices=choice[3])
        self.print_usage(sys.stderr)
        self.exit(2, f'{self.prog}: {translate("error", self.lang, detail=message)}\n')


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
        if candidate in LANGUAGES:
            lang = candidate
    return lang


def main():
    lang = argument_language(sys.argv[1:])
    parser = LocalizedParser(lang)
    parser.add_argument('--lang', choices=LANGUAGES, default='en', help=translate('cli_lang', lang))
    parser.add_argument('--url', default='http://127.0.0.1:6333', help=translate('cli_url', lang))
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA_PATH,
                        help=translate('cli_data', lang))
    args = parser.parse_args()
    try:
        result = services.QdrantMovieStore(args.url).load(args.data)
        print(translate('loaded', args.lang, **result))
    except (DemoError, ValueError, OSError, KeyError, TypeError) as exc:
        detail = exc.format(args.lang) if isinstance(exc, DemoError) else str(exc)
        print(translate('error', args.lang, detail=detail), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
