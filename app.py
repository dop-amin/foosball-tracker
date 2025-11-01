from flask import Flask, render_template, request, redirect, url_for, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta, timezone
import os
import json
import secrets
import math
import random

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
        return abs(self.team1_score - self.team2_score) >= 10

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


class LeaderboardHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    snapshot_date = db.Column(db.Date, nullable=False)
    rank = db.Column(db.Integer, nullable=False)
    elo_rating = db.Column(db.Integer, nullable=False)
    total_games = db.Column(db.Integer, nullable=False)

    player = db.relationship("Player")

    __table_args__ = (
        db.UniqueConstraint("player_id", "snapshot_date", name="unique_player_date"),
    )

    def __repr__(self):
        return f"<LeaderboardHistory {self.player.name} rank {self.rank} on {self.snapshot_date}>"


class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="setup")  # 'setup', 'active', 'completed'

    matches = db.relationship("TournamentMatch", back_populates="tournament", cascade="all, delete-orphan")
    participants = db.relationship("TournamentParticipant", back_populates="tournament", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tournament {self.name} ({self.status})>"


class TournamentParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournament.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    seed = db.Column(db.Integer, nullable=False)  # Tournament seeding position
    eliminated = db.Column(db.Boolean, default=False)

    tournament = db.relationship("Tournament", back_populates="participants")
    player = db.relationship("Player")

    def __repr__(self):
        return f"<TournamentParticipant {self.player.name} seed:{self.seed}>"


class TournamentMatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournament.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)  # 1=finals, 2=semifinals, 3=quarterfinals, etc.
    match_number = db.Column(db.Integer, nullable=False)  # Position in the round
    player1_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=True)  # Null if TBD
    player2_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=True)  # Null if TBD
    winner_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=True)  # Link to actual game played
    next_match_id = db.Column(db.Integer, db.ForeignKey("tournament_match.id"), nullable=True)  # Winner advances to this match

    tournament = db.relationship("Tournament", back_populates="matches")
    player1 = db.relationship("Player", foreign_keys=[player1_id])
    player2 = db.relationship("Player", foreign_keys=[player2_id])
    winner = db.relationship("Player", foreign_keys=[winner_id])
    game = db.relationship("Game")
    next_match = db.relationship("TournamentMatch", remote_side=[id], foreign_keys=[next_match_id])

    def __repr__(self):
        return f"<TournamentMatch R{self.round_number}M{self.match_number}>"


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

    # Count shutouts (10-point difference)
    all_games = Game.query.all()
    total_shutouts = sum(1 for game in all_games if game.is_shutout)

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


def create_daily_snapshot(snapshot_date=None):
    """
    Create a daily snapshot of the leaderboard for all players.
    Stores each player's rank, ELO rating, and total games count.

    Args:
        snapshot_date: Date to create snapshot for (defaults to today)
    """
    from datetime import date

    if snapshot_date is None:
        snapshot_date = date.today()

    # Calculate current leaderboard statistics
    players_stats = []
    players = Player.query.all()

    for player in players:
        total_games = GamePlayer.query.filter_by(player_id=player.id).count()

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
    Creates one snapshot per day where games were played.
    """
    from datetime import date, timedelta
    from collections import defaultdict

    # Clear existing snapshots
    LeaderboardHistory.query.delete()

    # Reset all player ratings to 1500
    players = Player.query.all()
    player_elo = {player.id: 1500 for player in players}
    player_games_count = {player.id: 0 for player in players}

    # Get all games in chronological order
    games = Game.query.order_by(Game.start_time).all()

    if not games:
        db.session.commit()
        return

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
                snapshot_date=game_date,
                rank=rank,
                elo_rating=player_stat["elo_rating"],
                total_games=player_stat["total_games"]
            )
            db.session.add(snapshot)

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

        # Validate score ranges
        if team1_score < 0 or team2_score < 0:
            return (
                '<div class="alert alert-danger">Scores cannot be negative!</div>',
                200,
            )

        if team1_score > 11 or team2_score > 11:
            return '<div class="alert alert-danger">Maximum score is 11!</div>', 200

        # Validate that it's not a draw
        if team1_score == team2_score:
            return (
                '<div class="alert alert-danger">Draw games are not allowed. One team must win!</div>',
                200,
            )

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

        # Validate that no player appears on both teams
        team1_ids = [int(p) for p in team1_players if p]
        team2_ids = [int(p) for p in team2_players if p]

        duplicate_players = set(team1_ids) & set(team2_ids)
        if duplicate_players:
            return '<div class="alert alert-danger">A player cannot play against themselves!</div>', 200

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

        # Create daily snapshot after committing the game
        try:
            create_daily_snapshot()
        except Exception as snapshot_error:
            # Log error but don't fail the game creation
            print(f"Warning: Failed to create daily snapshot: {snapshot_error}")

        return '<div class="alert alert-success">Game recorded successfully!</div>', 201

    except Exception as e:
        db.session.rollback()
        return f'<div class="alert alert-danger">Error: {str(e)}</div>', 200


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


def calculate_player_streaks(player_id):
    """Calculate current and best winning streaks for a player."""
    games = (
        GamePlayer.query.filter_by(player_id=player_id)
        .join(Game)
        .order_by(Game.start_time.asc())
        .all()
    )

    if not games:
        return 0, 0

    current_streak = 0
    best_streak = 0
    temp_streak = 0

    for gp in games:
        if gp.is_winner:
            temp_streak += 1
            best_streak = max(best_streak, temp_streak)
        else:
            temp_streak = 0

    # Check if currently on a streak (last game was a win)
    if games and games[-1].is_winner:
        current_streak = temp_streak

    return current_streak, best_streak


def calculate_badges(player_stats, all_players_stats):
    """Calculate achievement badges for a player based on their stats."""
    badges = []
    player = player_stats["player"]

    # Winning Streaks
    current_streak, best_streak = calculate_player_streaks(player.id)
    if current_streak >= 10:
        badges.append({"emoji": "💥", "label": "Unstoppable", "color": "danger", "tooltip": f"Unstoppable: Currently on a {current_streak} game winning streak!"})
    elif current_streak >= 5:
        badges.append({"emoji": "🔥", "label": "On Fire", "color": "danger", "tooltip": f"On Fire: Currently on a {current_streak} game winning streak!"})
    elif current_streak >= 3:
        badges.append({"emoji": "⚡", "label": "Hot Streak", "color": "warning", "tooltip": f"Hot Streak: Currently on a {current_streak} game winning streak!"})

    # Performance Badges
    if player_stats["total_games"] >= 10 and player_stats["win_rate"] == 100:
        badges.append({"emoji": "💯", "label": "Perfect", "color": "success", "tooltip": f"Undefeated with {player_stats['total_games']} games played!"})
    elif player_stats["total_games"] >= 20 and player_stats["win_rate"] >= 60:
        badges.append({"emoji": "⭐", "label": "Dominator", "color": "primary", "tooltip": f"{player_stats['win_rate']:.1f}% win rate with {player_stats['total_games']} games"})

    if player_stats["elo_rating"] >= 1700:
        badges.append({"emoji": "🏆", "label": "ELO Elite", "color": "warning", "tooltip": f"ELO rating of {player_stats['elo_rating']} (1700+ required)"})

    # Goals per game (Sharpshooter)
    if player_stats["total_games"] >= 20:
        goals_per_game = player_stats["goals_for"] / player_stats["total_games"]
        # Check if this is the highest goals per game among qualified players
        qualified_players = [p for p in all_players_stats if p["total_games"] >= 20]
        if qualified_players:
            max_goals_per_game = max(
                p["goals_for"] / p["total_games"] for p in qualified_players
            )
            if goals_per_game == max_goals_per_game and goals_per_game > 0:
                badges.append({"emoji": "🎯", "label": "Sharpshooter", "color": "info", "tooltip": f"Highest goals per game average: {goals_per_game:.1f}"})

    # Shutout Achievements
    if player_stats["shutouts_given"] >= 5:
        badges.append({"emoji": "🛡️", "label": "Shutout Master", "color": "secondary", "tooltip": f"{player_stats['shutouts_given']} shutout victories (10-0)"})

    # Cake King (most cakes owed to them)
    cake_query = (
        db.session.query(db.func.sum(CakeBalance.balance))
        .filter_by(creditor_id=player.id)
        .scalar()
    )
    total_cakes = cake_query or 0
    if total_cakes > 0:
        # Check if this is the most cakes
        all_cake_totals = []
        for p_stat in all_players_stats:
            p_cakes = (
                db.session.query(db.func.sum(CakeBalance.balance))
                .filter_by(creditor_id=p_stat["player"].id)
                .scalar() or 0
            )
            all_cake_totals.append(p_cakes)

        if all_cake_totals and total_cakes == max(all_cake_totals):
            badges.append({"emoji": "🎂", "label": "Cake King", "color": "light", "tooltip": f"Most cakes owed by opponents: {total_cakes} cake{'s' if total_cakes != 1 else ''}"})

    # Survivor (most shutouts received but still positive win rate)
    if (
        player_stats["shutouts_received"] >= 3
        and player_stats["win_rate"] > 50
        and player_stats["total_games"] >= 10
    ):
        qualified_survivors = [
            p
            for p in all_players_stats
            if p["shutouts_received"] >= 3
            and p["win_rate"] > 50
            and p["total_games"] >= 10
        ]
        if qualified_survivors:
            max_shutouts_received = max(p["shutouts_received"] for p in qualified_survivors)
            if player_stats["shutouts_received"] == max_shutouts_received:
                badges.append({"emoji": "💪", "label": "Survivor", "color": "success", "tooltip": f"Survived {player_stats['shutouts_received']} shutouts but still winning ({player_stats['win_rate']:.1f}% win rate)"})

    # Activity Badges
    if player_stats["total_games"] >= 50:
        badges.append({"emoji": "🎖️", "label": "Veteran", "color": "secondary", "tooltip": f"{player_stats['total_games']} games played (50+ required)"})

    # Marathon (most games in last 7 days, min 5)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_games = (
        GamePlayer.query.filter_by(player_id=player.id)
        .join(Game)
        .filter(Game.start_time >= seven_days_ago)
        .count()
    )

    if recent_games >= 5:
        # Check if this is the most recent games
        all_recent_games = []
        for p_stat in all_players_stats:
            p_recent = (
                GamePlayer.query.filter_by(player_id=p_stat["player"].id)
                .join(Game)
                .filter(Game.start_time >= seven_days_ago)
                .count()
            )
            all_recent_games.append(p_recent)

        if all_recent_games and recent_games == max(all_recent_games):
            badges.append({"emoji": "📈", "label": "Marathon", "color": "info", "tooltip": f"Most active player: {recent_games} games in the last 7 days"})

    return badges


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

    return render_template("partials/chart_script.html", chart_data=chart_data)


@app.route("/api/leaderboard-position-chart")
def get_leaderboard_position_chart():
    """
    Return data for leaderboard position chart showing all players' ranks over time.
    Returns JSON data for Chart.js line chart.
    """
    from collections import defaultdict

    # Get all snapshots ordered by date
    snapshots = LeaderboardHistory.query.order_by(LeaderboardHistory.snapshot_date).all()

    if not snapshots:
        return jsonify({"dates": [], "datasets": []})

    # Organize data by player
    player_data = defaultdict(lambda: {"name": "", "ranks": [], "dates": []})

    for snapshot in snapshots:
        player_id = snapshot.player_id
        if not player_data[player_id]["name"]:
            player_data[player_id]["name"] = snapshot.player.name

        player_data[player_id]["dates"].append(snapshot.snapshot_date.strftime("%Y-%m-%d"))
        player_data[player_id]["ranks"].append(snapshot.rank)

    # Get all unique dates (sorted)
    all_dates = sorted(set(snapshot.snapshot_date for snapshot in snapshots))
    date_strings = [d.strftime("%Y-%m-%d") for d in all_dates]

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


@app.route("/api/players/<int:player_id>/position-history")
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


# Tournament helper functions
def generate_tournament_bracket(tournament_id, player_ids):
    """
    Generate a single-elimination tournament bracket.
    Uses power-of-2 bracket structure with byes for odd numbers.
    """
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        return False

    num_players = len(player_ids)
    if num_players < 2:
        return False

    # Calculate number of rounds needed (log2 of next power of 2)
    num_rounds = math.ceil(math.log2(num_players))
    total_matches_in_first_round = 2 ** (num_rounds - 1)

    # Get players and randomize their order
    players = Player.query.filter(Player.id.in_(player_ids)).all()
    random.shuffle(players)

    # Create participants with seeding (after randomization)
    for idx, player in enumerate(players):
        participant = TournamentParticipant(
            tournament_id=tournament_id,
            player_id=player.id,
            seed=idx + 1
        )
        db.session.add(participant)

    # Create bracket structure from finals backwards
    match_map = {}  # Map of (round, match_number) to match object

    # Create finals (round 1)
    finals = TournamentMatch(
        tournament_id=tournament_id,
        round_number=1,
        match_number=1
    )
    db.session.add(finals)
    db.session.flush()
    match_map[(1, 1)] = finals

    # Create earlier rounds
    for round_num in range(2, num_rounds + 1):
        matches_in_round = 2 ** (round_num - 1)
        for match_num in range(1, matches_in_round + 1):
            match = TournamentMatch(
                tournament_id=tournament_id,
                round_number=round_num,
                match_number=match_num,
                next_match_id=match_map[(round_num - 1, (match_num + 1) // 2)].id
            )
            db.session.add(match)
            db.session.flush()
            match_map[(round_num, match_num)] = match

    # Assign players to first round using proper tournament seeding
    first_round_matches = sorted(
        [m for r, m in match_map.items() if r[0] == num_rounds],
        key=lambda x: x.match_number
    )

    # Calculate number of byes needed (higher seeds get byes)
    bracket_size = 2 ** num_rounds
    num_byes = bracket_size - num_players

    # Standard bracket seeding order for power of 2
    # For 8 players: [1,8, 4,5, 2,7, 3,6]
    def get_seeding_for_round(n):
        if n == 1:
            return [1, 2]
        prev = get_seeding_for_round(n - 1)
        size = 2 ** n
        result = []
        for seed in prev:
            result.append(seed)
            result.append(size + 1 - seed)
        return result

    seeding_order = get_seeding_for_round(num_rounds)

    # Assign players and byes
    # Top seeds (lowest numbers) get byes when needed
    for i, match in enumerate(first_round_matches):
        seed1 = seeding_order[i * 2]
        seed2 = seeding_order[i * 2 + 1]

        # Assign player if seed is within player count, otherwise bye
        player1_id = players[seed1 - 1].id if seed1 <= num_players else None
        player2_id = players[seed2 - 1].id if seed2 <= num_players else None

        match.player1_id = player1_id
        match.player2_id = player2_id

        # Handle byes - if only one player, they automatically advance
        if match.player1_id and not match.player2_id:
            match.winner_id = match.player1_id
            advance_winner(match, auto_advance_byes=True)
        elif match.player2_id and not match.player1_id:
            match.winner_id = match.player2_id
            advance_winner(match, auto_advance_byes=True)

    db.session.commit()
    return True


def advance_winner(match, auto_advance_byes=False):
    """Advance the winner of a match to the next round.

    Args:
        match: The match whose winner should advance
        auto_advance_byes: If True, automatically advance through byes (used during bracket setup)
    """
    if match.winner_id and match.next_match_id:
        next_match = TournamentMatch.query.get(match.next_match_id)
        if next_match:
            # Determine which slot to fill in next match
            parent_matches = TournamentMatch.query.filter_by(
                next_match_id=match.next_match_id
            ).order_by(TournamentMatch.match_number).all()

            if parent_matches[0].id == match.id:
                next_match.player1_id = match.winner_id
            else:
                next_match.player2_id = match.winner_id

            # Only auto-advance through byes during initial bracket setup
            if auto_advance_byes:
                # Get both parent matches feeding into the next match
                parent_matches = TournamentMatch.query.filter_by(
                    next_match_id=next_match.id
                ).all()

                # Check if BOTH parent matches are resolved (have winners or are byes)
                both_parents_resolved = all(
                    parent.winner_id is not None for parent in parent_matches
                )

                # Only auto-advance if both parents are resolved and one slot is still empty
                # (This means it's a true bye, not waiting for a match result)
                if both_parents_resolved:
                    if next_match.player1_id and not next_match.player2_id:
                        next_match.winner_id = next_match.player1_id
                        advance_winner(next_match, auto_advance_byes=True)
                    elif next_match.player2_id and not next_match.player1_id:
                        next_match.winner_id = next_match.player2_id
                        advance_winner(next_match, auto_advance_byes=True)


# Tournament Routes
@app.route("/tournaments")
def tournaments():
    return render_template("tournaments.html")


@app.route("/tournaments/<int:tournament_id>")
def tournament_detail(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    return render_template("tournament_detail.html", tournament=tournament)


# Tournament API Routes
@app.route("/api/tournaments/players/select", methods=["GET"])
def get_tournament_players():
    players = Player.query.order_by(Player.elo_rating.desc()).all()
    return render_template("partials/player_selection.html", players=players)


@app.route("/api/tournaments", methods=["GET"])
def get_tournaments():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    pagination = Tournament.query.order_by(Tournament.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "partials/tournaments_list.html",
        tournaments=pagination.items,
        current_page=pagination.page,
        total_pages=pagination.pages,
    )


@app.route("/api/tournaments", methods=["POST"])
def create_tournament():
    name = request.form.get("name", "").strip()
    player_ids = request.form.getlist("player_ids")

    if not name:
        return "<div class='alert alert-danger'>Tournament name is required</div>"

    if len(player_ids) < 2:
        return "<div class='alert alert-danger'>At least 2 players are required</div>"

    try:
        player_ids = [int(pid) for pid in player_ids]
    except ValueError:
        return "<div class='alert alert-danger'>Invalid player selection</div>"

    tournament = Tournament(name=name, status="setup")
    db.session.add(tournament)
    db.session.flush()

    # Generate bracket
    if not generate_tournament_bracket(tournament.id, player_ids):
        db.session.rollback()
        return "<div class='alert alert-danger'>Failed to generate tournament bracket</div>"

    tournament.status = "active"
    tournament.started_at = datetime.now(timezone.utc)
    db.session.commit()

    # Return redirect instruction for htmx
    response = make_response("")
    response.headers['HX-Redirect'] = url_for("tournament_detail", tournament_id=tournament.id)
    return response


@app.route("/api/tournaments/<int:tournament_id>/bracket")
def get_tournament_bracket(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    matches = TournamentMatch.query.filter_by(tournament_id=tournament_id).order_by(
        TournamentMatch.round_number.desc(), TournamentMatch.match_number
    ).all()

    # Group matches by round
    rounds = {}
    for match in matches:
        if match.round_number not in rounds:
            rounds[match.round_number] = []
        rounds[match.round_number].append(match)

    return render_template(
        "partials/tournament_bracket.html",
        tournament=tournament,
        rounds=rounds,
        max_round=max(rounds.keys()) if rounds else 0
    )


@app.route("/api/tournaments/<int:tournament_id>/matches/<int:match_id>/form", methods=["GET"])
def get_match_form(tournament_id, match_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    match = TournamentMatch.query.filter_by(
        id=match_id, tournament_id=tournament_id
    ).first_or_404()

    if not match.player1_id or not match.player2_id:
        return "<div class='alert alert-warning'>Match is not ready (missing players)</div>"

    if match.winner_id:
        return "<div class='alert alert-info'>Match already completed</div>"

    return render_template("partials/match_form.html", tournament=tournament, match=match)


@app.route("/api/tournaments/<int:tournament_id>/matches/<int:match_id>", methods=["POST"])
def record_tournament_match(tournament_id, match_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    match = TournamentMatch.query.filter_by(
        id=match_id, tournament_id=tournament_id
    ).first_or_404()

    # Helper function to return form with error
    def return_form_with_error(error_msg):
        response = make_response(render_template("partials/match_form.html", tournament=tournament, match=match, error=error_msg))
        response.headers['HX-Retarget'] = f'#match-{match.id}'
        response.headers['HX-Reswap'] = 'outerHTML'
        return response

    if match.winner_id:
        return return_form_with_error("Match already completed")

    if not match.player1_id or not match.player2_id:
        return return_form_with_error("Match is not ready (missing players)")

    team1_score = request.form.get("team1_score", type=int)
    team2_score = request.form.get("team2_score", type=int)

    # Validate scores
    if team1_score is None or team2_score is None:
        return return_form_with_error("Both scores are required")

    if team1_score < 0 or team2_score < 0:
        return return_form_with_error("Scores cannot be negative!")

    if team1_score > 11 or team2_score > 11:
        return return_form_with_error("Maximum score is 11!")

    # Validate that it's not a draw
    if team1_score == team2_score:
        return return_form_with_error("Draw games are not allowed. One team must win!")

    # Determine winner based on score
    winner_id = match.player1_id if team1_score > team2_score else match.player2_id

    # Create the actual game record
    game = Game(
        game_type="1v1",
        team1_score=team1_score,
        team2_score=team2_score,
        start_time=datetime.now(timezone.utc)
    )
    db.session.add(game)
    db.session.flush()

    # Link players to game
    gp1 = GamePlayer(
        game_id=game.id,
        player_id=match.player1_id,
        team=1,
        is_winner=(winner_id == match.player1_id)
    )
    gp2 = GamePlayer(
        game_id=game.id,
        player_id=match.player2_id,
        team=2,
        is_winner=(winner_id == match.player2_id)
    )
    db.session.add(gp1)
    db.session.add(gp2)

    # Update ELO ratings
    update_elo_ratings(game)

    # Update tournament match
    match.winner_id = winner_id
    match.game_id = game.id

    # Advance winner to next round
    advance_winner(match)

    # Commit the transaction first to ensure all changes are saved
    db.session.commit()

    # Create daily snapshot after committing the game
    try:
        create_daily_snapshot()
    except Exception as snapshot_error:
        # Log error but don't fail the tournament match creation
        print(f"Warning: Failed to create daily snapshot: {snapshot_error}")

    # Check if tournament is complete (must be after commit)
    finals = TournamentMatch.query.filter_by(
        tournament_id=tournament_id, round_number=1
    ).first()

    if finals and finals.winner_id and finals.game_id:
        # Finals has been played and has a winner - tournament is complete
        tournament.status = "completed"
        tournament.completed_at = datetime.now(timezone.utc)
        db.session.commit()

    # Return updated bracket HTML directly (not a redirect)
    matches = TournamentMatch.query.filter_by(tournament_id=tournament_id).order_by(
        TournamentMatch.round_number.desc(), TournamentMatch.match_number
    ).all()

    # Group matches by round
    rounds = {}
    for match_obj in matches:
        if match_obj.round_number not in rounds:
            rounds[match_obj.round_number] = []
        rounds[match_obj.round_number].append(match_obj)

    # On success, return bracket with headers to target the bracket container
    response = make_response(render_template(
        "partials/tournament_bracket.html",
        tournament=tournament,
        rounds=rounds,
        max_round=max(rounds.keys()) if rounds else 0
    ))
    response.headers['HX-Retarget'] = '#tournament-bracket'
    response.headers['HX-Reswap'] = 'innerHTML'
    return response


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0")
