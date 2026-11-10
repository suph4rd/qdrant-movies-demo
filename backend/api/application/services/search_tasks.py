from backend.api.infrastructure import clock, passwords
from backend.api.infrastructure.repositories import search_tasks


def owners(user_id, guest_token):
    result = {}
    if guest_token:
        result['g:' + passwords.token_hash(guest_token)] = None
    if user_id is not None:
        result['u:' + str(user_id)] = user_id
    return result


class SearchTaskService:
    def __init__(self, sessions):
        self.sessions = sessions
        self.repository = search_tasks.SearchTaskRepository()

    async def submit(self, params, user_id, guest_token):
        params = {**params, 'q': params['q'].strip()}
        identities = owners(user_id, guest_token)
        target = 'u:' + str(user_id) if user_id is not None else next(iter(identities))
        async with self.sessions() as session, session.begin():
            await self.repository.lock_owners(session, identities)
            active = await self.repository.active(session, identities)
            for task in active:
                if (task.query, task.mode, task.limit) == (params['q'], params['mode'], params['limit']):
                    return task, False
            if active:
                return active[0], True
            return await self.repository.add(session, target, params), False

    async def list(self, user_id, guest_token):
        async with self.sessions() as session:
            return await self.repository.visible(session, owners(user_id, guest_token))

    async def get(self, task_id, user_id, guest_token, read=False):
        async with self.sessions() as session, session.begin():
            task = await self.repository.visible(session, owners(user_id, guest_token), task_id)
            if task is not None and read and task.status in search_tasks.TERMINAL:
                task.read_at = clock.now()
            return task
