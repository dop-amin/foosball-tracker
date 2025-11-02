"""Blueprint for player-related API routes."""

from flask import Blueprint, render_template, request
from models import db, Player

players_bp = Blueprint("players", __name__)


@players_bp.route("/players", methods=["GET"])
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


@players_bp.route("/players", methods=["POST"])
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
