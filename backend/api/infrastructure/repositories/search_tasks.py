from datetime import timedelta
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from backend.api.infrastructure import clock, models


ACTIVE = ('queued', 'running')
TERMINAL = ('succeeded', 'failed')
LEASE_SECONDS = 60


class SearchTaskRepository:
    async def lock_owners(self, session, owners):
        # Insert and lock one owner at a time in a global order, including first use.
        for owner_id, user_id in sorted(owners.items()):
            await session.execute(postgresql.insert(models.SearchOwner).values(
                id=owner_id, user_id=user_id).on_conflict_do_nothing())
            await session.scalar(sa.select(models.SearchOwner).where(
                models.SearchOwner.id == owner_id).with_for_update())

    async def active(self, session, owner_ids):
        return (await session.scalars(sa.select(models.SearchTask).where(
            models.SearchTask.owner_id.in_(owner_ids), models.SearchTask.status.in_(ACTIVE))
            .order_by(models.SearchTask.created_at, models.SearchTask.id))).all()

    async def add(self, session, owner_id, params):
        task = models.SearchTask(id=uuid.uuid4().hex, owner_id=owner_id,
            query=params['q'], mode=params['mode'], limit=params['limit'], status='queued')
        session.add(task)
        await session.flush()
        session.add(models.SearchOutbox(task_id=task.id))
        await session.flush()
        return task

    async def visible(self, session, owner_ids, task_id=None):
        statement = sa.select(models.SearchTask).where(models.SearchTask.owner_id.in_(owner_ids))
        if task_id is not None:
            return await session.scalar(statement.where(models.SearchTask.id == task_id))
        return (await session.scalars(statement.where(sa.or_(
            models.SearchTask.status.in_(ACTIVE), models.SearchTask.read_at.is_(None)))
            .order_by(models.SearchTask.created_at, models.SearchTask.id))).all()

    async def claim(self, session, task_id, token):
        return await session.scalar(sa.update(models.SearchTask).where(
            models.SearchTask.id == task_id, models.SearchTask.status.in_(ACTIVE),
            sa.or_(models.SearchTask.lease_until.is_(None), models.SearchTask.lease_until <= clock.now()))
            .values(status='running', attempt_token=token,
                    lease_until=clock.now() + timedelta(seconds=LEASE_SECONDS))
            .returning(models.SearchTask))

    async def renew(self, session, task_id, token):
        result = await session.execute(sa.update(models.SearchTask).where(
            models.SearchTask.id == task_id, models.SearchTask.status == 'running',
            models.SearchTask.attempt_token == token, models.SearchTask.lease_until > clock.now())
            .values(lease_until=clock.now() + timedelta(seconds=LEASE_SECONDS)))
        return result.rowcount == 1

    async def finish(self, session, task_id, token, result, error):
        changed = await session.execute(sa.update(models.SearchTask).where(
            models.SearchTask.id == task_id, models.SearchTask.status == 'running',
            models.SearchTask.attempt_token == token, models.SearchTask.lease_until > clock.now())
            .values(status='failed' if error else 'succeeded', result=result, error=error,
                    completed_at=clock.now(), attempt_token=None, lease_until=None))
        return changed.rowcount == 1

    async def release(self, session, task_id, token):
        await session.execute(sa.update(models.SearchTask).where(
            models.SearchTask.id == task_id, models.SearchTask.attempt_token == token,
            models.SearchTask.status == 'running').values(attempt_token=None, lease_until=None))

    async def unpublished(self, session):
        return (await session.scalars(sa.select(models.SearchOutbox.task_id).where(
            models.SearchOutbox.published_at.is_(None)).order_by(models.SearchOutbox.task_id).limit(100))).all()

    async def published(self, session, task_id):
        await session.execute(sa.update(models.SearchOutbox).where(
            models.SearchOutbox.task_id == task_id).values(published_at=clock.now()))
