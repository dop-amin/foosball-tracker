"""Service for recalculating all derived data after game edits."""

from models import db, Game, GamePlayer, CakeBalance
from services.elo_service import recalculate_all_elo_ratings
from services.leaderboard_service import recalculate_historical_snapshots
from services.game_service import update_cake_balance


def recalculate_all_derived_data():
    """
    Recalculate all derived data (ELO, cake balances, leaderboard history).
    Must be called after editing any game to maintain data integrity.
    """
    # 1. Clear all ELO changes
    GamePlayer.query.update({GamePlayer.elo_change: None})

    # 2. Recalculate ELO ratings from scratch
    recalculate_all_elo_ratings()

    # 3. Rebuild cake balances
    CakeBalance.query.delete()
    games = Game.query.order_by(Game.start_time).all()
    for game in games:
        if game.is_shutout:
            update_cake_balance(game)

    # 4. Recalculate historical snapshots
    recalculate_historical_snapshots()

    db.session.commit()
