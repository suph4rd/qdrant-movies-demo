import sqlalchemy as sa
from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String(254), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text, nullable=False),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('blocked', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('user', 'admin')", name='user_role'))
    op.create_table('sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'])
    op.create_index('ix_sessions_expires_at', 'sessions', ['expires_at'])
    op.create_table('saved_movies',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('snapshot', sa.JSON, nullable=False))
    op.create_table('marks',
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('movie_id', sa.String(32), sa.ForeignKey('saved_movies.id'), primary_key=True),
        sa.Column('watched', sa.Boolean, nullable=False),
        sa.Column('liked', sa.Boolean, nullable=False),
        sa.Column('watchlist', sa.Boolean, nullable=False),
        sa.CheckConstraint('NOT (watched AND watchlist)', name='exclusive_watch_state'))


def downgrade():
    for table in ('marks', 'saved_movies', 'sessions', 'users'):
        op.drop_table(table)
