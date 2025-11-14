"""Blueprint for leaderboard-related API routes."""

from flask import Blueprint, render_template, request, jsonify
from collections import defaultdict
from models import db, Player, GamePlayer, Game, CakeBalance, LeaderboardHistory, Season
from services.statistics_service import calculate_badges, precompute_badge_data
from services.season_service import get_current_season, get_all_seasons
from services.leaderboard_service import get_all_time_leaderboard, get_season_leaderboard

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard")
def get_leaderboard():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    min_games = request.args.get("min_games", 5, type=int)  # Default to 5 games

    # Get current season
    current_season = get_current_season()

    # Calculate player statistics using optimized aggregation query
    # Single query with joins to get all stats at once
    stats_query = db.session.query(
        Player,
        db.func.count(GamePlayer.id).label('total_games'),
        db.func.sum(db.case((GamePlayer.is_winner == True, 1), else_=0)).label('wins'),
        db.func.sum(
            db.case(
                (GamePlayer.team == 1, Game.team1_score),
                else_=Game.team2_score
            )
        ).label('goals_for'),
        db.func.sum(
            db.case(
                (GamePlayer.team == 1, Game.team2_score),
                else_=Game.team1_score
            )
        ).label('goals_against'),
        db.func.sum(
            db.case(
                (
                    db.and_(
                        db.or_(
                            Game.team1_score - Game.team2_score >= 10,
                            Game.team2_score - Game.team1_score >= 10
                        ),
                        GamePlayer.is_winner == True
                    ),
                    1
                ),
                else_=0
            )
        ).label('shutouts_given'),
        db.func.sum(
            db.case(
                (
                    db.and_(
                        db.or_(
                            Game.team1_score - Game.team2_score >= 10,
                            Game.team2_score - Game.team1_score >= 10
                        ),
                        GamePlayer.is_winner == False
                    ),
                    1
                ),
                else_=0
            )
        ).label('shutouts_received')
    ).join(GamePlayer, Player.id == GamePlayer.player_id
    ).join(Game, GamePlayer.game_id == Game.id
    ).filter(Game.season_id == current_season.id
    ).group_by(Player.id)

    # Execute query and build stats list
    players_stats = []
    for row in stats_query.all():
        player, total_games, wins, goals_for, goals_against, shutouts_given, shutouts_received = row

        # Convert to int (they come back as Decimal/long from SQL aggregates)
        total_games = int(total_games or 0)
        wins = int(wins or 0)
        goals_for = int(goals_for or 0)
        goals_against = int(goals_against or 0)
        shutouts_given = int(shutouts_given or 0)
        shutouts_received = int(shutouts_received or 0)

        losses = total_games - wins
        win_rate = (wins / total_games * 100) if total_games > 0 else 0

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

    # Pre-compute badge data for all players in one go
    player_ids = [p["player"].id for p in players_stats]
    cached_badge_data = precompute_badge_data(player_ids, current_season.id)

    # Calculate badges for each player (needs all players for comparisons)
    for player_stat in players_stats:
        player_stat["badges"] = calculate_badges(player_stat, players_stats, cached_badge_data, current_season.id)

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

    # Get current season
    current_season = get_current_season()

    # Get players with most cakes owed to them
    cake_stats_query = (
        db.session.query(
            Player.name, db.func.sum(CakeBalance.balance).label("total_cakes")
        )
        .join(CakeBalance, Player.id == CakeBalance.creditor_id)
        .filter(CakeBalance.season_id == current_season.id)
        .group_by(Player.id, Player.name)
        .order_by(db.func.sum(CakeBalance.balance).desc())
    )

    # Get players who owe the most cakes
    debt_stats_query = (
        db.session.query(
            Player.name, db.func.sum(CakeBalance.balance).label("total_debt")
        )
        .join(CakeBalance, Player.id == CakeBalance.debtor_id)
        .filter(CakeBalance.season_id == current_season.id)
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
    # Get current season
    current_season = get_current_season()

    # Calculate win rates by game type for each player
    win_rates = {}
    players = Player.query.all()
    game_types = ["1v1", "2v2", "2v1"]

    for player in players:
        win_rates[player.name] = {}
        for game_type in game_types:
            # Get games for this player and game type in current season
            games_played = (
                db.session.query(GamePlayer)
                .join(Game)
                .filter(
                    GamePlayer.player_id == player.id,
                    Game.game_type == game_type,
                    Game.season_id == current_season.id
                )
                .count()
            )

            games_won = (
                db.session.query(GamePlayer)
                .join(Game)
                .filter(
                    GamePlayer.player_id == player.id,
                    Game.game_type == game_type,
                    GamePlayer.is_winner == True,
                    Game.season_id == current_season.id
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

    # Get current season
    current_season = get_current_season()

    # Get all snapshots for current season ordered by date
    snapshots = LeaderboardHistory.query.filter_by(
        season_id=current_season.id
    ).order_by(LeaderboardHistory.snapshot_date).all()

    if not snapshots:
        return jsonify({"dates": [], "datasets": []})

    # If filtering by min_games, get the set of player IDs that meet the criteria
    filtered_player_ids = None
    if min_games > 0:
        filtered_player_ids = set()
        players = Player.query.all()
        for player in players:
            total_games = db.session.query(GamePlayer).join(Game).filter(
                GamePlayer.player_id == player.id,
                Game.season_id == current_season.id
            ).count()
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


@leaderboard_bp.route("/all-time-leaderboard")
def get_all_time_leaderboard_view():
    """Get all-time leaderboard across all seasons."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    all_time_stats = get_all_time_leaderboard()

    # Manual pagination
    total_items = len(all_time_stats)
    total_pages = (total_items + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_stats = all_time_stats[start_idx:end_idx]

    return render_template(
        "partials/all_time_leaderboard.html",
        players_stats=paginated_stats,
        current_page=page,
        total_pages=total_pages,
        rank_offset=(page - 1) * per_page,
    )


@leaderboard_bp.route("/season-selector")
def get_season_selector():
    """Get season selector dropdown."""
    current_season = get_current_season()
    all_seasons = get_all_seasons(order_by_newest=True)

    return render_template(
        "partials/season_selector.html",
        current_season=current_season,
        all_seasons=all_seasons,
    )


@leaderboard_bp.route("/season/<int:season_id>/leaderboard")
def get_season_leaderboard_view(season_id):
    """Get leaderboard for a specific season."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    min_games = request.args.get("min_games", 5, type=int)

    from services.season_service import get_season_by_id
    season = get_season_by_id(season_id)
    if not season:
        return '<div class="alert alert-danger">Season not found!</div>', 404

    season_stats = get_season_leaderboard(season_id)

    # Filter by minimum games
    if min_games > 0:
        season_stats = [p for p in season_stats if p["total_games"] >= min_games]

    # Manual pagination
    total_items = len(season_stats)
    total_pages = (total_items + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_stats = season_stats[start_idx:end_idx]

    return render_template(
        "partials/season_leaderboard.html",
        players_stats=paginated_stats,
        season=season,
        current_page=page,
        total_pages=total_pages,
        rank_offset=(page - 1) * per_page,
        min_games=min_games,
    )


@leaderboard_bp.route("/season-info")
def get_season_info():
    """Debug endpoint to show current season information."""
    current_season = get_current_season()
    all_seasons = get_all_seasons(order_by_newest=True)

    info = {
        "current_season": {
            "id": current_season.id,
            "name": current_season.name,
            "start_date": current_season.start_date.isoformat(),
            "end_date": current_season.end_date.isoformat(),
            "is_current": current_season.is_current,
        },
        "all_seasons": [
            {
                "id": s.id,
                "name": s.name,
                "start_date": s.start_date.isoformat(),
                "end_date": s.end_date.isoformat(),
                "is_current": s.is_current,
                "games_count": len(s.games) if s.games else 0,
            }
            for s in all_seasons
        ]
    }

    return jsonify(info)
