import os
from flask import Flask
from flask_migrate import Migrate
from config import Config
from models import db
from services.recalculation_service import recalculate_all_derived_data
from services.season_service import get_current_season


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
    debug = os.environ.get("FLASK_DEBUG", "1").lower() not in ("0", "false", "no")
    # With the reloader, this block also runs in the parent watcher process;
    # only initialise the database once (in the serving process).
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        with app.app_context():
            db.create_all()
            # Ensure current season exists (auto-transitions if needed)
            get_current_season()
            # Rebuild all derived data (ELO, cakes, snapshots) on startup
            recalculate_all_derived_data()
    app.run(
        debug=debug,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "5000")),
    )
