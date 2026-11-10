from datetime import datetime

from sqlalchemy import orm
import sqlalchemy as sa

from backend.api.infrastructure import clock


class Base(orm.DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: orm.Mapped[int] = orm.mapped_column(primary_key=True)
    email: orm.Mapped[str] = orm.mapped_column(sa.String(254), unique=True)
    password_hash: orm.Mapped[str] = orm.mapped_column(sa.Text)
    role: orm.Mapped[str] = orm.mapped_column(sa.String(16), default='user')
    blocked: orm.Mapped[bool] = orm.mapped_column(default=False)
    created_at: orm.Mapped[datetime] = orm.mapped_column(sa.DateTime(timezone=True), default=clock.now)
    deleted_at: orm.Mapped[datetime | None] = orm.mapped_column(sa.DateTime(timezone=True))
    __table_args__ = (sa.CheckConstraint("role IN ('user', 'admin')", name='user_role'),)


class Session(Base):
    __tablename__ = 'sessions'
    token_hash: orm.Mapped[str] = orm.mapped_column(sa.String(64), primary_key=True)
    user_id: orm.Mapped[int] = orm.mapped_column(sa.ForeignKey('users.id'), index=True)
    expires_at: orm.Mapped[datetime] = orm.mapped_column(sa.DateTime(timezone=True), index=True)


class SavedMovie(Base):
    __tablename__ = 'saved_movies'
    id: orm.Mapped[str] = orm.mapped_column(sa.String(32), primary_key=True)
    snapshot: orm.Mapped[dict] = orm.mapped_column(sa.JSON)


class Mark(Base):
    __tablename__ = 'marks'
    user_id: orm.Mapped[int] = orm.mapped_column(sa.ForeignKey('users.id'), primary_key=True)
    movie_id: orm.Mapped[str] = orm.mapped_column(sa.ForeignKey('saved_movies.id'), primary_key=True)
    watched: orm.Mapped[bool] = orm.mapped_column(default=False)
    liked: orm.Mapped[bool] = orm.mapped_column(default=False)
    watchlist: orm.Mapped[bool] = orm.mapped_column(default=False)
    __table_args__ = (sa.CheckConstraint('NOT (watched AND watchlist)', name='exclusive_watch_state'),)


