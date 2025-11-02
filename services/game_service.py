"""Game recording and cake balance management service."""

from models import db, CakeBalance


def update_cake_balance(game):
    """
    Update cake balance for shutout games (10-0).
    Each loser owes each winner a cake.

    Args:
        game: Game object with shutout result
    """
    winners = []
    losers = []

    for gp in game.players:
        if gp.is_winner:
            winners.append(gp.player_id)
        else:
            losers.append(gp.player_id)

    # Each loser owes each winner a cake
    for loser_id in losers:
        for winner_id in winners:
            balance = CakeBalance.query.filter_by(
                debtor_id=loser_id, creditor_id=winner_id
            ).first()

            if balance:
                balance.balance += 1
            else:
                balance = CakeBalance(
                    debtor_id=loser_id, creditor_id=winner_id, balance=1
                )
                db.session.add(balance)
