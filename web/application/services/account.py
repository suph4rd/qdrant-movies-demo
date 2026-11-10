from engine import errors as engine_errors, imports
from web.application import dtos
from web.application import errors
from web.application import movie_snapshots
from web.infrastructure.repositories import marks, users


PAGE_SIZE = 20
FLAGS = ('watched', 'liked', 'watchlist')
LABELS = {'watched': 'Watched', 'liked': 'Liked', 'watchlist': 'Watchlist'}


def apply_mark(mark, flag, state):
    if flag not in FLAGS or type(state) is not bool:
        raise ValueError('Invalid movie mark')
    setattr(mark, flag, state)
    if state and flag == 'watched':
        mark.watchlist = False
    elif state and flag == 'watchlist':
        mark.watched = False
    return mark


class AccountService:
    def __init__(self, session_factory, catalog, cards, user_repository=None, mark_repository=None):
        self.sessions = session_factory
        self.catalog = catalog
        self.cards = cards
        self.users = user_repository or users.UserRepository()
        self.marks = mark_repository or marks.MarkRepository()

    async def all_marks(self, user_id):
        async with self.sessions() as session:
            return {mark.movie_id: dtos.Mark.from_record(mark)
                    for mark in await self.marks.all(session, user_id)}

    async def lists(self, user_id, flag, page):
        if flag not in FLAGS or not 1 <= page <= 1000000:
            raise errors.ScenarioError('Invalid page number.')
        async with self.sessions() as session:
            return [await self.movie_list(session, user_id, item, page if item == flag else 1)
                    for item in FLAGS]

    async def movie_list(self, session, user_id, flag, page):
        count, rows = await self.marks.list(session, user_id, flag, (page - 1) * PAGE_SIZE, PAGE_SIZE)
        return dtos.MovieList(flag, page, count, [
            (saved.snapshot, dtos.Mark.from_record(mark)) for saved, mark in rows])

    async def update_mark(self, user_id, movie_id, flag, state, reference=''):
        if flag not in FLAGS or type(state) is not bool:
            raise errors.ScenarioError('Invalid movie mark.')
        invalid = 'Invalid movie selection. Search for the movie again.'
        if (not isinstance(movie_id, str) or not movie_id.isascii() or not movie_id.isdecimal()
                or len(movie_id) > 20 or int(movie_id) > 2**64 - 1):
            raise errors.ScenarioError(invalid)
        movie_id = str(int(movie_id))
        snapshot = next((movie_snapshots.clean_snapshot(item) for item in self.catalog
                         if str(item['id']) == movie_id), None)
        if snapshot is None and isinstance(reference, str):
            candidate = self.cards.get(reference)
            if candidate and str(candidate['id']) == movie_id:
                try:
                    imports.validate_movie(candidate)
                except Exception as exc:
                    if not engine_errors.is_expected_error(exc):
                        raise
                    raise errors.ScenarioError(invalid) from exc
                snapshot = candidate
        async with self.sessions.begin() as session:
            # Serialize this user's updates, including concurrent first marks for a film.
            user = await self.users.lock(session, user_id)
            if user is None or user.blocked or user.deleted_at is not None:
                raise errors.AuthenticationRequired()
            saved = await self.marks.saved(session, movie_id)
            if saved is None:
                if snapshot is None:
                    raise errors.ScenarioError(invalid)
                await self.marks.save(session, movie_id, snapshot)
            mark = await self.marks.get_or_create(session, user_id, movie_id)
            apply_mark(mark, flag, state)
