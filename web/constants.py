from pathlib import Path

from engine import constants


PACKAGE_PATH = Path(__file__).resolve().parent
TEMPLATES_PATH = PACKAGE_PATH / 'templates'
STATIC_PATH = PACKAGE_PATH / 'static'
SEARCH_MODES = ('movie', 'description')
DEFAULT_MODE = SEARCH_MODES[0]
LIMIT_OPTIONS = ('5', '10', '20', '50')
DEFAULT_WEB_LIMIT = str(constants.DEFAULT_LIMIT)
