"""Leaderboard historical snapshot service."""

from datetime import date
from types import SimpleNamespace
from dateutil.relativedelta import relativedelta
from models import db, LeaderboardHistory, Player
from services.elo_service import ordered_games, replay_by_day

# Position history charts span at most this many months
POSITION_HISTORY_MONTHS = 6


def position_history_cutoff(end=None):
    """
    Earliest snapshot date shown in a position history chart ending at ``end``.

    Args:
        end: Last date of the chart (default: today)
    """
    return (end or date.today()) - relativedelta(months=POSITION_HISTORY_MONTHS)


def limit_to_history_window(snapshots):
    """
    Drop snapshots more than POSITION_HISTORY_MONTHS before the latest one.

    Args:
        snapshots: snapshot-like objects with a snapshot_date

    Returns:
        list of the remaining snapshots, in their original order
    """
    if not snapshots:
        return []
    cutoff = position_history_cutoff(max(s.snapshot_date for s in snapshots))
    return [s for s in snapshots if s.snapshot_date >= cutoff]


def extend_snapshots_to_present(snapshots):
    """
    Carry each season's last standings forward so chart lines reach the present.

    Snapshots only exist on days with games. For every season in ``snapshots``,
    the standings of its last snapshot day are repeated at the season's end
    date, or today if the season is still running.

    Args:
        snapshots: LeaderboardHistory rows

    Returns:
        list of snapshot-like objects (originals plus carried-forward copies),
        sorted by snapshot_date
    """
    today = date.today()
    last_day_by_season = {}
    for s in snapshots:
        if s.snapshot_date > last_day_by_season.get(s.season_id, date.min):
            last_day_by_season[s.season_id] = s.snapshot_date

    extended = list(snapshots)
    for s in snapshots:
        if s.snapshot_date != last_day_by_season[s.season_id]:
            continue
        end_day = min(s.season.end_date.date(), today)
        if end_day > s.snapshot_date:
            extended.append(SimpleNamespace(
                player_id=s.player_id,
                player=s.player,
                season_id=s.season_id,
                snapshot_date=end_day,
                rank=s.rank,
                elo_rating=s.elo_rating,
                total_games=s.total_games,
            ))
    extended.sort(key=lambda s: s.snapshot_date)
    return extended


def add_daily_snapshot(season_id, snapshot_date, ratings, games_played):
    """
    Add one day's leaderboard snapshot for a season to the session.

    Only players who have played at least one game in the season are ranked.

    Args:
        season_id: Season the snapshot belongs to
        snapshot_date: date of the snapshot
        ratings: dict player_id -> season ELO rating at the end of that day
        games_played: dict player_id -> games played in the season so far
    """
    standings = sorted(games_played, key=ratings.__getitem__, reverse=True)
    for rank, player_id in enumerate(standings, start=1):
        db.session.add(
            LeaderboardHistory(
                player_id=player_id,
                season_id=season_id,
                snapshot_date=snapshot_date,
                rank=rank,
                elo_rating=ratings[player_id],
                total_games=games_played[player_id],
            )
        )


def all_time_daily_standings(since=None):
    """
    Daily all-time standings, matching the all-time leaderboard.

    All games are replayed as one continuous ELO run (no season resets). For
    each day with games, and for today, every player who has played so far is
    included with their latest rating, so lines reach the present.

    Args:
        since: Optional date; earlier days are left out of the result (the
            replay still starts at the first game)

    Returns:
        list of snapshot-like objects with player_id, player, snapshot_date,
        elo_rating and total_games, sorted by snapshot_date
    """
    players = {p.id: p for p in Player.query.all()}
    standings = []

    def add_day(day, ratings, games_played):
        for player_id, rating in ratings.items():
            standings.append(SimpleNamespace(
                player_id=player_id,
                player=players[player_id],
                snapshot_date=day,
                elo_rating=rating,
                total_games=games_played[player_id],
            ))

    last_day, ratings, games_played = None, {}, {}
    for last_day, _, ratings, games_played in replay_by_day(ordered_games()):
        if since is None or last_day >= since:
            add_day(last_day, ratings, games_played)

    today = date.today()
    if last_day is not None and last_day < today:
        add_day(today, ratings, games_played)
    return standings
