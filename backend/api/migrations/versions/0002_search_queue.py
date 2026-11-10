import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('search_owners',
        sa.Column('id', sa.String(80), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), unique=True))
    op.create_table('search_tasks',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('owner_id', sa.String(80), sa.ForeignKey('search_owners.id'), nullable=False),
        sa.Column('query', sa.Text, nullable=False),
        sa.Column('mode', sa.String(16), nullable=False),
        sa.Column('limit', sa.String(2), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('result', sa.JSON), sa.Column('error', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('read_at', sa.DateTime(timezone=True)),
        sa.Column('attempt_token', sa.String(32)),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name='search_task_status'))
    op.create_index('ix_search_tasks_owner_id', 'search_tasks', ['owner_id'])
    op.create_index('uq_search_tasks_active_owner', 'search_tasks', ['owner_id'], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'running')"))
    op.create_table('search_outbox',
        sa.Column('task_id', sa.String(32), sa.ForeignKey('search_tasks.id'), primary_key=True),
        sa.Column('published_at', sa.DateTime(timezone=True)))


def downgrade():
    op.drop_table('search_outbox')
    op.drop_table('search_tasks')
    op.drop_table('search_owners')
