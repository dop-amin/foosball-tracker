"""Blueprint for leaderboard-related API routes."""

from flask import Blueprint, render_template, request, jsonify
from collections import defaultdict
from models import db, Player, GamePlayer, Game, CakeBalance, LeaderboardHistory
from services.statistics_service import calculate_badges, precompute_badge_data

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard")
def get_leaderboard():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    min_games = request.args.get("min_games", 5, type=int)  # Default to 5 games
    game_type = request.args.get("game_type", "all", type=str)  # Filter by game type

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
    ).join(Game, GamePlayer.game_id == Game.id)

    # Filter by game type if specified
    if game_type != "all":
        stats_query = stats_query.filter(Game.game_type == game_type)

    stats_query = stats_query.group_by(Player.id)

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

        # Get the appropriate ELO rating based on game type filter
        if game_type == "all":
            elo_rating = player.elo_rating
        else:
            elo_rating = getattr(player, f"elo_{game_type}")

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
                "elo_rating": elo_rating,
            }
        )

    # Sort by ELO rating (highest first)
    players_stats.sort(key=lambda x: x["elo_rating"], reverse=True)

    # Filter by minimum games (if min_games is 0 or negative, show all)
    if min_games > 0:
        players_stats = [p for p in players_stats if p["total_games"] >= min_games]

    # Pre-compute badge data for all players in one go
    player_ids = [p["player"].id for p in players_stats]
    # Pass game_type filter to badge calculation (None if "all")
    badge_game_type = None if game_type == "all" else game_type
    cached_badge_data = precompute_badge_data(player_ids, badge_game_type)

    # Calculate badges for each player (needs all players for comparisons)
    for player_stat in players_stats:
        player_stat["badges"] = calculate_badges(player_stat, players_stats, cached_badge_data, badge_game_type)

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
        game_type=game_type,
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
    Supports filtering by game type.
    """
    min_games = request.args.get("min_games", 5, type=int)
    game_type = request.args.get("game_type", "all", type=str)

    # For "all" game types, use existing LeaderboardHistory data
    if game_type == "all":
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
    else:
        # For game-type-specific filtering, recalculate historical positions
        # by replaying games of that type
        from services.elo_service import calculate_elo_change

        # Get all games of this type in chronological order
        games_query = Game.query.filter_by(game_type=game_type).order_by(Game.start_time)
        games = games_query.all()

        if not games:
            return jsonify({"dates": [], "datasets": []})

        # Initialize player ELO ratings for this game type
        all_players = Player.query.all()
        player_elo = {player.id: 1500 for player in all_players}
        player_games_count = {player.id: 0 for player in all_players}

        # Group games by date
        games_by_date = defaultdict(list)
        for game in games:
            game_date = game.start_time.date()
            games_by_date[game_date].append(game)

        # Process games chronologically by date to build snapshots
        snapshots = []
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

            # Store snapshots (using a simple object for compatibility with existing code)
            for rank, player_stat in enumerate(players_stats, start=1):
                # Create a mock snapshot object
                class MockSnapshot:
                    def __init__(self, player_id, snapshot_date, rank, elo_rating, total_games):
                        self.player_id = player_id
                        self.snapshot_date = snapshot_date
                        self.rank = rank
                        self.elo_rating = elo_rating
                        self.total_games = total_games
                        self.player = Player.query.get(player_id)

                snapshot = MockSnapshot(
                    player_stat["player_id"],
                    game_date,
                    rank,
                    player_stat["elo_rating"],
                    player_stat["total_games"]
                )
                snapshots.append(snapshot)

        # If filtering by min_games, get the set of player IDs that meet the criteria (for this game type)
        filtered_player_ids = None
        if min_games > 0:
            filtered_player_ids = set()
            for player_id, games_count in player_games_count.items():
                if games_count >= min_games:
                    filtered_player_ids.add(player_id)

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
