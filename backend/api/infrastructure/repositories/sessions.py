import sqlalchemy as sa

from backend.api.infrastructure import clock
from backend.api.infrastructure import models


class SessionRepository:
    async def user(self, session, token_hash, lock=False):
        statement = sa.select(models.User).join(models.Session).where(
            models.Session.token_hash == token_hash,
            models.Session.expires_at > clock.now(), models.User.blocked.is_(False),
            models.User.deleted_at.is_(None))
        if lock:
            statement = statement.with_for_update(of=models.User)
        return await session.scalar(statement)

    async def delete(self, session, token_hash):
        await session.execute(sa.delete(models.Session).where(models.Session.token_hash == token_hash))

    async def revoke(self, session, user_id):
        await session.execute(sa.delete(models.Session).where(models.Session.user_id == user_id))

    async def add(self, session, token_hash, user_id, expires_at):
        session.add(models.Session(token_hash=token_hash, user_id=user_id, expires_at=expires_at))
