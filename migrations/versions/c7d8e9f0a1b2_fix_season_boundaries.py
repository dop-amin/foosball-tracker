"""Fix season boundaries and game season assignment

Earlier versions computed the end of Q1 as Feb 28/29 instead of Mar 31, so
existing databases may contain Q1 seasons with a wrong end_date and games
assigned to the wrong season. This data migration:

1. Recomputes start_date/end_date of every season from its "Q<n> <year>" name.
2. Re-assigns every game to the season of its start_time quarter (creating
   missing seasons).

Derived data (ELO changes, cake balances, leaderboard snapshots) is rebuilt
by running ``python recalculate_elo.py`` after the upgrade.

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5g6
Create Date: 2026-11-04 12:00:00.000000

"""
import calendar
import re
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d8e9f0a1b2'
down_revision = 'b1c2d3e4f5g6'
branch_labels = None
depends_on = None


SEASON_NAME = re.compile(r"^Q([1-4]) (\d{4})$")


def get_quarter_boundaries(year, quarter):
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    end_day = calendar.monthrange(year, end_month)[1]
    start_date = f"{year}-{start_month:02d}-01 00:00:00.000000"
    end_date = f"{year}-{end_month:02d}-{end_day:02d} 23:59:59.000000"
    return start_date, end_date


def upgrade():
    conn = op.get_bind()

    # Step 1: Fix boundaries of existing seasons
    season_ids = {}
    for season_id, name in conn.execute(sa.text("SELECT id, name FROM season")).fetchall():
        season_ids[name] = season_id
        match = SEASON_NAME.match(name)
        if not match:
            continue
        quarter, year = int(match.group(1)), int(match.group(2))
        start_date, end_date = get_quarter_boundaries(year, quarter)
        conn.execute(
            sa.text(
                "UPDATE season SET start_date = :start_date, end_date = :end_date WHERE id = :id"
            ),
            {"start_date": start_date, "end_date": end_date, "id": season_id},
        )

    # Step 2: Re-assign games to the season of their start_time quarter
    games = conn.execute(
        sa.text(
            """
            SELECT id, season_id,
                   CAST(strftime('%Y', start_time) AS INTEGER) AS year,
                   CAST(strftime('%m', start_time) AS INTEGER) AS month
            FROM game
            """
        )
    ).fetchall()

    for game_id, season_id, year, month in games:
        quarter = (month - 1) // 3 + 1
        name = f"Q{quarter} {year}"
        if name not in season_ids:
            start_date, end_date = get_quarter_boundaries(year, quarter)
            conn.execute(
                sa.text(
                    """
                    INSERT INTO season (name, start_date, end_date, is_current, created_at)
                    VALUES (:name, :start_date, :end_date, 0, datetime('now'))
                    """
                ),
                {"name": name, "start_date": start_date, "end_date": end_date},
            )
            season_ids[name] = conn.execute(
                sa.text("SELECT id FROM season WHERE name = :name"), {"name": name}
            ).scalar_one()

        if season_id != season_ids[name]:
            conn.execute(
                sa.text("UPDATE game SET season_id = :season_id WHERE id = :id"),
                {"season_id": season_ids[name], "id": game_id},
            )


def downgrade():
    # Pure data fix; the previous (incorrect) boundaries are not restored.
    pass
