from backend.api.application import dtos
from backend.api.application import errors
from backend.api.application.services import account
from backend.api.infrastructure import clock
from backend.api.infrastructure import passwords
from backend.api.infrastructure.repositories import sessions, users


PAGE_SIZE = 20


class AdminService:
    def __init__(self, session_factory, account_service, user_repository=None, session_repository=None):
        self.sessions = session_factory
        self.account = account_service
        self.users = user_repository or users.UserRepository()
        self.tokens = session_repository or sessions.SessionRepository()

    async def list_users(self, query, role, state, page):
        if role not in ('', 'user', 'admin') or state not in ('', 'active', 'blocked', 'deleted'):
            raise errors.ScenarioError('Invalid user filters.')
        async with self.sessions() as session:
            rows = await self.users.list(session, query, role, state, (page - 1) * PAGE_SIZE, PAGE_SIZE + 1)
            return dtos.UserPage([dtos.User.from_record(user) for user in rows[:PAGE_SIZE]], len(rows) > PAGE_SIZE)

    async def detail(self, user_id, page):
        async with self.sessions() as session:
            user = await self.users.get(session, user_id)
            if user is None:
                raise errors.UserNotFound()
            lists = [await self.account.movie_list(session, user_id, flag, page) for flag in account.FLAGS]
            return dtos.UserDetail(dtos.User.from_record(user), lists)

    async def change_user(self, token, user_id, action, confirmation=''):
        async with self.sessions() as session, session.begin():
            await self.users.admin_lock(session)
            actor = await self.tokens.user(session, passwords.token_hash(token), lock=True)
            if actor is None:
                raise errors.AuthenticationRequired()
            if actor.role != 'admin':
                raise errors.AdministratorRequired()
            target = await self.users.get(session, user_id, lock=True)
            if target is None:
                raise errors.UserNotFound()
            if action not in ('block', 'unblock', 'promote', 'demote', 'delete', 'restore'):
                raise errors.ScenarioError('Invalid user action.')
            if actor.id == target.id and action in ('block', 'delete', 'demote'):
                raise errors.ScenarioError('You cannot block, delete, or demote yourself.')
            if action == 'delete' and (not isinstance(confirmation, str)
                                       or confirmation.strip().casefold() != target.email):
                raise errors.ScenarioError('The confirmation email does not match.')
            if target.deleted_at is not None and action not in ('restore', 'delete'):
                raise errors.ScenarioError('Invalid user action.')
            if action == 'restore' and target.deleted_at is None:
                raise errors.ScenarioError('Invalid user action.')
            if (target.role == 'admin' and not target.blocked and target.deleted_at is None
                    and action in ('block', 'delete', 'demote')):
                count = await self.users.active_admin_count(session)
                if count <= 1:
                    raise errors.ScenarioError('The last active administrator must be preserved.')
            if action in ('block', 'unblock'):
                target.blocked = action == 'block'
            elif action in ('promote', 'demote'):
                target.role = 'admin' if action == 'promote' else 'user'
            elif action == 'delete':
                target.deleted_at = target.deleted_at or clock.now()
                target.blocked = True
            elif action == 'restore':
                target.deleted_at = None
                target.blocked = True
            if action in ('block', 'delete', 'restore'):
                await self.tokens.revoke(session, target.id)
