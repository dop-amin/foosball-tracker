"""Blueprint for game-related API routes."""

from flask import Blueprint, render_template, request
from markupsafe import escape
from sqlalchemy import func
from sqlalchemy.orm import aliased
from datetime import datetime, timedelta
from models import db, Player, Game, CakeBalance, TournamentMatch, GameAuditLog
from services.game_service import (
    GAME_TYPE_TEAM_SIZES,
    GameValidationError,
    add_game_players,
    create_game_audit_entry,
    parse_game_form,
)
from services.recalculation_service import recalculate_all_derived_data
from services.season_service import get_season_for_date

games_bp = Blueprint("games", __name__)

EDIT_WINDOW = timedelta(days=7)


def _error(message):
    return f'<div class="alert alert-danger">{escape(message)}</div>', 200


def _tournament_game_ids():
    return {
        game_id
        for (game_id,) in db.session.query(TournamentMatch.game_id).filter(
            TournamentMatch.game_id.isnot(None)
        )
    }


def _edit_block_reason(game):
    """Why ``game`` cannot be edited, or None if it can."""
    if TournamentMatch.query.filter_by(game_id=game.id).first():
        return "This game is part of a tournament and cannot be edited."
    if game.start_time < datetime.now() - EDIT_WINDOW:
        return f"Games older than {EDIT_WINDOW.days} days cannot be edited."
    return None


def _edit_error(game_id, message):
    """
    Error for the inline edit form.

    The form swaps its response over the whole table row, so errors are
    retargeted into the form's error slot instead, keeping the user's edits.
    """
    body, status = _error(message)
    return body, status, {
        "HX-Retarget": f"#edit-error-{game_id}",
        "HX-Reswap": "innerHTML",
    }


@games_bp.route("/games", methods=["GET"])
def get_games():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    pagination = Game.query.order_by(Game.start_time.desc(), Game.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template(
        "partials/games_list.html",
        games=pagination.items,
        current_page=pagination.page,
        total_pages=pagination.pages,
        # Games linked to tournaments cannot be edited
        tournament_game_ids=_tournament_game_ids(),
    )


@games_bp.route("/games", methods=["POST"])
def add_game():
    try:
        data = parse_game_form(request.form)
    except GameValidationError as e:
        return _error(str(e))

    try:
        # Assign game to correct season based on start_time (before any other
        # change: it may roll back the session if the season is created concurrently)
        season = get_season_for_date(data["start_time"])

        game = Game(
            season_id=season.id,
            game_type=data["game_type"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            team1_score=data["team1_score"],
            team2_score=data["team2_score"],
        )
        add_game_players(game, data["team1_ids"], data["team2_ids"])
        db.session.add(game)
        db.session.flush()

        # Replay the season: ELO changes, cake balances and snapshots stay
        # correct even for back-dated games or games of past seasons
        recalculate_all_derived_data(
            season_id=season.id, since=data["start_time"].date()
        )

        return '<div class="alert alert-success">Game recorded successfully!</div>', 201

    except Exception as e:
        db.session.rollback()
        return _error(f"Error: {e}")


@games_bp.route("/game-form")
def get_game_form():
    game_type = request.args.get("game_type")
    # In 2v1 games: which side the two players are on ("black" or "white")
    two_side = request.args.get("two_side", "black")
    sizes = GAME_TYPE_TEAM_SIZES.get(game_type)
    team1_size, team2_size = 0, 0
    if sizes:
        # 2v1 allows both (2, 1) and (1, 2): two_side picks one
        team1_size, team2_size = (1, 2) if (1, 2) in sizes and two_side == "white" else max(sizes)
    players = Player.query.order_by(func.lower(Player.name)).all()
    return render_template(
        "partials/game_form.html",
        game_type=game_type,
        two_side=two_side,
        team1_size=team1_size,
        team2_size=team2_size,
        players=players,
    )


@games_bp.route("/recent-games")
def get_recent_games():
    recent_games = Game.query.order_by(Game.start_time.desc(), Game.id.desc()).limit(5).all()
    return render_template("partials/recent_games.html", games=recent_games)


@games_bp.route("/cake-balances")
def get_cake_balances():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Unpaid cakes don't expire at season rollover: sum each pair's debts over
    # all seasons (the same scope as the player stats page)
    debtor = aliased(Player)
    creditor = aliased(Player)
    total = func.sum(CakeBalance.balance)
    pagination = (
        db.session.query(
            debtor.name.label("debtor_name"),
            creditor.name.label("creditor_name"),
            total.label("balance"),
        )
        .join(debtor, debtor.id == CakeBalance.debtor_id)
        .join(creditor, creditor.id == CakeBalance.creditor_id)
        .group_by(CakeBalance.debtor_id, CakeBalance.creditor_id)
        .having(total > 0)
        .order_by(total.desc(), func.lower(debtor.name), func.lower(creditor.name))
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

    reason = _edit_block_reason(game)
    if reason:
        body, status = _error(reason)
        return f'<tr><td colspan="7">{body}</td></tr>', status

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
    game = db.session.get(Game, game_id)
    if game is None:
        return _edit_error(game_id, "This game no longer exists.")

    reason = _edit_block_reason(game)
    if reason:
        return _edit_error(game_id, reason)

    try:
        data = parse_game_form(request.form)
    except GameValidationError as e:
        return _edit_error(game_id, str(e))

    # Moving a game further into the past would bypass the edit window
    if data["start_time"] < datetime.now() - EDIT_WINDOW:
        return _edit_error(
            game_id, f"Games cannot be moved to a date older than {EDIT_WINDOW.days} days."
        )

    try:
        # Reassign game to the season of its (possibly changed) start_time.
        # Done before any other change: it may roll back the session if the
        # season is created concurrently.
        new_season = get_season_for_date(data["start_time"])

        # Capture before state (including season for potential reassignment)
        old_season_id = game.season_id
        old_day = game.start_time.date()
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

        # Capture after state for audit log
        after_data = {
            'scores': {'team1': data["team1_score"], 'team2': data["team2_score"]},
            'players': {
                'team1': sorted(data["team1_ids"]),
                'team2': sorted(data["team2_ids"])
            },
            'game_type': data["game_type"],
            'start_time': data["start_time"].isoformat(),
            'end_time': data["end_time"].isoformat() if data["end_time"] else None,
        }

        # Update game record
        game.season_id = new_season.id
        game.game_type = data["game_type"]
        game.start_time = data["start_time"]
        game.end_time = data["end_time"]
        game.team1_score = data["team1_score"]
        game.team2_score = data["team2_score"]

        # Replace players (delete-orphan cascade removes the old rows)
        game.players.clear()
        db.session.flush()
        add_game_players(game, data["team1_ids"], data["team2_ids"])

        db.session.add(
            create_game_audit_entry(game, before_data, after_data, request.remote_addr)
        )
        db.session.flush()

        # Recalculate derived data for affected seasons in the same transaction,
        # so a failing recalculation never leaves a half-applied edit behind.
        # Nothing before the earliest affected day can change.
        new_day = data["start_time"].date()
        if old_season_id == new_season.id:
            affected = {new_season.id: min(old_day, new_day)}
        else:
            affected = {old_season_id: old_day, new_season.id: new_day}
        for season_id, since in affected.items():
            recalculate_all_derived_data(season_id=season_id, commit=False, since=since)
        db.session.commit()

        # Return updated game row (tournament games cannot be edited)
        return render_template(
            "partials/game_row.html", game=game, tournament_game_ids=set()
        )

    except Exception as e:
        db.session.rollback()
        return _edit_error(game_id, f"Error: {e}")


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
    is_tournament_game = TournamentMatch.query.filter_by(game_id=game_id).first() is not None

    return render_template(
        "partials/game_row.html",
        game=game,
        tournament_game_ids={game_id} if is_tournament_game else set(),
    )


@games_bp.route("/games/<int:game_id>/hide-history", methods=["GET"])
def hide_game_history(game_id):
    """Return empty response to remove history row."""
    return ""
