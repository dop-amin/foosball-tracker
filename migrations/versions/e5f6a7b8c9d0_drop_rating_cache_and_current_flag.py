"""Drop Player.elo_rating and Season.is_current

Both were caches of derived information: the current season is the season of
today's quarter, and season ratings are the sum of the stored per-game ELO
changes (GamePlayer.elo_change).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-04 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('season', schema=None) as batch_op:
        batch_op.drop_index('ix_season_is_current')
        batch_op.drop_column('is_current')

    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.drop_column('elo_rating')


def downgrade():
    # Values are refilled by `python recalculate_elo.py` on the old code
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.add_column(sa.Column('elo_rating', sa.Integer(), nullable=False, server_default='1500'))

    with op.batch_alter_table('season', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_current', sa.Boolean(), nullable=True))
        batch_op.create_index('ix_season_is_current', ['is_current'], unique=False)
