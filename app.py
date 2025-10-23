from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
import os
import json
import secrets

app = Flask(__name__)
app.config["SECRET_KEY"] = secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_PATH", "sqlite:///foosball.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    elo_rating = db.Column(db.Integer, default=1500, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Player {self.name}>"


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    game_type = db.Column(db.String(10), nullable=False)  # '1v1', '2v2', '2v1'
    team1_score = db.Column(db.Integer, nullable=False)
    team2_score = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    players = db.relationship(
        "GamePlayer", back_populates="game", cascade="all, delete-orphan"
    )

    @property
    def duration_minutes(self):
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() / 60)
        return None

    @property
    def is_shutout(self):
        return (
            self.team1_score == 10
            and self.team2_score == 0
            or self.team1_score == 0
            and self.team2_score == 10
        )

    def __repr__(self):
        return f"<Game {self.team1_score}-{self.team2_score} ({self.game_type})>"


class GamePlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    team = db.Column(db.Integer, nullable=False)  # 1 or 2
    is_winner = db.Column(db.Boolean, nullable=False)
    elo_change = db.Column(db.Integer, nullable=True)  # ELO rating change for this game

    game = db.relationship("Game", back_populates="players")
    player = db.relationship("Player")

    def __repr__(self):
        return f"<GamePlayer {self.player.name} Team{self.team}>"


class CakeBalance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    creditor_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    balance = db.Column(db.Integer, default=0)

    debtor = db.relationship("Player", foreign_keys=[debtor_id])
    creditor = db.relationship("Player", foreign_keys=[creditor_id])

    def __repr__(self):
        return f"<CakeBalance {self.debtor.name} owes {self.creditor.name}: {self.balance}>"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/players")
def players():
    return render_template("players.html")


@app.route("/games")
def games():
    return render_template("games.html")


@app.route("/leaderboard")
def leaderboard():
    return render_template("leaderboard.html")


@app.route("/statistics")
def statistics():
    return render_template("statistics.html")


@app.route("/players/<int:player_id>")
def player_detail(player_id):
    player = Player.query.get_or_404(player_id)
    return render_template("player_detail.html", player=player)


# API Routes
@app.route("/api/players", methods=["GET"])
def get_players():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = Player.query.order_by(Player.name).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "partials/players_list.html",
        players=pagination.items,
        current_page=pagination.page,
        total_pages=pagination.pages,
    )


@app.route("/api/players", methods=["POST"])
def add_player():
    name = request.form.get("name", "").strip()
    if not name:
        return '<div class="alert alert-danger">Player name is required</div>', 200

    if Player.query.filter_by(name=name).first():
        return '<div class="alert alert-danger">Player already exists</div>', 200

    player = Player(name=name)
    db.session.add(player)
    db.session.commit()

    return '<div class="alert alert-success">Player added successfully!</div>', 201


@app.route("/api/cake-balances")
def get_cake_balances():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = (
        db.session.query(CakeBalance)
        .filter(CakeBalance.balance > 0)
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return render_template(
        "partials/cake_balances.html",
        balances=pagination.items,
        current_page=pagination.page,
        total_pages=pagination.pages,
    )


@app.route("/api/quick-stats")
def get_quick_stats():
    total_players = Player.query.count()
    total_games = Game.query.count()
    total_shutouts = Game.query.filter(
        db.or_(
            db.and_(Game.team1_score == 10, Game.team2_score == 0),
            db.and_(Game.team1_score == 0, Game.team2_score == 10),
        )
    ).count()

    stats = {
        "total_players": total_players,
        "total_games": total_games,
        "total_shutouts": total_shutouts,
    }
    return render_template("partials/quick_stats.html", stats=stats)


@app.route("/api/recent-games")
def get_recent_games():
    recent_games = Game.query.order_by(Game.start_time.desc()).limit(5).all()
    return render_template("partials/recent_games.html", games=recent_games)


@app.route("/api/game-form")
def get_game_form():
    game_type = request.args.get("game_type")
    players = Player.query.order_by(Player.name).all()
    return render_template(
        "partials/game_form.html", game_type=game_type, players=players
    )


def calculate_elo_change(
    team1_rating, team2_rating, team1_score, team2_score, k_factor=32
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


def update_elo_ratings(game):
    """
    Update ELO ratings for all players in a game and store ELO changes.
    """
    # Get team players and their GamePlayer records
    team1_players = []
    team2_players = []
    team1_game_players = []
    team2_game_players = []

    for gp in game.players:
        player = Player.query.get(gp.player_id)
        if gp.team == 1:
            team1_players.append(player)
            team1_game_players.append(gp)
        else:
            team2_players.append(player)
            team2_game_players.append(gp)

    # Calculate average team ratings
    team1_avg_rating = sum(p.elo_rating for p in team1_players) / len(team1_players)
    team2_avg_rating = sum(p.elo_rating for p in team2_players) / len(team2_players)

    # Calculate ELO changes
    team1_change, team2_change = calculate_elo_change(
        team1_avg_rating, team2_avg_rating, game.team1_score, game.team2_score
    )

    # Update player ratings and store ELO changes
    for i, player in enumerate(team1_players):
        player.elo_rating += team1_change
        team1_game_players[i].elo_change = team1_change

    for i, player in enumerate(team2_players):
        player.elo_rating += team2_change
        team2_game_players[i].elo_change = team2_change


def recalculate_all_elo_ratings():
    """
    Recalculate ELO ratings for all players from scratch by replaying all games.
    This is useful for initializing ELO ratings or fixing inconsistencies.
    """
    # Reset all player ratings to 1500
    players = Player.query.all()
    for player in players:
        player.elo_rating = 1500

    # Get all games in chronological order
    games = Game.query.order_by(Game.start_time).all()

    # Replay each game to update ELO ratings
    for game in games:
        update_elo_ratings(game)

    db.session.commit()


@app.route("/api/games", methods=["POST"])
def add_game():
    from dateutil.parser import parse

    try:
        game_type = request.form.get("game_type")
        start_time = parse(request.form.get("start_time"))
        end_time = (
            parse(request.form.get("end_time"))
            if request.form.get("end_time")
            else None
        )

        # Don't save end_time if it's the same as start_time
        if end_time and end_time == start_time:
            end_time = None

        team1_score = int(request.form.get("team1_score"))
        team2_score = int(request.form.get("team2_score"))

        # Create game
        game = Game(
            game_type=game_type,
            start_time=start_time,
            end_time=end_time,
            team1_score=team1_score,
            team2_score=team2_score,
        )
        db.session.add(game)
        db.session.flush()  # Get the game ID

        # Add players to teams
        team1_players = request.form.getlist("team1_players")
        team2_players = request.form.getlist("team2_players")

        # Determine winners
        team1_wins = team1_score > team2_score

        for player_id in team1_players:
            if player_id:
                game_player = GamePlayer(
                    game_id=game.id,
                    player_id=int(player_id),
                    team=1,
                    is_winner=team1_wins,
                )
                db.session.add(game_player)

        for player_id in team2_players:
            if player_id:
                game_player = GamePlayer(
                    game_id=game.id,
                    player_id=int(player_id),
                    team=2,
                    is_winner=not team1_wins,
                )
                db.session.add(game_player)

        # Handle cake counter for shutouts
        if game.is_shutout:
            update_cake_balance(game)

        # Update ELO ratings
        update_elo_ratings(game)

        db.session.commit()
        return '<div class="alert alert-success">Game recorded successfully!</div>', 201

    except Exception as e:
        db.session.rollback()
        return f'<div class="alert alert-danger">Error: {str(e)}</div>', 400


def update_cake_balance(game):
    winners = []
    losers = []

    for gp in game.players:
        if gp.is_winner:
            winners.append(gp.player_id)
        else:
            losers.append(gp.player_id)

    # Each loser owes each winner a cake
    for loser_id in losers:
        for winner_id in winners:
            balance = CakeBalance.query.filter_by(
                debtor_id=loser_id, creditor_id=winner_id
            ).first()

            if balance:
                balance.balance += 1
            else:
                balance = CakeBalance(
                    debtor_id=loser_id, creditor_id=winner_id, balance=1
                )
                db.session.add(balance)


@app.route("/api/games", methods=["GET"])
def get_games():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = Game.query.order_by(Game.start_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "partials/games_list.html",
        games=pagination.items,
        current_page=pagination.page,
        total_pages=pagination.pages,
    )


@app.route("/api/leaderboard")
def get_leaderboard():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

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
    )


@app.route("/api/cake-leaderboard")
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


@app.route("/api/win-rates")
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


@app.route("/api/players/<int:player_id>/stats")
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


@app.route("/api/players/<int:player_id>/games")
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


@app.route("/api/chart-data")
def get_chart_data():
    from collections import defaultdict
    from datetime import datetime, timedelta

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

    return f"<script>createCharts({json.dumps(chart_data)});</script>"


@app.route("/api/detailed-stats")
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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0")
