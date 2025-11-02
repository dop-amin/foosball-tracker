from flask import Flask
from flask_migrate import Migrate
from config import Config
from models import db
from services.elo_service import recalculate_all_elo_ratings


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    # Register blueprints
    from blueprints.pages import pages_bp
    from blueprints.players import players_bp
    from blueprints.games import games_bp
    from blueprints.leaderboard import leaderboard_bp
    from blueprints.statistics import statistics_bp
    from blueprints.tournaments import tournaments_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(players_bp, url_prefix="/api")
    app.register_blueprint(games_bp, url_prefix="/api")
    app.register_blueprint(leaderboard_bp, url_prefix="/api")
    app.register_blueprint(statistics_bp, url_prefix="/api")
    app.register_blueprint(tournaments_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.create_all()
        # Recalculate ELO ratings on startup
        recalculate_all_elo_ratings()
    app.run(debug=True, host="0.0.0.0")
