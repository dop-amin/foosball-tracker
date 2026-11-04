"""ELO rating calculation service.

All ELO numbers in the application are derived by replaying games in
chronological order through :func:`apply_game`. There is exactly one replay
implementation so that stored per-game changes, the leaderboard, and the
historical snapshots can never disagree with each other.
"""

from itertools import groupby
from sqlalchemy.orm import selectinload
from sqlalchemy import func
from models import db, Game, GamePlayer

INITIAL_ELO = 1500
K_FACTOR = 32


def calculate_elo_change(
    team1_rating, team2_rating, team1_score, team2_score, k_factor=K_FACTOR
):
    """
    Calculate ELO rating changes for both teams.

    Args:
        team1_rating: Average ELO rating of team 1
        team2_rating: Average ELO rating of team 2
        team1_score: Score of team 1
        team2_score: Score of team 2
        k_factor: K-factor for ELO calculation (default 32)

    Returns:
        Tuple of (team1_change, team2_change)
    """
    # Calculate expected scores
    expected_team1 = 1 / (1 + 10 ** ((team2_rating - team1_rating) / 400))
    expected_team2 = 1 / (1 + 10 ** ((team1_rating - team2_rating) / 400))

    # Actual scores (1 for win, 0 for loss)
    actual_team1 = 1 if team1_score > team2_score else 0
    actual_team2 = 1 if team2_score > team1_score else 0

    # Calculate rating changes
    team1_change = k_factor * (actual_team1 - expected_team1)
    team2_change = k_factor * (actual_team2 - expected_team2)

    return round(team1_change), round(team2_change)


def ordered_games(season_id=None):
    """
    Return games in deterministic chronological replay order.

    Games sharing the same start_time are ordered by id so every replay
    processes them identically. Players are eager-loaded to avoid N+1 queries.

    Args:
        season_id: Optional season ID. None returns games of all seasons.
    """
    query = Game.query.options(
        selectinload(Game.players)
    ).order_by(Game.start_time, Game.id)
    if season_id is not None:
        query = query.filter(Game.season_id == season_id)
    return query.all()


def apply_game(ratings, game):
    """
    Apply a single game's result to ``ratings`` in place.

    Team ratings are averaged before the calculation (2v2 and 2v1 games).

    Args:
        ratings: dict mapping player_id -> current rating (missing = INITIAL_ELO)
        game: Game with its GamePlayer rows loaded

    Returns:
        dict mapping team number (1/2) -> rating change applied to that team
    """
    team1 = [gp.player_id for gp in game.players if gp.team == 1]
    team2 = [gp.player_id for gp in game.players if gp.team == 2]
    if not team1 or not team2:
        raise ValueError(f"Game {game.id} does not have players on both teams")

    team1_avg = sum(ratings.get(pid, INITIAL_ELO) for pid in team1) / len(team1)
    team2_avg = sum(ratings.get(pid, INITIAL_ELO) for pid in team2) / len(team2)

    team1_change, team2_change = calculate_elo_change(
        team1_avg, team2_avg, game.team1_score, game.team2_score
    )

    for pid in team1:
        ratings[pid] = ratings.get(pid, INITIAL_ELO) + team1_change
    for pid in team2:
        ratings[pid] = ratings.get(pid, INITIAL_ELO) + team2_change

    return {1: team1_change, 2: team2_change}


def replay_games(games):
    """
    Replay games (already in chronological order) starting everyone at INITIAL_ELO.

    Returns:
        dict mapping player_id -> final rating (only players who played)
    """
    ratings = {}
    for game in games:
        apply_game(ratings, game)
    return ratings


def season_ratings(season_id):
    """
    Final ratings of a season, read from the stored per-game ELO changes.

    Returns:
        dict mapping player_id -> rating (only players who played the season)
    """
    rows = (
        db.session.query(GamePlayer.player_id, func.sum(GamePlayer.elo_change))
        .join(Game, GamePlayer.game_id == Game.id)
        .filter(Game.season_id == season_id)
        .group_by(GamePlayer.player_id)
    )
    return {player_id: INITIAL_ELO + (total or 0) for player_id, total in rows}


def replay_by_day(games):
    """
    Replay games (already in chronological order) and yield once per game day.

    Ratings start at INITIAL_ELO. The yielded ``ratings`` and ``games_played``
    dicts are live state that keeps changing after the next step; copy them if
    they need to be kept.

    Yields:
        (day, results, ratings, games_played) where ``results`` is a list of
        (game, changes) for that day's games, ``changes`` being the dict
        returned by :func:`apply_game`, ``ratings`` maps player_id -> rating
        and ``games_played`` maps player_id -> games played so far
    """
    ratings = {}
    games_played = {}
    for day, day_games in groupby(games, key=lambda g: g.start_time.date()):
        results = []
        for game in day_games:
            results.append((game, apply_game(ratings, game)))
            for gp in game.players:
                games_played[gp.player_id] = games_played.get(gp.player_id, 0) + 1
        yield day, results, ratings, games_played
