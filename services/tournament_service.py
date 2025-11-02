"""Tournament bracket generation and management service."""

import math
import random
from models import db, Player, Tournament, TournamentParticipant, TournamentMatch


def generate_tournament_bracket(tournament_id, player_ids):
    """
    Generate a single-elimination tournament bracket.
    Uses power-of-2 bracket structure with byes for odd numbers.
    """
    tournament = Tournament.query.get(tournament_id)
    if not tournament:
        return False

    num_players = len(player_ids)
    if num_players < 2:
        return False

    # Calculate number of rounds needed (log2 of next power of 2)
    num_rounds = math.ceil(math.log2(num_players))
    total_matches_in_first_round = 2 ** (num_rounds - 1)

    # Get players and randomize their order
    players = Player.query.filter(Player.id.in_(player_ids)).all()
    random.shuffle(players)

    # Create participants with seeding (after randomization)
    for idx, player in enumerate(players):
        participant = TournamentParticipant(
            tournament_id=tournament_id,
            player_id=player.id,
            seed=idx + 1
        )
        db.session.add(participant)

    # Create bracket structure from finals backwards
    match_map = {}  # Map of (round, match_number) to match object

    # Create finals (round 1)
    finals = TournamentMatch(
        tournament_id=tournament_id,
        round_number=1,
        match_number=1
    )
    db.session.add(finals)
    db.session.flush()
    match_map[(1, 1)] = finals

    # Create earlier rounds
    for round_num in range(2, num_rounds + 1):
        matches_in_round = 2 ** (round_num - 1)
        for match_num in range(1, matches_in_round + 1):
            match = TournamentMatch(
                tournament_id=tournament_id,
                round_number=round_num,
                match_number=match_num,
                next_match_id=match_map[(round_num - 1, (match_num + 1) // 2)].id
            )
            db.session.add(match)
            db.session.flush()
            match_map[(round_num, match_num)] = match

    # Assign players to first round using proper tournament seeding
    first_round_matches = sorted(
        [m for r, m in match_map.items() if r[0] == num_rounds],
        key=lambda x: x.match_number
    )

    # Calculate number of byes needed (higher seeds get byes)
    bracket_size = 2 ** num_rounds
    num_byes = bracket_size - num_players

    # Standard bracket seeding order for power of 2
    # For 8 players: [1,8, 4,5, 2,7, 3,6]
    def get_seeding_for_round(n):
        if n == 1:
            return [1, 2]
        prev = get_seeding_for_round(n - 1)
        size = 2 ** n
        result = []
        for seed in prev:
            result.append(seed)
            result.append(size + 1 - seed)
        return result

    seeding_order = get_seeding_for_round(num_rounds)

    # Assign players and byes
    # Top seeds (lowest numbers) get byes when needed
    for i, match in enumerate(first_round_matches):
        seed1 = seeding_order[i * 2]
        seed2 = seeding_order[i * 2 + 1]

        # Assign player if seed is within player count, otherwise bye
        player1_id = players[seed1 - 1].id if seed1 <= num_players else None
        player2_id = players[seed2 - 1].id if seed2 <= num_players else None

        match.player1_id = player1_id
        match.player2_id = player2_id

        # Handle byes - if only one player, they automatically advance
        if match.player1_id and not match.player2_id:
            match.winner_id = match.player1_id
            advance_winner(match, auto_advance_byes=True)
        elif match.player2_id and not match.player1_id:
            match.winner_id = match.player2_id
            advance_winner(match, auto_advance_byes=True)

    db.session.commit()
    return True


def advance_winner(match, auto_advance_byes=False):
    """Advance the winner of a match to the next round.

    Args:
        match: The match whose winner should advance
        auto_advance_byes: If True, automatically advance through byes (used during bracket setup)
    """
    if match.winner_id and match.next_match_id:
        next_match = TournamentMatch.query.get(match.next_match_id)
        if next_match:
            # Determine which slot to fill in next match
            parent_matches = TournamentMatch.query.filter_by(
                next_match_id=match.next_match_id
            ).order_by(TournamentMatch.match_number).all()

            if parent_matches[0].id == match.id:
                next_match.player1_id = match.winner_id
            else:
                next_match.player2_id = match.winner_id

            # Only auto-advance through byes during initial bracket setup
            if auto_advance_byes:
                # Get both parent matches feeding into the next match
                parent_matches = TournamentMatch.query.filter_by(
                    next_match_id=next_match.id
                ).all()

                # Check if BOTH parent matches are resolved (have winners or are byes)
                both_parents_resolved = all(
                    parent.winner_id is not None for parent in parent_matches
                )

                # Only auto-advance if both parents are resolved and one slot is still empty
                # (This means it's a true bye, not waiting for a match result)
                if both_parents_resolved:
                    if next_match.player1_id and not next_match.player2_id:
                        next_match.winner_id = next_match.player1_id
                        advance_winner(next_match, auto_advance_byes=True)
                    elif next_match.player2_id and not next_match.player1_id:
                        next_match.winner_id = next_match.player2_id
                        advance_winner(next_match, auto_advance_byes=True)
