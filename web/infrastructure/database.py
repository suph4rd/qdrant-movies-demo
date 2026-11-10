from sqlalchemy.ext import asyncio as sa_async


class Database:
    def __init__(self, url):
        self.engine = sa_async.create_async_engine(url, pool_pre_ping=True)
        self.sessions = sa_async.async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self):
        await self.engine.dispose()
