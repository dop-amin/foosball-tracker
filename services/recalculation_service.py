"""Service for recalculating all data derived from the game history.

ELO changes, cake balances and leaderboard snapshots are all derived from
games. They are rebuilt per season by replaying that season's games, so every code
path that records or edits a game goes through :func:`recalculate_season`.
"""

from collections import defaultdict
from models import db, Season, CakeBalance, LeaderboardHistory
from services.elo_service import ordered_games, replay_by_day
from services.leaderboard_service import add_daily_snapshot


def recalculate_season(season, since=None):
    """
    Rebuild every derived value for one season (does not commit).

    - GamePlayer.elo_change for each game of the season
    - CakeBalance rows of the season (each loser owes each winner per shutout)
    - LeaderboardHistory snapshots of the season (one per day with games)

    Args:
        season: Season to rebuild
        since: Optional date. Only snapshots dated on or after it are
            rewritten (earlier days cannot be affected by a change at
            ``since``). All games are still replayed for correct ratings.
    """
    snapshots = LeaderboardHistory.query.filter_by(season_id=season.id)
    if since is not None:
        snapshots = snapshots.filter(LeaderboardHistory.snapshot_date >= since)
    snapshots.delete(synchronize_session=False)
    CakeBalance.query.filter_by(season_id=season.id).delete()

    cakes = defaultdict(int)
    for day, results, ratings, games_played in replay_by_day(ordered_games(season.id)):
        for game, changes in results:
            for gp in game.players:
                gp.elo_change = changes[gp.team]

            if game.is_shutout:
                winners = [gp.player_id for gp in game.players if gp.is_winner]
                losers = [gp.player_id for gp in game.players if not gp.is_winner]
                for loser_id in losers:
                    for winner_id in winners:
                        cakes[(loser_id, winner_id)] += 1

        if since is None or day >= since:
            add_daily_snapshot(season.id, day, ratings, games_played)

    for (debtor_id, creditor_id), balance in cakes.items():
        db.session.add(
            CakeBalance(
                season_id=season.id,
                debtor_id=debtor_id,
                creditor_id=creditor_id,
                balance=balance,
            )
        )


def recalculate_all_derived_data(season_id=None, commit=True, since=None):
    """
    Recalculate all derived data (ELO, cake balances, leaderboard history).
    Must be called after recording or editing any game.

    Args:
        season_id: Optional season ID to recalculate. If None, every season is
                   recalculated (each starting from INITIAL_ELO).
        commit: Commit the session afterwards (default True).
        since: Optional date passed to :func:`recalculate_season` (only with
               ``season_id``): the earliest day affected by the change.
    """
    if season_id is not None:
        recalculate_season(db.session.get(Season, season_id), since=since)
    else:
        for season in Season.query.order_by(Season.start_date):
            recalculate_season(season)

    if commit:
        db.session.commit()
