"""Blueprint for tournament-related routes and API."""

from flask import Blueprint, render_template, request, url_for, make_response
from datetime import datetime, timezone
from models import db, Player, Game, GamePlayer, Tournament, TournamentMatch
from services.tournament_service import generate_tournament_bracket, advance_winner
from services.elo_service import update_elo_ratings
from services.leaderboard_service import create_daily_snapshot

tournaments_bp = Blueprint("tournaments", __name__)


# Tournament API Routes
@tournaments_bp.route("/api/tournaments/players/select", methods=["GET"])
def get_tournament_players():
    players = Player.query.order_by(Player.elo_rating.desc()).all()
    return render_template("partials/player_selection.html", players=players)


@tournaments_bp.route("/api/tournaments", methods=["GET"])
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


@tournaments_bp.route("/api/tournaments", methods=["POST"])
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
    response.headers['HX-Redirect'] = url_for("pages.tournament_detail", tournament_id=tournament.id)
    return response


@tournaments_bp.route("/api/tournaments/<int:tournament_id>/bracket")
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


@tournaments_bp.route("/api/tournaments/<int:tournament_id>/matches/<int:match_id>/form", methods=["GET"])
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


@tournaments_bp.route("/api/tournaments/<int:tournament_id>/matches/<int:match_id>", methods=["POST"])
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
