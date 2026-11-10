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



class SearchOwner(Base):
    __tablename__ = 'search_owners'
    id: orm.Mapped[str] = orm.mapped_column(sa.String(80), primary_key=True)
    user_id: orm.Mapped[int | None] = orm.mapped_column(sa.ForeignKey('users.id'), unique=True)


class SearchTask(Base):
    __tablename__ = 'search_tasks'
    id: orm.Mapped[str] = orm.mapped_column(sa.String(32), primary_key=True)
    owner_id: orm.Mapped[str] = orm.mapped_column(sa.ForeignKey('search_owners.id'), index=True)
    query: orm.Mapped[str] = orm.mapped_column(sa.Text)
    mode: orm.Mapped[str] = orm.mapped_column(sa.String(16))
    limit: orm.Mapped[str] = orm.mapped_column(sa.String(2))
    status: orm.Mapped[str] = orm.mapped_column(sa.String(16), default='queued')
    result: orm.Mapped[dict | None] = orm.mapped_column(sa.JSON)
    error: orm.Mapped[dict | None] = orm.mapped_column(sa.JSON)
    created_at: orm.Mapped[datetime] = orm.mapped_column(sa.DateTime(timezone=True), default=clock.now)
    completed_at: orm.Mapped[datetime | None] = orm.mapped_column(sa.DateTime(timezone=True))
    read_at: orm.Mapped[datetime | None] = orm.mapped_column(sa.DateTime(timezone=True))
    attempt_token: orm.Mapped[str | None] = orm.mapped_column(sa.String(32))
    lease_until: orm.Mapped[datetime | None] = orm.mapped_column(sa.DateTime(timezone=True))
    __table_args__ = (
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name='search_task_status'),
        sa.Index('uq_search_tasks_active_owner', 'owner_id', unique=True,
                 postgresql_where=sa.text("status IN ('queued', 'running')")),
    )


class SearchOutbox(Base):
    __tablename__ = 'search_outbox'
    task_id: orm.Mapped[str] = orm.mapped_column(sa.ForeignKey('search_tasks.id'), primary_key=True)
    published_at: orm.Mapped[datetime | None] = orm.mapped_column(sa.DateTime(timezone=True))
