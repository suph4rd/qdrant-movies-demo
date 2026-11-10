from sqlalchemy.dialects import postgresql
import sqlalchemy as sa

from backend.api.infrastructure import models


class MarkRepository:
    async def all(self, session, user_id):
        return list(await session.scalars(sa.select(models.Mark).where(models.Mark.user_id == user_id)))

    async def list(self, session, user_id, flag, offset, limit):
        statement = sa.select(models.SavedMovie, models.Mark).join(
            models.Mark, models.Mark.movie_id == models.SavedMovie.id).where(
            models.Mark.user_id == user_id, getattr(models.Mark, flag).is_(True))
        count = await session.scalar(sa.select(sa.func.count()).select_from(statement.subquery()))
        rows = (await session.execute(statement.order_by(models.SavedMovie.id).offset(
            offset).limit(limit))).all()
        return count, rows

    async def saved(self, session, movie_id):
        return await session.get(models.SavedMovie, movie_id)

    async def save(self, session, movie_id, snapshot):
        await session.execute(postgresql.insert(models.SavedMovie).values(
            id=movie_id, snapshot=snapshot).on_conflict_do_nothing(index_elements=['id']))

    async def get_or_create(self, session, user_id, movie_id):
        mark = await session.get(models.Mark, (user_id, movie_id))
        if mark is None:
            mark = models.Mark(user_id=user_id, movie_id=movie_id,
                                watched=False, liked=False, watchlist=False)
            session.add(mark)
        return mark
