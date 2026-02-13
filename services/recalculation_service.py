"""Service for recalculating all derived data after game edits."""

from models import db, Game, GamePlayer, CakeBalance
from services.elo_service import recalculate_all_elo_ratings
from services.leaderboard_service import recalculate_historical_snapshots
from services.game_service import update_cake_balance


def recalculate_all_derived_data(season_id=None):
    """
    Recalculate all derived data (ELO, cake balances, leaderboard history).
    Must be called after editing any game to maintain data integrity.

    Args:
        season_id: Optional season ID to recalculate. If provided, only recalculates
                   data for that season. If None, recalculates all seasons.
    """
    # 1. Clear ELO changes (for all games or specific season)
    if season_id is not None:
        # Clear ELO changes for games in this season
        db.session.query(GamePlayer).filter(
            GamePlayer.game_id.in_(
                db.session.query(Game.id).filter_by(season_id=season_id)
            )
        ).update({GamePlayer.elo_change: None}, synchronize_session=False)
    else:
        GamePlayer.query.update({GamePlayer.elo_change: None})

    # 2. Recalculate ELO ratings from scratch
    recalculate_all_elo_ratings(season_id=season_id)

    # 3. Rebuild cake balances
    if season_id is not None:
        # Delete only cake balances for this season
        CakeBalance.query.filter_by(season_id=season_id).delete()
        # Rebuild cake balances for this season
        games = Game.query.filter_by(season_id=season_id).order_by(Game.start_time).all()
    else:
        # Delete all cake balances
        CakeBalance.query.delete()
        # Rebuild all cake balances
        games = Game.query.order_by(Game.start_time).all()

    for game in games:
        if game.is_shutout:
            update_cake_balance(game)

    # 4. Recalculate historical snapshots
    recalculate_historical_snapshots(season_id=season_id)

    db.session.commit()
