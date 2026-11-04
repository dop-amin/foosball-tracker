"""Blueprint for tournament-related routes and API."""

from flask import Blueprint, render_template, request, url_for, make_response
from datetime import datetime, timezone
from models import db, Player, Game, Tournament, TournamentMatch
from services.game_service import GameValidationError, add_game_players, validate_scores
from services.tournament_service import generate_tournament_bracket, advance_winner
from services.recalculation_service import recalculate_all_derived_data
from services.elo_service import INITIAL_ELO, season_ratings
from services.season_service import get_current_season, get_season_for_date

tournaments_bp = Blueprint("tournaments", __name__)


def _render_bracket(tournament):
    """Render the bracket partial, matches grouped by round."""
    matches = TournamentMatch.query.filter_by(tournament_id=tournament.id).order_by(
        TournamentMatch.round_number.desc(), TournamentMatch.match_number
    ).all()

    rounds = {}
    for match in matches:
        rounds.setdefault(match.round_number, []).append(match)

    return render_template(
        "partials/tournament_bracket.html",
        tournament=tournament,
        rounds=rounds,
        max_round=max(rounds.keys()) if rounds else 0
    )


# Tournament API Routes
@tournaments_bp.route("/api/tournaments/players/select", methods=["GET"])
def get_tournament_players():
    ratings = season_ratings(get_current_season().id)
    players = sorted(
        Player.query.all(),
        key=lambda p: ratings.get(p.id, INITIAL_ELO),
        reverse=True,
    )
    return render_template(
        "partials/player_selection.html",
        players=players,
        ratings=ratings,
        initial_elo=INITIAL_ELO,
    )


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
    return _render_bracket(tournament)


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

    try:
        validate_scores(team1_score, team2_score)
    except GameValidationError as e:
        return return_form_with_error(str(e))

    # Determine winner based on score
    winner_id = match.player1_id if team1_score > team2_score else match.player2_id

    # Create the actual game record (naive local time, like manually recorded games).
    # Look up the season first: it may roll back the session on a race.
    start_time = datetime.now()
    season = get_season_for_date(start_time)
    game = Game(
        season_id=season.id,
        game_type="1v1",
        team1_score=team1_score,
        team2_score=team2_score,
        start_time=start_time,
    )
    add_game_players(game, [match.player1_id], [match.player2_id])
    db.session.add(game)
    db.session.flush()

    # Update tournament match
    match.winner_id = winner_id
    match.game_id = game.id

    # Advance winner to next round
    advance_winner(match)

    # Finals played - tournament is complete
    if match.round_number == 1:
        tournament.status = "completed"
        tournament.completed_at = datetime.now(timezone.utc)

    # Update ELO ratings, cake balances and snapshots for the season, then
    # commit everything in one transaction
    recalculate_all_derived_data(season_id=season.id, since=start_time.date())

    # On success, return bracket with headers to target the bracket container
    response = make_response(_render_bracket(tournament))
    response.headers['HX-Retarget'] = '#tournament-bracket'
    response.headers['HX-Reswap'] = 'innerHTML'
    return response
