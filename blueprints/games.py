"""Blueprint for game-related API routes."""

from flask import Blueprint, render_template, request
from sqlalchemy import func
from dateutil.parser import parse
from models import db, Player, Game, GamePlayer, CakeBalance
from services.elo_service import update_elo_ratings
from services.game_service import update_cake_balance
from services.leaderboard_service import create_daily_snapshot

games_bp = Blueprint("games", __name__)


@games_bp.route("/games", methods=["GET"])
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


@games_bp.route("/games", methods=["POST"])
def add_game():
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


@games_bp.route("/game-form")
def get_game_form():
    game_type = request.args.get("game_type")
    players = Player.query.order_by(func.lower(Player.name)).all()
    return render_template(
        "partials/game_form.html", game_type=game_type, players=players
    )


@games_bp.route("/recent-games")
def get_recent_games():
    recent_games = Game.query.order_by(Game.start_time.desc()).limit(5).all()
    return render_template("partials/recent_games.html", games=recent_games)


@games_bp.route("/cake-balances")
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
