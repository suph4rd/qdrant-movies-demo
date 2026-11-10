import argparse
import asyncio
import getpass

from backend.engine import i18n
from backend.api import config
from backend.api.application import credential_validation
from backend.api.application.services import auth
from backend.api.infrastructure import database


async def create_admin(database_url, email, password):
    db = database.Database(database_url)
    try:
        await auth.AuthService(db.sessions).create_admin(email, password)
    finally:
        await db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lang', choices=('en', 'ru'), default='en')
    args = parser.parse_args()

    def translate(message):
        return i18n.translate_message(message, args.lang)

    try:
        email = input(translate('Email') + ': ')
        password = getpass.getpass(translate('Password') + ': ')
        repeated = getpass.getpass(translate('Repeat password') + ': ')
        credential_validation.validate_password(password, repeated)
        asyncio.run(create_admin(config.Settings().database_url, email, password))
    except ValueError as exc:
        parser.exit(1, translate(str(exc)) + '\n')
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, translate('Account creation cancelled.') + '\n')
    print(translate('Administrator created.'))


if __name__ == '__main__':
    main()
