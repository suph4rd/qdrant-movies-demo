import asyncio

from alembic import context
from sqlalchemy.ext import asyncio as sa_async

from backend.api import config as web_config
from backend.api.infrastructure import models


config = context.config
target_metadata = models.Base.metadata


def migrate(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run():
    engine = sa_async.create_async_engine(web_config.Settings().database_url)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=web_config.Settings().database_url, target_metadata=target_metadata,
                      literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run())
