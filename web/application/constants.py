from engine import constants


SEARCH_MODES = ('movie', 'description')
DEFAULT_MODE = SEARCH_MODES[0]
LIMIT_OPTIONS = ('5', '10', '20', '50')
DEFAULT_WEB_LIMIT = str(constants.DEFAULT_LIMIT)
SESSION_SECONDS = 7 * 24 * 60 * 60
