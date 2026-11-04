"""Convert tournament game times from UTC to local time

Tournament matches used to store their game's start_time as the UTC wall-clock
time, while all other games store naive local time (entered via datetime-local
inputs). This data migration converts the start/end times of all games linked
to a tournament match to local time (the timezone of the machine running the
migration) and moves them to the season of their corrected quarter.

Derived data (ELO changes, cake balances, leaderboard snapshots) is rebuilt
when the app starts, or by running ``python recalculate_elo.py``.

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
Create Date: 2026-11-04 18:00:00.000000

"""
import calendar
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def _utc_to_local(value):
    return value.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def _local_to_utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _season_id(conn, season_ids, moment):
    quarter = (moment.month - 1) // 3 + 1
    name = f"Q{quarter} {moment.year}"
    if name not in season_ids:
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        end_day = calendar.monthrange(moment.year, end_month)[1]
        conn.execute(
            sa.text(
                """
                INSERT INTO season (name, start_date, end_date, is_current, created_at)
                VALUES (:name, :start_date, :end_date, 0, datetime('now'))
                """
            ),
            {
                "name": name,
                "start_date": f"{moment.year}-{start_month:02d}-01 00:00:00.000000",
                "end_date": f"{moment.year}-{end_month:02d}-{end_day:02d} 23:59:59.000000",
            },
        )
        season_ids[name] = conn.execute(
            sa.text("SELECT id FROM season WHERE name = :name"), {"name": name}
        ).scalar_one()
    return season_ids[name]


def _convert(convert):
    conn = op.get_bind()
    season_ids = dict(
        (name, season_id)
        for season_id, name in conn.execute(sa.text("SELECT id, name FROM season"))
    )
    game = sa.table(
        "game",
        sa.column("id", sa.Integer),
        sa.column("season_id", sa.Integer),
        sa.column("start_time", sa.DateTime),
        sa.column("end_time", sa.DateTime),
    )
    match = sa.table("tournament_match", sa.column("game_id", sa.Integer))

    rows = conn.execute(
        sa.select(game.c.id, game.c.start_time, game.c.end_time).where(
            game.c.id.in_(
                sa.select(match.c.game_id).where(match.c.game_id.isnot(None))
            )
        )
    ).fetchall()

    for game_id, start_time, end_time in rows:
        start_time = convert(start_time)
        end_time = convert(end_time) if end_time is not None else None
        conn.execute(
            game.update()
            .where(game.c.id == game_id)
            .values(
                start_time=start_time,
                end_time=end_time,
                season_id=_season_id(conn, season_ids, start_time),
            )
        )


def upgrade():
    _convert(_utc_to_local)


def downgrade():
    _convert(_local_to_utc)
