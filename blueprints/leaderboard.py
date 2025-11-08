"""Blueprint for leaderboard-related API routes."""

from flask import Blueprint, render_template, request, jsonify
from collections import defaultdict
from models import db, Player, GamePlayer, Game, CakeBalance, LeaderboardHistory
from services.statistics_service import calculate_badges

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard")
def get_leaderboard():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    min_games = request.args.get("min_games", 5, type=int)  # Default to 5 games

    # Calculate player statistics
    players_stats = []
    players = Player.query.all()

    for player in players:
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

        players_stats.append(
            {
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
            }
        )

    # Sort by ELO rating (highest first)
    players_stats.sort(key=lambda x: x["elo_rating"], reverse=True)

    # Filter by minimum games (if min_games is 0 or negative, show all)
    if min_games > 0:
        players_stats = [p for p in players_stats if p["total_games"] >= min_games]

    # Calculate badges for each player (needs all players for comparisons)
    for player_stat in players_stats:
        player_stat["badges"] = calculate_badges(player_stat, players_stats)

    # Manual pagination
    total_items = len(players_stats)
    total_pages = (total_items + per_page - 1) // per_page  # Ceiling division
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_stats = players_stats[start_idx:end_idx]

    return render_template(
        "partials/leaderboard.html",
        players_stats=paginated_stats,
        current_page=page,
        total_pages=total_pages,
        rank_offset=(page - 1) * per_page,
        min_games=min_games,
    )


@leaderboard_bp.route("/cake-leaderboard")
def get_cake_leaderboard():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Get players with most cakes owed to them
    cake_stats_query = (
        db.session.query(
            Player.name, db.func.sum(CakeBalance.balance).label("total_cakes")
        )
        .join(CakeBalance, Player.id == CakeBalance.creditor_id)
        .group_by(Player.id, Player.name)
        .order_by(db.func.sum(CakeBalance.balance).desc())
    )

    # Get players who owe the most cakes
    debt_stats_query = (
        db.session.query(
            Player.name, db.func.sum(CakeBalance.balance).label("total_debt")
        )
        .join(CakeBalance, Player.id == CakeBalance.debtor_id)
        .group_by(Player.id, Player.name)
        .order_by(db.func.sum(CakeBalance.balance).desc())
    )

    # Calculate pagination based on the larger of the two lists
    cake_stats_all = cake_stats_query.all()
    debt_stats_all = debt_stats_query.all()
    total_items = max(len(cake_stats_all), len(debt_stats_all))
    total_pages = (total_items + per_page - 1) // per_page

    # Paginate both lists
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    cake_stats = cake_stats_all[start_idx:end_idx]
    debt_stats = debt_stats_all[start_idx:end_idx]

    return render_template(
        "partials/cake_leaderboard.html",
        cake_stats=cake_stats,
        debt_stats=debt_stats,
        current_page=page,
        total_pages=total_pages,
    )


@leaderboard_bp.route("/win-rates")
def get_win_rates():
    # Calculate win rates by game type for each player
    win_rates = {}
    players = Player.query.all()
    game_types = ["1v1", "2v2", "2v1"]

    for player in players:
        win_rates[player.name] = {}
        for game_type in game_types:
            # Get games for this player and game type
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

            win_rate = (games_won / games_played * 100) if games_played > 0 else 0
            win_rates[player.name][game_type] = {
                "games_played": games_played,
                "games_won": games_won,
                "win_rate": win_rate,
            }

    return render_template(
        "partials/win_rates.html", win_rates=win_rates, game_types=game_types
    )


@leaderboard_bp.route("/leaderboard-position-chart")
def get_leaderboard_position_chart():
    """
    Return data for leaderboard position chart showing all players' ranks over time.
    Returns JSON data for Chart.js line chart.
    """
    min_games = request.args.get("min_games", 5, type=int)

    # Get all snapshots ordered by date
    snapshots = LeaderboardHistory.query.order_by(LeaderboardHistory.snapshot_date).all()

    if not snapshots:
        return jsonify({"dates": [], "datasets": []})

    # If filtering by min_games, get the set of player IDs that meet the criteria
    filtered_player_ids = None
    if min_games > 0:
        filtered_player_ids = set()
        players = Player.query.all()
        for player in players:
            total_games = GamePlayer.query.filter_by(player_id=player.id).count()
            if total_games >= min_games:
                filtered_player_ids.add(player.id)

    # Get all unique dates (sorted)
    all_dates = sorted(set(snapshot.snapshot_date for snapshot in snapshots))
    date_strings = [d.strftime("%Y-%m-%d") for d in all_dates]

    # Group snapshots by date for recalculating ranks
    snapshots_by_date = defaultdict(list)
    for snapshot in snapshots:
        if filtered_player_ids is None or snapshot.player_id in filtered_player_ids:
            snapshots_by_date[snapshot.snapshot_date].append(snapshot)

    # Organize data by player with recalculated ranks
    player_data = defaultdict(lambda: {"name": "", "ranks": [], "dates": []})

    for date in all_dates:
        date_snapshots = snapshots_by_date[date]

        # Sort by ELO rating (descending) to recalculate ranks
        date_snapshots.sort(key=lambda s: s.elo_rating, reverse=True)

        # Assign new ranks based on filtered players
        for new_rank, snapshot in enumerate(date_snapshots, start=1):
            player_id = snapshot.player_id

            if not player_data[player_id]["name"]:
                player_data[player_id]["name"] = snapshot.player.name

            player_data[player_id]["dates"].append(date.strftime("%Y-%m-%d"))
            player_data[player_id]["ranks"].append(new_rank)

    # Build datasets for each player
    datasets = []
    colors = [
        "#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", "#9966FF",
        "#FF9F40", "#FF6384", "#C9CBCF", "#4BC0C0", "#FF6384"
    ]

    for idx, (player_id, data) in enumerate(player_data.items()):
        # Create a date-to-rank mapping for this player
        date_rank_map = dict(zip(data["dates"], data["ranks"]))

        # Fill in ranks for all dates (null if player didn't have data that day)
        ranks_by_date = []
        for date_str in date_strings:
            ranks_by_date.append(date_rank_map.get(date_str, None))

        datasets.append({
            "label": data["name"],
            "data": ranks_by_date,
            "borderColor": colors[idx % len(colors)],
            "backgroundColor": colors[idx % len(colors)] + "33",  # Add transparency
            "tension": 0.1,
            "spanGaps": True  # Connect lines even with null values
        })

    return jsonify({
        "dates": date_strings,
        "datasets": datasets
    })
