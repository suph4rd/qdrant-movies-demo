from datetime import timedelta
import secrets

from sqlalchemy import exc as sa_errors

from web.application import constants
from web.application import credential_validation
from web.application import dtos
from web.application import errors
from web.infrastructure import clock
from web.infrastructure import passwords
from web.infrastructure.repositories import sessions, users


class AuthService:
    def __init__(self, session_factory, user_repository=None, session_repository=None):
        self.sessions = session_factory
        self.users = user_repository or users.UserRepository()
        self.tokens = session_repository or sessions.SessionRepository()

    async def current_user(self, token):
        if not token:
            return None
        async with self.sessions() as session:
            user = await self.tokens.user(session, passwords.token_hash(token))
            return dtos.User.from_record(user) if user is not None else None

    async def create_session(self, session, user_id, old_token=None):
        if old_token:
            await self.tokens.delete(session, passwords.token_hash(old_token))
        token = secrets.token_urlsafe(32)
        await self.tokens.add(session, passwords.token_hash(token), user_id,
                              clock.now() + timedelta(seconds=constants.SESSION_SECONDS))
        return token

    async def register(self, email, password, repeated, old_token=None):
        email = credential_validation.normalize_email(email)
        credential_validation.validate_password(password, repeated)
        encoded = await passwords.hash_password(password)
        try:
            async with self.sessions() as session, session.begin():
                user = await self.users.add(session, email, encoded)
                return await self.create_session(session, user.id, old_token)
        except sa_errors.IntegrityError as exc:
            if getattr(exc.orig, 'sqlstate', None) != '23505':
                raise
            raise errors.EmailRegistered() from exc

    async def login(self, email, password, old_token=None):
        try:
            email = credential_validation.normalize_email(email)
        except errors.ScenarioError:
            email = ''
        # Invalid and unknown credentials still perform Argon2 verification.
        if not isinstance(password, str) or len(password) > 128:
            password = ''
        async with self.sessions() as session, session.begin():
            user = await self.users.by_email(session, email)
            valid = await passwords.verify_password(user.password_hash if user else passwords.DUMMY_HASH, password)
            if not valid or user is None or user.blocked or user.deleted_at is not None:
                raise errors.ScenarioError('Invalid email or password.')
            if passwords.needs_rehash(user.password_hash):
                user.password_hash = await passwords.hash_password(password)
            return await self.create_session(session, user.id, old_token)

    async def logout(self, token):
        if token:
            async with self.sessions() as session, session.begin():
                await self.tokens.delete(session, passwords.token_hash(token))

    async def create_admin(self, email, password):
        email = credential_validation.normalize_email(email)
        credential_validation.validate_password(password, password)
        encoded = await passwords.hash_password(password)
        try:
            async with self.sessions() as session, session.begin():
                await self.users.admin_lock(session)
                if await self.users.active_admin_count(session):
                    raise errors.ScenarioError('An active administrator already exists.')
                await self.users.add(session, email, encoded, role='admin')
        except sa_errors.IntegrityError as exc:
            if getattr(exc.orig, 'sqlstate', None) != '23505':
                raise
            raise errors.EmailRegistered() from exc
