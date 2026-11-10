from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr

from backend.api.application import constants


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SearchInput(Input):
    q: StrictStr
    mode: StrictStr = constants.DEFAULT_MODE
    limit: StrictStr = constants.DEFAULT_WEB_LIMIT


class LoginInput(Input):
    email: StrictStr
    password: StrictStr


class RegistrationInput(LoginInput):
    password_repeat: StrictStr


class MarkInput(Input):
    movie_id: StrictStr
    flag: StrictStr
    state: StrictBool
    reference: StrictStr = ''


class AdminInput(Input):
    action: StrictStr
    confirmation_email: StrictStr = ''

