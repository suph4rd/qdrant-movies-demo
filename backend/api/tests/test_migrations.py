from pathlib import Path
import asyncio
import os
import sys
import unittest
import uuid

from sqlalchemy.ext import asyncio as sa_async
import sqlalchemy as sa

from backend.api.infrastructure import database
from backend.api.infrastructure import models


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Requires a separate PostgreSQL database')
class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_database_repeat_upgrade_and_reconnect(self):
        schema = 'migration_test_' + uuid.uuid4().hex
        control = sa_async.create_async_engine(os.environ['TEST_DATABASE_URL'])
        db = None
        try:
            async with control.begin() as connection:
                await connection.execute(sa.text('CREATE SCHEMA ' + schema))
            url = sa.engine.make_url(os.environ['TEST_DATABASE_URL']).update_query_dict(
                {'options': '-csearch_path=' + schema}).render_as_string(hide_password=False)
            env = {**os.environ, 'DATABASE_URL': url}
            for _ in range(2):
                process = await asyncio.create_subprocess_exec(
                    sys.executable, '-m', 'alembic', '-c', 'backend/api/alembic.ini', 'upgrade', 'head',
                    cwd=Path(__file__).resolve().parents[3], env=env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, stderr = await process.communicate()
                self.assertEqual(process.returncode, 0, (stdout + stderr).decode())
            db = database.Database(url)
            async with db.engine.connect() as connection:
                tables = await connection.run_sync(lambda sync: sa.inspect(sync).get_table_names(schema=schema))
                self.assertEqual(set(tables), {'alembic_version', 'users', 'sessions', 'saved_movies', 'marks', 'search_owners', 'search_tasks', 'search_outbox'})
                self.assertEqual(await connection.scalar(sa.text('SELECT version_num FROM alembic_version')), '0002')
            async with db.sessions.begin() as session:
                user = models.User(email='persist@example.com', password_hash='test-only')
                session.add(user)
                await session.flush()
                user_id = user.id
            await db.close()
            db = database.Database(url)
            async with db.sessions() as session:
                self.assertEqual((await session.get(models.User, user_id)).email, 'persist@example.com')
        finally:
            if db is not None:
                await db.close()
            async with control.begin() as connection:
                await connection.execute(sa.text('DROP SCHEMA ' + schema + ' CASCADE'))
            await control.dispose()
