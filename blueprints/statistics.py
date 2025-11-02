"""Blueprint for statistics and chart-related API routes."""

from flask import Blueprint, render_template, request, jsonify
from datetime import datetime, timedelta
from collections import defaultdict
from models import db, Player, Game, GamePlayer, CakeBalance, LeaderboardHistory

statistics_bp = Blueprint("statistics", __name__)


@statistics_bp.route("/quick-stats")
def get_quick_stats():
    total_players = Player.query.count()
    total_games = Game.query.count()

    # Count shutouts (10-point difference)
    all_games = Game.query.all()
    total_shutouts = sum(1 for game in all_games if game.is_shutout)

    stats = {
        "total_players": total_players,
        "total_games": total_games,
        "total_shutouts": total_shutouts,
    }
    return render_template("partials/quick_stats.html", stats=stats)


@statistics_bp.route("/detailed-stats")
def get_detailed_stats():
    # Calculate various detailed statistics
    total_games = Game.query.count()
    total_players = Player.query.count()

    # Calculate average game duration
    games_with_duration = Game.query.filter(
        Game.start_time.isnot(None), Game.end_time.isnot(None)
    ).all()
    avg_duration = None
    if games_with_duration:
        avg_duration = sum(g.duration_minutes for g in games_with_duration) / len(
            games_with_duration
        )

    # Most active players
    most_active = (
        db.session.query(Player.name, db.func.count(GamePlayer.id).label("game_count"))
        .join(GamePlayer)
        .group_by(Player.id, Player.name)
        .order_by(db.func.count(GamePlayer.id).desc())
        .limit(3)
        .all()
    )

    # Best winning streaks (simplified - just current win rate leaders)
    best_players = (
        db.session.query(
            Player.name,
            db.func.count(GamePlayer.id).label("total_games"),
            db.func.sum(db.case((GamePlayer.is_winner == True, 1), else_=0)).label(
                "wins"
            ),
        )
        .join(GamePlayer)
        .group_by(Player.id, Player.name)
        .having(db.func.count(GamePlayer.id) >= 3)
        .all()
    )

    best_win_rates = []
    for name, total, wins in best_players:
        win_rate = (wins / total * 100) if total > 0 else 0
        best_win_rates.append((name, win_rate, total))

    best_win_rates.sort(key=lambda x: x[1], reverse=True)
    best_win_rates = best_win_rates[:3]

    # Game type popularity
    game_type_stats = (
        db.session.query(Game.game_type, db.func.count(Game.id).label("count"))
        .group_by(Game.game_type)
        .order_by(db.func.count(Game.id).desc())
        .all()
    )

    stats = {
        "total_games": total_games,
        "total_players": total_players,
        "avg_duration": round(avg_duration, 1) if avg_duration else None,
        "most_active": most_active,
        "best_win_rates": best_win_rates,
        "game_type_stats": game_type_stats,
    }

    return render_template("partials/detailed_stats.html", stats=stats)


@statistics_bp.route("/chart-data")
def get_chart_data():
    # Games over time data
    games = Game.query.order_by(Game.start_time).all()
    games_by_date = defaultdict(int)

    # Group games by date
    for game in games:
        date_key = game.start_time.strftime("%Y-%m-%d")
        games_by_date[date_key] += 1

    # Fill in missing dates for the last 30 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    dates = []
    games_per_day = []

    current_date = start_date
    while current_date <= end_date:
        date_key = current_date.strftime("%Y-%m-%d")
        dates.append(current_date.strftime("%m/%d"))
        games_per_day.append(games_by_date.get(date_key, 0))
        current_date += timedelta(days=1)

    # Game duration data
    duration_data = defaultdict(list)
    for game in games:
        if game.duration_minutes:
            duration_data[game.game_type].append(game.duration_minutes)

    duration_labels = []
    average_durations = []
    for game_type in ["1v1", "2v2", "2v1"]:
        if duration_data[game_type]:
            duration_labels.append(game_type)
            avg_duration = sum(duration_data[game_type]) / len(duration_data[game_type])
            average_durations.append(round(avg_duration, 1))

    # Game types distribution
    game_type_counts = defaultdict(int)
    for game in games:
        game_type_counts[game.game_type] += 1

    # Player performance data
    players = Player.query.all()
    player_names = []
    win_rates = []

    for player in players:
        total_games = GamePlayer.query.filter_by(player_id=player.id).count()
        if total_games > 0:
            wins = GamePlayer.query.filter_by(
                player_id=player.id, is_winner=True
            ).count()
            win_rate = wins / total_games * 100
            player_names.append(player.name)
            win_rates.append(round(win_rate, 1))

    chart_data = {
        "dates": dates,
        "games_per_day": games_per_day,
        "duration_labels": duration_labels,
        "average_durations": average_durations,
        "game_types": list(game_type_counts.keys()),
        "game_type_counts": list(game_type_counts.values()),
        "player_names": player_names,
        "win_rates": win_rates,
    }

    return render_template("partials/chart_script.html", chart_data=chart_data)


@statistics_bp.route("/players/<int:player_id>/stats")
def get_player_stats(player_id):
    player = Player.query.get_or_404(player_id)

    # Calculate player statistics
    total_games = GamePlayer.query.filter_by(player_id=player.id).count()
    wins = GamePlayer.query.filter_by(player_id=player.id, is_winner=True).count()
    losses = total_games - wins

    win_rate = (wins / total_games * 100) if total_games > 0 else 0

    # Calculate goals scored and conceded
    goals_for = 0
    goals_against = 0

    for gp in GamePlayer.query.filter_by(player_id=player.id).all():
        game = gp.game
        if gp.team == 1:
            goals_for += game.team1_score
            goals_against += game.team2_score
        else:
            goals_for += game.team2_score
            goals_against += game.team1_score

    # Calculate shutouts given and received
    shutouts_given = 0
    shutouts_received = 0

    for gp in GamePlayer.query.filter_by(player_id=player.id).all():
        game = gp.game
        if game.is_shutout:
            if gp.is_winner:
                shutouts_given += 1
            else:
                shutouts_received += 1

    # Calculate win rates by game type
    game_types = ["1v1", "2v2", "2v1"]
    win_rates_by_type = {}

    for game_type in game_types:
        games_played = (
            db.session.query(GamePlayer)
            .join(Game)
            .filter(GamePlayer.player_id == player.id, Game.game_type == game_type)
            .count()
        )

        games_won = (
            db.session.query(GamePlayer)
            .join(Game)
            .filter(
                GamePlayer.player_id == player.id,
                Game.game_type == game_type,
                GamePlayer.is_winner == True,
            )
            .count()
        )

        win_rate_type = (games_won / games_played * 100) if games_played > 0 else 0
        win_rates_by_type[game_type] = {
            "games_played": games_played,
            "games_won": games_won,
            "win_rate": win_rate_type,
        }

    # Calculate cake balance
    cakes_owed_to_player = (
        db.session.query(db.func.sum(CakeBalance.balance))
        .filter(CakeBalance.creditor_id == player.id)
        .scalar()
        or 0
    )

    cakes_player_owes = (
        db.session.query(db.func.sum(CakeBalance.balance))
        .filter(CakeBalance.debtor_id == player.id)
        .scalar()
        or 0
    )

    stats = {
        "player": player,
        "total_games": total_games,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_difference": goals_for - goals_against,
        "shutouts_given": shutouts_given,
        "shutouts_received": shutouts_received,
        "elo_rating": player.elo_rating,
        "win_rates_by_type": win_rates_by_type,
        "game_types": game_types,
        "cakes_owed_to_player": cakes_owed_to_player,
        "cakes_player_owes": cakes_player_owes,
    }

    return render_template("partials/player_stats.html", stats=stats)


@statistics_bp.route("/players/<int:player_id>/games")
def get_player_games(player_id):
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    player = Player.query.get_or_404(player_id)

    # Get all games this player participated in
    game_players = GamePlayer.query.filter_by(player_id=player.id).all()
    games = [gp.game for gp in game_players]

    # Sort by most recent first
    games.sort(key=lambda x: x.start_time, reverse=True)

    # Manual pagination
    total_items = len(games)
    total_pages = (total_items + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_games = games[start_idx:end_idx]

    return render_template(
        "partials/player_games.html",
        games=paginated_games,
        player=player,
        current_page=page,
        total_pages=total_pages,
    )


@statistics_bp.route("/players/<int:player_id>/position-history")
def get_player_position_history(player_id):
    """
    Return position history data for a single player.
    Returns JSON data for Chart.js line chart.
    """
    player = Player.query.get_or_404(player_id)

    # Get all snapshots for this player
    snapshots = LeaderboardHistory.query.filter_by(
        player_id=player_id
    ).order_by(LeaderboardHistory.snapshot_date).all()

    if not snapshots:
        return jsonify({
            "dates": [],
            "ranks": [],
            "elo_ratings": [],
            "player_name": player.name
        })

    dates = [s.snapshot_date.strftime("%Y-%m-%d") for s in snapshots]
    ranks = [s.rank for s in snapshots]
    elo_ratings = [s.elo_rating for s in snapshots]

    return jsonify({
        "dates": dates,
        "ranks": ranks,
        "elo_ratings": elo_ratings,
        "player_name": player.name
    })
