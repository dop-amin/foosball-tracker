"""Create all tables with seasons

Revision ID: a1b2c3d4e5f6
Revises: 95dfed98d8cf
Create Date: 2025-11-14 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '95dfed98d8cf'
branch_labels = None
depends_on = None


def get_quarter_info(date):
    """Get quarter number and year for a given date."""
    quarter = (date.month - 1) // 3 + 1
    year = date.year
    return quarter, year


def get_quarter_start_end(year, quarter):
    """Get start and end dates for a given quarter."""
    start_month = (quarter - 1) * 3 + 1
    start_date = datetime(year, start_month, 1, 0, 0, 0)

    # Calculate end date (last day of the quarter)
    if quarter == 4:
        end_date = datetime(year + 1, 1, 1, 0, 0, 0) - timedelta(seconds=1)
    else:
        end_month = start_month + 3
        end_date = datetime(year, end_month, 1, 0, 0, 0) - timedelta(seconds=1)

    return start_date, end_date


def upgrade():
    # Create Season table
    op.create_table('season',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )

    # Add season_id to game table
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.add_column(sa.Column('season_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_game_season', 'season', ['season_id'], ['id'])

    # Add season_id to cake_balance table
    with op.batch_alter_table('cake_balance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('season_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_cake_balance_season', 'season', ['season_id'], ['id'])

    # Add season_id to leaderboard_history table and update unique constraint
    with op.batch_alter_table('leaderboard_history', schema=None) as batch_op:
        batch_op.drop_constraint('unique_player_date', type_='unique')
        batch_op.add_column(sa.Column('season_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_leaderboard_history_season', 'season', ['season_id'], ['id'])
        batch_op.create_unique_constraint('unique_player_season_date', ['player_id', 'season_id', 'snapshot_date'])

    # Create the first season (current quarter)
    conn = op.get_bind()
    now = datetime.utcnow()
    quarter, year = get_quarter_info(now)
    start_date, end_date = get_quarter_start_end(year, quarter)
    season_name = f"Q{quarter} {year}"

    conn.execute(
        sa.text("""
            INSERT INTO season (name, start_date, end_date, is_current, created_at)
            VALUES (:name, :start_date, :end_date, :is_current, :created_at)
        """),
        {
            "name": season_name,
            "start_date": start_date,
            "end_date": end_date,
            "is_current": True,
            "created_at": now
        }
    )

    # Get the season ID
    result = conn.execute(sa.text("SELECT id FROM season WHERE name = :name"), {"name": season_name})
    season_id = result.fetchone()[0]

    # Assign all existing games to the current season
    conn.execute(
        sa.text("UPDATE game SET season_id = :season_id WHERE season_id IS NULL"),
        {"season_id": season_id}
    )

    # Assign all existing cake balances to the current season
    conn.execute(
        sa.text("UPDATE cake_balance SET season_id = :season_id WHERE season_id IS NULL"),
        {"season_id": season_id}
    )

    # Assign all existing leaderboard history to the current season
    conn.execute(
        sa.text("UPDATE leaderboard_history SET season_id = :season_id WHERE season_id IS NULL"),
        {"season_id": season_id}
    )

    # Make season_id NOT NULL after populating existing data
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.alter_column('season_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('cake_balance', schema=None) as batch_op:
        batch_op.alter_column('season_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('leaderboard_history', schema=None) as batch_op:
        batch_op.alter_column('season_id', existing_type=sa.Integer(), nullable=False)


def downgrade():
    # Remove season_id from leaderboard_history and restore old unique constraint
    with op.batch_alter_table('leaderboard_history', schema=None) as batch_op:
        batch_op.drop_constraint('unique_player_season_date', type_='unique')
        batch_op.drop_constraint('fk_leaderboard_history_season', type_='foreignkey')
        batch_op.drop_column('season_id')
        batch_op.create_unique_constraint('unique_player_date', ['player_id', 'snapshot_date'])

    # Remove season_id from cake_balance
    with op.batch_alter_table('cake_balance', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cake_balance_season', type_='foreignkey')
        batch_op.drop_column('season_id')

    # Remove season_id from game
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.drop_constraint('fk_game_season', type_='foreignkey')
        batch_op.drop_column('season_id')

    # Drop season table
    op.drop_table('season')
