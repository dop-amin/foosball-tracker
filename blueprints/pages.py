"""Blueprint for page routes (non-API routes that return full HTML pages)."""

from flask import Blueprint, render_template
from models import Player, Tournament

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    return render_template("index.html")


@pages_bp.route("/players")
def players():
    return render_template("players.html")


@pages_bp.route("/games")
def games():
    return render_template("games.html")


@pages_bp.route("/leaderboard")
def leaderboard():
    return render_template("leaderboard.html")


@pages_bp.route("/statistics")
def statistics():
    return render_template("statistics.html")


@pages_bp.route("/players/<int:player_id>")
def player_detail(player_id):
    player = Player.query.get_or_404(player_id)
    return render_template("player_detail.html", player=player)


@pages_bp.route("/tournaments")
def tournaments():
    return render_template("tournaments.html")


@pages_bp.route("/tournaments/<int:tournament_id>")
def tournament_detail(tournament_id):
    tournament = Tournament.query.get_or_404(tournament_id)
    return render_template("tournament_detail.html", tournament=tournament)
