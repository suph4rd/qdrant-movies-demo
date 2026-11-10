import sqlalchemy as sa

from backend.api.infrastructure import models


class UserRepository:
    async def get(self, session, user_id, lock=False):
        return await session.get(models.User, user_id, with_for_update=lock)

    async def lock(self, session, user_id):
        return await session.scalar(sa.select(models.User).where(
            models.User.id == user_id).with_for_update())

    async def by_email(self, session, email):
        return await session.scalar(sa.select(models.User).where(
            models.User.email == email).with_for_update())

    async def add(self, session, email, password_hash, role='user'):
        user = models.User(email=email, password_hash=password_hash, role=role)
        session.add(user)
        await session.flush()
        return user

    async def admin_lock(self, session):
        await session.execute(sa.text('SELECT pg_advisory_xact_lock(:key)'), {'key': 194274})

    async def active_admin_count(self, session):
        return await session.scalar(sa.select(sa.func.count()).select_from(models.User).where(
            models.User.role == 'admin', models.User.blocked.is_(False),
            models.User.deleted_at.is_(None)))

    async def list(self, session, query, role, state, offset, limit):
        conditions = []
        if query:
            conditions.append(models.User.email.contains(query.casefold(), autoescape=True))
        if role:
            conditions.append(models.User.role == role)
        if state == 'active':
            conditions.extend((models.User.blocked.is_(False), models.User.deleted_at.is_(None)))
        elif state == 'blocked':
            conditions.extend((models.User.blocked.is_(True), models.User.deleted_at.is_(None)))
        elif state == 'deleted':
            conditions.append(models.User.deleted_at.is_not(None))
        return list((await session.scalars(sa.select(models.User).where(*conditions).order_by(
            models.User.id).offset(offset).limit(limit))).all())
