"""Leaderboard calculation and historical snapshot service."""

from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import func
from models import db, Player, GamePlayer, LeaderboardHistory, Game, Season
from services.elo_service import calculate_elo_change


def create_daily_snapshot(season_id, snapshot_date=None):
    """
    Create a daily snapshot of the leaderboard for all players in a season.
    Stores each player's rank, ELO rating, and total games count.

    Args:
        season_id: ID of the season to snapshot
        snapshot_date: Date to create snapshot for (defaults to today)
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    # Calculate current leaderboard statistics for this season
    players_stats = []
    players = Player.query.all()

    for player in players:
        # Count games for this player in this season
        total_games = db.session.query(func.count(GamePlayer.id)).join(Game).filter(
            GamePlayer.player_id == player.id,
            Game.season_id == season_id
        ).scalar()

        # Only include players who have played at least one game
        if total_games > 0:
            players_stats.append({
                "player_id": player.id,
                "elo_rating": player.elo_rating,
                "total_games": total_games,
            })

    # Sort by ELO rating (highest first) to determine ranks
    players_stats.sort(key=lambda x: x["elo_rating"], reverse=True)

    # Store snapshots for each player
    for rank, player_stat in enumerate(players_stats, start=1):
        # Check if snapshot already exists
        existing = LeaderboardHistory.query.filter_by(
            player_id=player_stat["player_id"],
            season_id=season_id,
            snapshot_date=snapshot_date
        ).first()

        if existing:
            # Update existing snapshot
            existing.rank = rank
            existing.elo_rating = player_stat["elo_rating"]
            existing.total_games = player_stat["total_games"]
        else:
            # Create new snapshot
            snapshot = LeaderboardHistory(
                player_id=player_stat["player_id"],
                season_id=season_id,
                snapshot_date=snapshot_date,
                rank=rank,
                elo_rating=player_stat["elo_rating"],
                total_games=player_stat["total_games"]
            )
            db.session.add(snapshot)

    db.session.commit()


def recalculate_historical_snapshots():
    """
    Recalculate all historical leaderboard snapshots from game history.
    Clears existing snapshots and rebuilds them by replaying all games.
    Creates one snapshot per day where games were played, per season.
    """
    # Clear existing snapshots
    LeaderboardHistory.query.delete()

    # Get all seasons in chronological order
    seasons = Season.query.order_by(Season.start_date).all()

    if not seasons:
        db.session.commit()
        return

    # Process each season separately
    for season in seasons:
        # Reset player ratings and game counts for this season
        players = Player.query.all()
        player_elo = {player.id: 1500 for player in players}
        player_games_count = {player.id: 0 for player in players}

        # Get all games for this season in chronological order
        games = Game.query.filter_by(season_id=season.id).order_by(Game.start_time).all()

        if not games:
            continue

        # Group games by date
        games_by_date = defaultdict(list)
        for game in games:
            game_date = game.start_time.date()
            games_by_date[game_date].append(game)

        # Process games chronologically by date
        sorted_dates = sorted(games_by_date.keys())

        for game_date in sorted_dates:
            # Process all games for this date
            for game in games_by_date[game_date]:
                # Get team players
                team1_players = []
                team2_players = []

                for gp in game.players:
                    if gp.team == 1:
                        team1_players.append(gp.player_id)
                    else:
                        team2_players.append(gp.player_id)

                    # Increment games count
                    player_games_count[gp.player_id] = player_games_count.get(gp.player_id, 0) + 1

                # Calculate average team ratings
                team1_avg_rating = sum(player_elo[pid] for pid in team1_players) / len(team1_players)
                team2_avg_rating = sum(player_elo[pid] for pid in team2_players) / len(team2_players)

                # Calculate ELO changes
                team1_change, team2_change = calculate_elo_change(
                    team1_avg_rating, team2_avg_rating, game.team1_score, game.team2_score
                )

                # Update player ELO ratings in memory
                for pid in team1_players:
                    player_elo[pid] += team1_change

                for pid in team2_players:
                    player_elo[pid] += team2_change

            # Create snapshot for this date (after all games for the day)
            players_stats = []
            for player_id, elo_rating in player_elo.items():
                games_count = player_games_count.get(player_id, 0)
                if games_count > 0:  # Only include players with games
                    players_stats.append({
                        "player_id": player_id,
                        "elo_rating": elo_rating,
                        "total_games": games_count,
                    })

            # Sort by ELO to determine ranks
            players_stats.sort(key=lambda x: x["elo_rating"], reverse=True)

            # Store snapshots
            for rank, player_stat in enumerate(players_stats, start=1):
                snapshot = LeaderboardHistory(
                    player_id=player_stat["player_id"],
                    season_id=season.id,
                    snapshot_date=game_date,
                    rank=rank,
                    elo_rating=player_stat["elo_rating"],
                    total_games=player_stat["total_games"]
                )
                db.session.add(snapshot)

    db.session.commit()


def get_all_time_leaderboard():
    """
    Calculate all-time leaderboard statistics across all seasons.
    Returns a list of player statistics with total wins, games, and win rate.
    """
    players = Player.query.all()
    all_time_stats = []

    for player in players:
        # Get all games across all seasons
        total_games = GamePlayer.query.filter_by(player_id=player.id).count()

        if total_games == 0:
            continue

        # Get wins
        total_wins = GamePlayer.query.filter_by(
            player_id=player.id,
            is_winner=True
        ).count()

        # Calculate win rate
        win_rate = (total_wins / total_games * 100) if total_games > 0 else 0

        all_time_stats.append({
            "player_id": player.id,
            "player_name": player.name,
            "total_wins": total_wins,
            "total_games": total_games,
            "win_rate": round(win_rate, 1),
        })

    # Sort by total wins, then by win rate
    all_time_stats.sort(key=lambda x: (x["total_wins"], x["win_rate"]), reverse=True)

    return all_time_stats


def get_season_leaderboard(season_id):
    """
    Get leaderboard statistics for a specific season.
    Returns a list of player statistics with ELO, wins, games, and win rate.
    """
    players = Player.query.all()
    season_stats = []

    for player in players:
        # Get games in this season
        total_games = db.session.query(func.count(GamePlayer.id)).join(Game).filter(
            GamePlayer.player_id == player.id,
            Game.season_id == season_id
        ).scalar()

        if total_games == 0:
            continue

        # Get wins in this season
        total_wins = db.session.query(func.count(GamePlayer.id)).join(Game).filter(
            GamePlayer.player_id == player.id,
            GamePlayer.is_winner == True,
            Game.season_id == season_id
        ).scalar()

        # Calculate win rate
        win_rate = (total_wins / total_games * 100) if total_games > 0 else 0

        season_stats.append({
            "player_id": player.id,
            "player_name": player.name,
            "elo_rating": player.elo_rating,
            "total_wins": total_wins,
            "total_games": total_games,
            "win_rate": round(win_rate, 1),
        })

    # Sort by ELO rating
    season_stats.sort(key=lambda x: x["elo_rating"], reverse=True)

    return season_stats
