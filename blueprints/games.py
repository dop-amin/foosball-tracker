"""Blueprint for game-related API routes."""

from flask import Blueprint, render_template, request
from sqlalchemy import func
from dateutil.parser import parse
from datetime import datetime, timedelta
from models import db, Player, Game, GamePlayer, CakeBalance, TournamentMatch, GameAuditLog
from services.elo_service import update_elo_ratings
from services.game_service import update_cake_balance, create_game_audit_entry
from services.leaderboard_service import create_daily_snapshot
from services.recalculation_service import recalculate_all_derived_data
from services.season_service import get_season_for_date, get_current_season

games_bp = Blueprint("games", __name__)


@games_bp.route("/games", methods=["GET"])
def get_games():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = Game.query.order_by(Game.start_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get IDs of games that are linked to tournaments (cannot be edited)
    tournament_game_ids = {match.game_id for match in TournamentMatch.query.filter(TournamentMatch.game_id.isnot(None)).all()}

    return render_template(
        "partials/games_list.html",
        games=pagination.items,
        current_page=pagination.page,
        total_pages=pagination.pages,
        tournament_game_ids=tournament_game_ids,
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

        # Assign game to correct season based on start_time
        season = get_season_for_date(start_time)

        # Create game
        game = Game(
            season_id=season.id,
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

        # Create daily snapshot for the game's season after committing the game
        try:
            create_daily_snapshot(season_id=game.season_id)
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


@games_bp.route("/games/<int:game_id>/edit-form", methods=["GET"])
def get_game_edit_form(game_id):
    """Return inline edit form HTML for a game."""
    game = Game.query.get_or_404(game_id)

    # Check if game is linked to tournament
    tournament_match = TournamentMatch.query.filter_by(game_id=game_id).first()
    if tournament_match:
        return (
            '<tr><td colspan="7"><div class="alert alert-danger">This game is part of a tournament and cannot be edited. Please contact the tournament organizer.</div></td></tr>',
            200,
        )

    # Check if game is older than 7 days
    age_limit = datetime.utcnow() - timedelta(days=7)
    if game.start_time < age_limit:
        return (
            '<tr><td colspan="7"><div class="alert alert-danger">Games older than 7 days cannot be edited to maintain historical integrity.</div></td></tr>',
            200,
        )

    # Load all players for dropdowns
    players = Player.query.order_by(func.lower(Player.name)).all()

    # Get current player IDs for each team
    team1_player_ids = [gp.player_id for gp in game.players if gp.team == 1]
    team2_player_ids = [gp.player_id for gp in game.players if gp.team == 2]

    return render_template(
        "partials/game_edit_form.html",
        game=game,
        players=players,
        team1_player_ids=team1_player_ids,
        team2_player_ids=team2_player_ids,
    )


@games_bp.route("/games/<int:game_id>", methods=["POST", "PUT"])
def update_game(game_id):
    """Update a game and create audit log."""
    try:
        game = Game.query.get_or_404(game_id)

        # Check if game is linked to tournament
        tournament_match = TournamentMatch.query.filter_by(game_id=game_id).first()
        if tournament_match:
            return (
                '<div class="alert alert-danger">This game is part of a tournament and cannot be edited.</div>',
                200,
            )

        # Check if game is older than 7 days
        age_limit = datetime.utcnow() - timedelta(days=7)
        if game.start_time < age_limit:
            return (
                '<div class="alert alert-danger">Games older than 7 days cannot be edited.</div>',
                200,
            )

        # Capture before state (including season for potential reassignment)
        old_season_id = game.season_id
        before_data = {
            'scores': {'team1': game.team1_score, 'team2': game.team2_score},
            'players': {
                'team1': sorted([gp.player_id for gp in game.players if gp.team == 1]),
                'team2': sorted([gp.player_id for gp in game.players if gp.team == 2])
            },
            'game_type': game.game_type,
            'start_time': game.start_time.isoformat() if game.start_time else None,
            'end_time': game.end_time.isoformat() if game.end_time else None,
        }

        # Parse new data
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

        # Get player lists
        team1_players = request.form.getlist("team1_players")
        team2_players = request.form.getlist("team2_players")

        # Validate that no player appears on both teams
        team1_ids = [int(p) for p in team1_players if p]
        team2_ids = [int(p) for p in team2_players if p]

        duplicate_players = set(team1_ids) & set(team2_ids)
        if duplicate_players:
            return '<div class="alert alert-danger">A player cannot play against themselves!</div>', 200

        # Capture after state for audit log
        after_data = {
            'scores': {'team1': team1_score, 'team2': team2_score},
            'players': {
                'team1': sorted(team1_ids),
                'team2': sorted(team2_ids)
            },
            'game_type': game_type,
            'start_time': start_time.isoformat() if start_time else None,
            'end_time': end_time.isoformat() if end_time else None,
        }

        # Reassign game to correct season if start_time changed
        new_season = get_season_for_date(start_time)

        # Update game record
        game.season_id = new_season.id
        game.game_type = game_type
        game.start_time = start_time
        game.end_time = end_time
        game.team1_score = team1_score
        game.team2_score = team2_score

        # Delete old GamePlayer records
        GamePlayer.query.filter_by(game_id=game_id).delete()

        # Determine winners
        team1_wins = team1_score > team2_score

        # Create new GamePlayer records
        for player_id in team1_ids:
            game_player = GamePlayer(
                game_id=game.id,
                player_id=player_id,
                team=1,
                is_winner=team1_wins,
            )
            db.session.add(game_player)

        for player_id in team2_ids:
            game_player = GamePlayer(
                game_id=game.id,
                player_id=player_id,
                team=2,
                is_winner=not team1_wins,
            )
            db.session.add(game_player)

        # Create audit log entry
        audit_log = create_game_audit_entry(
            game, before_data, after_data, request.remote_addr
        )
        db.session.add(audit_log)

        # Commit the game update and audit log before recalculation
        db.session.commit()

        # Recalculate derived data for affected seasons
        if old_season_id == new_season.id:
            # Game stayed in same season, just recalculate that season
            recalculate_all_derived_data(season_id=new_season.id)
        else:
            # Game moved to different season, recalculate both seasons
            recalculate_all_derived_data(season_id=old_season_id)
            recalculate_all_derived_data(season_id=new_season.id)

            # Also recalculate current season if it's different from both
            current_season = get_current_season()
            if current_season.id not in [old_season_id, new_season.id]:
                recalculate_all_derived_data(season_id=current_season.id)

        # Reload game to get updated relationships
        db.session.refresh(game)

        # Get tournament game IDs for rendering
        tournament_game_ids = {match.game_id for match in TournamentMatch.query.filter(TournamentMatch.game_id.isnot(None)).all()}

        # Return updated game row
        return render_template(
            "partials/game_row.html",
            game=game,
            tournament_game_ids=tournament_game_ids,
        )

    except Exception as e:
        db.session.rollback()
        return f'<div class="alert alert-danger">Error: {str(e)}</div>', 200


@games_bp.route("/games/<int:game_id>/history", methods=["GET"])
def get_game_history(game_id):
    """Return audit log history for a game."""
    audit_logs = GameAuditLog.query.filter_by(game_id=game_id).order_by(GameAuditLog.edited_at.desc()).all()

    return render_template(
        "partials/game_audit_history.html",
        game_id=game_id,
        audit_logs=audit_logs,
    )


@games_bp.route("/games/<int:game_id>/cancel-edit", methods=["GET"])
def cancel_edit_game(game_id):
    """Return non-editable game row (for cancel button)."""
    game = Game.query.get_or_404(game_id)

    # Get tournament game IDs for rendering
    tournament_game_ids = {match.game_id for match in TournamentMatch.query.filter(TournamentMatch.game_id.isnot(None)).all()}

    return render_template(
        "partials/game_row.html",
        game=game,
        tournament_game_ids=tournament_game_ids,
    )


@games_bp.route("/games/<int:game_id>/hide-history", methods=["GET"])
def hide_game_history(game_id):
    """Return empty response to remove history row."""
    return ""
