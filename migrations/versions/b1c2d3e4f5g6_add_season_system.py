"""Add season system

Revision ID: b1c2d3e4f5g6
Revises: a1b2c3d4e5f6
Create Date: 2026-02-13 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5g6'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # Step 1: Create season table
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

    # Create index on is_current for fast current season lookup
    op.create_index('ix_season_is_current', 'season', ['is_current'], unique=False)

    # Step 2: Add season_id columns (nullable initially)
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.add_column(sa.Column('season_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('cake_balance', schema=None) as batch_op:
        batch_op.add_column(sa.Column('season_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('leaderboard_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column('season_id', sa.Integer(), nullable=True))

    # Step 3: Create seasons based on actual game dates
    # Get connection to execute queries
    conn = op.get_bind()

    # Get min and max game dates
    result = conn.execute(sa.text("SELECT MIN(start_time), MAX(start_time) FROM game"))
    min_date, max_date = result.fetchone()

    if min_date and max_date:
        # Parse dates (handle both with and without microseconds)
        from datetime import datetime
        try:
            min_dt = datetime.strptime(min_date, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            min_dt = datetime.strptime(min_date, '%Y-%m-%d %H:%M:%S')

        try:
            max_dt = datetime.strptime(max_date, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            max_dt = datetime.strptime(max_date, '%Y-%m-%d %H:%M:%S')

        # Helper function to get quarter info
        def get_quarter(dt):
            month = dt.month
            year = dt.year
            quarter = (month - 1) // 3 + 1
            return year, quarter

        # Helper function to get quarter boundaries
        def get_quarter_boundaries(year, quarter):
            start_month = (quarter - 1) * 3 + 1
            if quarter == 4:
                end_month = 12
                end_day = 31
            else:
                end_month = start_month + 2
                if end_month == 3:
                    # February
                    if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                        end_day = 29
                    else:
                        end_day = 28
                elif end_month in [1, 3, 5, 7, 8, 10, 12]:
                    end_day = 31
                else:
                    end_day = 30

            start_date = f"{year}-{start_month:02d}-01 00:00:00"
            end_date = f"{year}-{end_month:02d}-{end_day} 23:59:59"
            return start_date, end_date

        # Create all necessary seasons
        start_year, start_quarter = get_quarter(min_dt)
        end_year, end_quarter = get_quarter(max_dt)

        current_year = start_year
        current_quarter = start_quarter

        # Determine which season should be current (the one containing max_date)
        current_season_name = f"Q{end_quarter} {end_year}"

        while (current_year < end_year) or (current_year == end_year and current_quarter <= end_quarter):
            season_name = f"Q{current_quarter} {current_year}"
            start_date, end_date = get_quarter_boundaries(current_year, current_quarter)
            is_current = 1 if season_name == current_season_name else 0

            op.execute(
                sa.text(
                    """
                    INSERT INTO season (name, start_date, end_date, is_current, created_at)
                    VALUES (:name, :start_date, :end_date, :is_current, datetime('now'))
                    """
                ).bindparams(
                    name=season_name,
                    start_date=start_date,
                    end_date=end_date,
                    is_current=is_current
                )
            )

            # Move to next quarter
            current_quarter += 1
            if current_quarter > 4:
                current_quarter = 1
                current_year += 1
    else:
        # No games exist, create current quarter as default
        from datetime import datetime
        now = datetime.utcnow()
        year = now.year
        quarter = (now.month - 1) // 3 + 1

        def get_quarter_boundaries(year, quarter):
            start_month = (quarter - 1) * 3 + 1
            if quarter == 4:
                end_month = 12
                end_day = 31
            else:
                end_month = start_month + 2
                if end_month in [1, 3, 5, 7, 8, 10, 12]:
                    end_day = 31
                else:
                    end_day = 30

            start_date = f"{year}-{start_month:02d}-01 00:00:00"
            end_date = f"{year}-{end_month:02d}-{end_day} 23:59:59"
            return start_date, end_date

        season_name = f"Q{quarter} {year}"
        start_date, end_date = get_quarter_boundaries(year, quarter)

        op.execute(
            sa.text(
                """
                INSERT INTO season (name, start_date, end_date, is_current, created_at)
                VALUES (:name, :start_date, :end_date, 1, datetime('now'))
                """
            ).bindparams(
                name=season_name,
                start_date=start_date,
                end_date=end_date
            )
        )

    # Step 4: Assign games to correct seasons based on their start_time
    # For each season, update games that fall within its date range
    seasons = conn.execute(sa.text("SELECT id, start_date, end_date FROM season"))
    for season_id, start_date, end_date in seasons:
        op.execute(
            sa.text(
                """
                UPDATE game
                SET season_id = :season_id
                WHERE start_time >= :start_date AND start_time <= :end_date
                """
            ).bindparams(
                season_id=season_id,
                start_date=start_date,
                end_date=end_date
            )
        )

    # Assign leaderboard_history to seasons based on snapshot_date
    seasons = conn.execute(sa.text("SELECT id, start_date, end_date FROM season"))
    for season_id, start_date, end_date in seasons:
        op.execute(
            sa.text(
                """
                UPDATE leaderboard_history
                SET season_id = :season_id
                WHERE snapshot_date >= date(:start_date) AND snapshot_date <= date(:end_date)
                """
            ).bindparams(
                season_id=season_id,
                start_date=start_date,
                end_date=end_date
            )
        )

    # For cake_balance, assign to the most recent season (since they don't have dates)
    # This will be recalculated properly when games are processed
    current_season = conn.execute(sa.text("SELECT id FROM season WHERE is_current = 1")).fetchone()
    if current_season:
        op.execute(
            sa.text("UPDATE cake_balance SET season_id = :season_id").bindparams(
                season_id=current_season[0]
            )
        )

    # Step 5: Make season_id non-nullable and add foreign keys
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.alter_column('season_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_game_season_id', 'season', ['season_id'], ['id'])
        batch_op.create_index('ix_game_season_id', ['season_id'], unique=False)

    with op.batch_alter_table('cake_balance', schema=None) as batch_op:
        batch_op.alter_column('season_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key('fk_cake_balance_season_id', 'season', ['season_id'], ['id'])
        batch_op.create_index('ix_cake_balance_season_id', ['season_id'], unique=False)

    # Step 6: Update leaderboard_history unique constraint and add foreign key
    # Check if unique_player_date constraint exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    constraints = {c['name'] for c in inspector.get_unique_constraints('leaderboard_history')}

    with op.batch_alter_table('leaderboard_history', schema=None) as batch_op:
        # Drop old unique constraint only if it exists
        if 'unique_player_date' in constraints:
            batch_op.drop_constraint('unique_player_date', type_='unique')

        # Make season_id non-nullable
        batch_op.alter_column('season_id', existing_type=sa.Integer(), nullable=False)
        # Add foreign key
        batch_op.create_foreign_key('fk_leaderboard_history_season_id', 'season', ['season_id'], ['id'])
        # Create new unique constraint including season_id
        batch_op.create_unique_constraint('unique_player_season_date', ['player_id', 'season_id', 'snapshot_date'])
        # Create index
        batch_op.create_index('ix_leaderboard_history_season_id', ['season_id'], unique=False)


def downgrade():
    # Remove indexes and foreign keys from leaderboard_history
    with op.batch_alter_table('leaderboard_history', schema=None) as batch_op:
        batch_op.drop_index('ix_leaderboard_history_season_id')
        batch_op.drop_constraint('unique_player_season_date', type_='unique')
        batch_op.drop_constraint('fk_leaderboard_history_season_id', type_='foreignkey')
        batch_op.create_unique_constraint('unique_player_date', ['player_id', 'snapshot_date'])
        batch_op.drop_column('season_id')

    # Remove indexes and foreign keys from cake_balance
    with op.batch_alter_table('cake_balance', schema=None) as batch_op:
        batch_op.drop_index('ix_cake_balance_season_id')
        batch_op.drop_constraint('fk_cake_balance_season_id', type_='foreignkey')
        batch_op.drop_column('season_id')

    # Remove indexes and foreign keys from game
    with op.batch_alter_table('game', schema=None) as batch_op:
        batch_op.drop_index('ix_game_season_id')
        batch_op.drop_constraint('fk_game_season_id', type_='foreignkey')
        batch_op.drop_column('season_id')

    # Drop season table
    op.drop_index('ix_season_is_current', table_name='season')
    op.drop_table('season')
