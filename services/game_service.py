"""Game recording and cake balance management service."""

import json
from models import db, CakeBalance, GameAuditLog


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


def create_game_audit_entry(game, before_data, after_data, editor_ip):
    """
    Create an audit log entry documenting changes to a game.

    Args:
        game: Game object being edited
        before_data: Dict with before state {scores, players, game_type, times}
        after_data: Dict with after state {scores, players, game_type, times}
        editor_ip: IP address of the editor

    Returns:
        GameAuditLog object
    """
    changes = {}
    summary_parts = []

    # Compare scores
    if before_data['scores'] != after_data['scores']:
        changes['scores'] = {'before': before_data['scores'], 'after': after_data['scores']}
        summary_parts.append(f"Changed scores from {before_data['scores']['team1']}-{before_data['scores']['team2']} to {after_data['scores']['team1']}-{after_data['scores']['team2']}")

    # Compare players
    if before_data['players'] != after_data['players']:
        changes['players'] = {'before': before_data['players'], 'after': after_data['players']}
        summary_parts.append("Changed player assignments")

    # Compare game type
    if before_data['game_type'] != after_data['game_type']:
        changes['game_type'] = {'before': before_data['game_type'], 'after': after_data['game_type']}
        summary_parts.append(f"Changed game type from {before_data['game_type']} to {after_data['game_type']}")

    # Compare times
    if before_data['start_time'] != after_data['start_time']:
        changes['start_time'] = {'before': before_data['start_time'], 'after': after_data['start_time']}
        summary_parts.append("Updated start time")

    if before_data.get('end_time') != after_data.get('end_time'):
        changes['end_time'] = {'before': before_data.get('end_time'), 'after': after_data.get('end_time')}
        summary_parts.append("Updated end time")

    summary = '; '.join(summary_parts)

    audit_log = GameAuditLog(
        game_id=game.id,
        editor_ip=editor_ip,
        changes=json.dumps(changes),
        summary=summary
    )

    return audit_log
