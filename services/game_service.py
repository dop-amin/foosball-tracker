"""Game form validation and audit log service."""

import json
from datetime import datetime, timedelta
from dateutil.parser import parse
from models import db, Player, GamePlayer, GameAuditLog

MAX_SCORE = 11

# Games cannot lie in the future; this much browser/server clock drift is tolerated
MAX_CLOCK_SKEW = timedelta(minutes=5)

# SQLite integers are signed 64-bit; larger ids would overflow in queries
MAX_PLAYER_ID = 2**63 - 1

# Allowed team sizes per game type (2v1 may be played either way round)
GAME_TYPE_TEAM_SIZES = {
    "1v1": {(1, 1)},
    "2v2": {(2, 2)},
    "2v1": {(2, 1), (1, 2)},
}


class GameValidationError(ValueError):
    """Raised when submitted game data is invalid. The message is user-facing."""


def _parse_datetime(value, field_label):
    try:
        parsed = parse(value)
        # Game times are stored as naive local times
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
    except (ValueError, OverflowError, TypeError):
        raise GameValidationError(f"Invalid {field_label}")
    if parsed > datetime.now() + MAX_CLOCK_SKEW:
        raise GameValidationError(f"The {field_label} cannot be in the future")
    return parsed


def _parse_player_ids(values):
    try:
        ids = [int(v) for v in values if v]
    except ValueError:
        raise GameValidationError("Invalid player selection")
    if any(not 1 <= player_id <= MAX_PLAYER_ID for player_id in ids):
        raise GameValidationError("Unknown player selected")
    return ids


def validate_scores(team1_score, team2_score):
    """
    Validate a game's scores.

    Raises:
        GameValidationError: with a user-facing message
    """
    if team1_score is None or team2_score is None:
        raise GameValidationError("Both scores are required")

    if team1_score < 0 or team2_score < 0:
        raise GameValidationError("Scores cannot be negative!")

    if team1_score > MAX_SCORE or team2_score > MAX_SCORE:
        raise GameValidationError(f"Maximum score is {MAX_SCORE}!")

    if team1_score == team2_score:
        raise GameValidationError("Draw games are not allowed. One team must win!")


def add_game_players(game, team1_ids, team2_ids):
    """Add GamePlayer rows for both teams; winners follow from the scores."""
    team1_wins = game.team1_score > game.team2_score
    for player_id in team1_ids:
        game.players.append(GamePlayer(player_id=player_id, team=1, is_winner=team1_wins))
    for player_id in team2_ids:
        game.players.append(GamePlayer(player_id=player_id, team=2, is_winner=not team1_wins))


def parse_game_form(form):
    """
    Parse and validate a submitted game form.

    Args:
        form: request.form

    Returns:
        dict with game_type, start_time, end_time, team1_score, team2_score,
        team1_ids, team2_ids

    Raises:
        GameValidationError: with a user-facing message
    """
    game_type = form.get("game_type")
    if game_type not in GAME_TYPE_TEAM_SIZES:
        raise GameValidationError("Please select a valid game type")

    start_time = _parse_datetime(form.get("start_time"), "start time")
    end_time = (
        _parse_datetime(form.get("end_time"), "end time")
        if form.get("end_time")
        else None
    )

    # Don't save end_time if it's the same as start_time
    if end_time and end_time == start_time:
        end_time = None
    if end_time and end_time < start_time:
        raise GameValidationError("End time cannot be before start time!")

    try:
        team1_score = int(form.get("team1_score"))
        team2_score = int(form.get("team2_score"))
    except (TypeError, ValueError):
        raise GameValidationError("Both scores are required")

    validate_scores(team1_score, team2_score)

    team1_ids = _parse_player_ids(form.getlist("team1_players"))
    team2_ids = _parse_player_ids(form.getlist("team2_players"))

    if set(team1_ids) & set(team2_ids):
        raise GameValidationError("A player cannot play against themselves!")

    if len(set(team1_ids)) != len(team1_ids) or len(set(team2_ids)) != len(team2_ids):
        raise GameValidationError("A player cannot be selected twice!")

    if (len(team1_ids), len(team2_ids)) not in GAME_TYPE_TEAM_SIZES[game_type]:
        raise GameValidationError(
            f"Please select the right number of players for a {game_type} game"
        )

    all_ids = team1_ids + team2_ids
    if db.session.query(Player.id).filter(Player.id.in_(all_ids)).count() != len(all_ids):
        raise GameValidationError("Unknown player selected")

    return {
        "game_type": game_type,
        "start_time": start_time,
        "end_time": end_time,
        "team1_score": team1_score,
        "team2_score": team2_score,
        "team1_ids": team1_ids,
        "team2_ids": team2_ids,
    }


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
