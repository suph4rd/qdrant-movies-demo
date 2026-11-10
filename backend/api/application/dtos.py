from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    id: int
    email: str
    role: str
    blocked: bool
    created_at: datetime
    deleted_at: datetime | None

    @classmethod
    def from_record(cls, record):
        return cls(**{name: getattr(record, name) for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Mark:
    movie_id: str
    watched: bool
    liked: bool
    watchlist: bool

    @classmethod
    def from_record(cls, record):
        return cls(**{name: getattr(record, name) for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class MovieList:
    flag: str
    page: int
    total: int
    movies: list


@dataclass(frozen=True)
class UserPage:
    users: list[User]
    has_next: bool


@dataclass(frozen=True)
class UserDetail:
    user: User
    lists: list[MovieList]
