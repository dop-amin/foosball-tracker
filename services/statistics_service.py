"""Statistics calculation service including streaks and badges."""

from datetime import datetime, timedelta, timezone
from sqlalchemy import func, or_
from models import db, GamePlayer, Game, CakeBalance


def calculate_player_streaks(player_id):
    """Calculate current and best winning streaks for a player."""
    games = (
        GamePlayer.query.filter_by(player_id=player_id)
        .join(Game)
        .order_by(Game.start_time.asc())
        .all()
    )

    if not games:
        return 0, 0

    current_streak = 0
    best_streak = 0
    temp_streak = 0

    for gp in games:
        if gp.is_winner:
            temp_streak += 1
            best_streak = max(best_streak, temp_streak)
        else:
            temp_streak = 0

    # Check if currently on a streak (last game was a win)
    if games and games[-1].is_winner:
        current_streak = temp_streak

    return current_streak, best_streak


def precompute_badge_data(player_ids):
    """Pre-compute all data needed for badge calculations in bulk.

    This reduces N queries to 3-4 queries for all players.

    Args:
        player_ids: List of player IDs to compute data for

    Returns:
        Dictionary with keys 'streaks', 'cake_totals', 'recent_games', 'night_owl', 'early_bird', 'cat_data', 'addict'
    """
    cached_data = {
        'streaks': {},
        'cake_totals': {},
        'recent_games': {},
        'night_owl': set(),
        'early_bird': set(),
        'cat_data': {},
        'addict': set()
    }

    # Bulk compute streaks for all players
    for player_id in player_ids:
        cached_data['streaks'][player_id] = calculate_player_streaks(player_id)

    # Bulk query cake totals
    cake_results = db.session.query(
        CakeBalance.creditor_id,
        func.sum(CakeBalance.balance).label('total')
    ).filter(
        CakeBalance.creditor_id.in_(player_ids)
    ).group_by(CakeBalance.creditor_id).all()

    for creditor_id, total in cake_results:
        cached_data['cake_totals'][creditor_id] = int(total or 0)

    # Ensure all players have an entry (even if 0)
    for player_id in player_ids:
        if player_id not in cached_data['cake_totals']:
            cached_data['cake_totals'][player_id] = 0

    # Bulk query recent games (last 7 days)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_results = db.session.query(
        GamePlayer.player_id,
        func.count(GamePlayer.id).label('game_count')
    ).join(
        Game, GamePlayer.game_id == Game.id
    ).filter(
        GamePlayer.player_id.in_(player_ids),
        Game.start_time >= seven_days_ago
    ).group_by(GamePlayer.player_id).all()

    for player_id, game_count in recent_results:
        cached_data['recent_games'][player_id] = int(game_count or 0)

    # Ensure all players have an entry (even if 0)
    for player_id in player_ids:
        if player_id not in cached_data['recent_games']:
            cached_data['recent_games'][player_id] = 0

    # Compute Night Owl badge (played between 8pm and 6am)
    night_owl_games = db.session.query(GamePlayer.player_id).join(
        Game, GamePlayer.game_id == Game.id
    ).filter(
        GamePlayer.player_id.in_(player_ids),
        or_(
            func.cast(func.strftime('%H', Game.start_time), db.Integer) >= 20,
            func.cast(func.strftime('%H', Game.start_time), db.Integer) < 6
        )
    ).distinct().all()

    cached_data['night_owl'] = {player_id for (player_id,) in night_owl_games}

    # Compute Early Bird badge (played between 6am and 9am)
    early_bird_games = db.session.query(GamePlayer.player_id).join(
        Game, GamePlayer.game_id == Game.id
    ).filter(
        GamePlayer.player_id.in_(player_ids),
        func.cast(func.strftime('%H', Game.start_time), db.Integer) >= 6,
        func.cast(func.strftime('%H', Game.start_time), db.Integer) < 9
    ).distinct().all()

    cached_data['early_bird'] = {player_id for (player_id,) in early_bird_games}

    # Compute Cat badge (lost against majority of players)
    # For each player, find unique opponents and count losses against unique opponents
    for player_id in player_ids:
        # Get all games for this player
        player_games = db.session.query(
            GamePlayer.is_winner,
            GamePlayer.team,
            Game.id.label('game_id')
        ).join(
            Game, GamePlayer.game_id == Game.id
        ).filter(
            GamePlayer.player_id == player_id
        ).all()

        if not player_games:
            continue

        # Get all opponents (players on the opposite team in each game)
        game_ids = [g.game_id for g in player_games]
        opponents_data = db.session.query(
            GamePlayer.player_id,
            GamePlayer.is_winner,
            GamePlayer.team,
            GamePlayer.game_id
        ).filter(
            GamePlayer.game_id.in_(game_ids),
            GamePlayer.player_id != player_id
        ).all()

        # Build opponent map per game
        opponents_by_game = {}
        for opp_data in opponents_data:
            if opp_data.game_id not in opponents_by_game:
                opponents_by_game[opp_data.game_id] = []
            opponents_by_game[opp_data.game_id].append(opp_data)

        unique_opponents = set()
        opponents_lost_to = set()

        for game in player_games:
            game_opponents = opponents_by_game.get(game.game_id, [])
            for opp in game_opponents:
                # Opponent is on different team
                if opp.team != game.team:
                    unique_opponents.add(opp.player_id)
                    # If this player lost this game, they lost to this opponent
                    if not game.is_winner:
                        opponents_lost_to.add(opp.player_id)

        # Cat badge: lost to more than 50% of unique opponents
        if len(unique_opponents) > 0:
            loss_ratio = len(opponents_lost_to) / len(unique_opponents)
            cached_data['cat_data'][player_id] = {
                'unique_opponents': len(unique_opponents),
                'opponents_lost_to': len(opponents_lost_to),
                'loss_ratio': loss_ratio
            }

    # Compute Addict badge (avg 3+ games per day for a week = 21+ games in any 7-day period)
    for player_id in player_ids:
        # Get all games sorted by start time
        games = db.session.query(
            Game.start_time
        ).join(
            GamePlayer, GamePlayer.game_id == Game.id
        ).filter(
            GamePlayer.player_id == player_id
        ).order_by(Game.start_time.asc()).all()

        if len(games) < 21:
            continue

        # Check if there's any 7-day window with 21+ games
        for i in range(len(games)):
            window_start = games[i].start_time
            window_end = window_start + timedelta(days=7)

            # Count games in this window
            games_in_window = sum(1 for g in games[i:] if g.start_time < window_end)

            if games_in_window >= 21:
                cached_data['addict'].add(player_id)
                break

    return cached_data


def calculate_badges(player_stats, all_players_stats, cached_data=None):
    """Calculate achievement badges for a player based on their stats.

    Args:
        player_stats: Dictionary containing stats for the current player
        all_players_stats: List of all player stats dictionaries for comparisons
        cached_data: Optional dictionary with pre-computed global data to avoid repeated queries:
            - 'streaks': dict mapping player_id to (current_streak, best_streak)
            - 'cake_totals': dict mapping player_id to total_cakes
            - 'recent_games': dict mapping player_id to recent game count
    """
    badges = []
    player = player_stats["player"]

    # Use cached data if provided, otherwise compute on-demand
    if cached_data is None:
        cached_data = {}

    # Winning Streaks
    if 'streaks' in cached_data:
        current_streak, best_streak = cached_data['streaks'].get(player.id, (0, 0))
    else:
        current_streak, best_streak = calculate_player_streaks(player.id)

    if current_streak >= 10:
        badges.append({"emoji": "💥", "label": "Unstoppable", "color": "danger", "tooltip": f"Unstoppable: Currently on a {current_streak} game winning streak!"})
    elif current_streak >= 5:
        badges.append({"emoji": "🔥", "label": "On Fire", "color": "danger", "tooltip": f"On Fire: Currently on a {current_streak} game winning streak!"})
    elif current_streak >= 3:
        badges.append({"emoji": "⚡", "label": "Hot Streak", "color": "warning", "tooltip": f"Hot Streak: Currently on a {current_streak} game winning streak!"})

    # Performance Badges
    if player_stats["total_games"] >= 10 and player_stats["win_rate"] == 100:
        badges.append({"emoji": "💯", "label": "Perfect", "color": "success", "tooltip": f"Undefeated with {player_stats['total_games']} games played!"})
    elif player_stats["total_games"] >= 20 and player_stats["win_rate"] >= 60:
        badges.append({"emoji": "⭐", "label": "Dominator", "color": "primary", "tooltip": f"{player_stats['win_rate']:.1f}% win rate with {player_stats['total_games']} games"})

    if player_stats["elo_rating"] >= 1700:
        badges.append({"emoji": "🏆", "label": "ELO Elite", "color": "warning", "tooltip": f"ELO rating of {player_stats['elo_rating']} (1700+ required)"})

    # Goals per game (Sharpshooter)
    if player_stats["total_games"] >= 20:
        goals_per_game = player_stats["goals_for"] / player_stats["total_games"]
        # Check if this is the highest goals per game among qualified players
        qualified_players = [p for p in all_players_stats if p["total_games"] >= 20]
        if qualified_players:
            max_goals_per_game = max(
                p["goals_for"] / p["total_games"] for p in qualified_players
            )
            if goals_per_game == max_goals_per_game and goals_per_game > 0:
                badges.append({"emoji": "🎯", "label": "Sharpshooter", "color": "info", "tooltip": f"Highest goals per game average: {goals_per_game:.1f}"})

    # Shutout Achievements
    if player_stats["shutouts_given"] >= 5:
        badges.append({"emoji": "🛡️", "label": "Shutout Master", "color": "secondary", "tooltip": f"{player_stats['shutouts_given']} shutout victories (10-0)"})

    # Cake King (most cakes owed to them)
    if 'cake_totals' in cached_data:
        total_cakes = cached_data['cake_totals'].get(player.id, 0)
        all_cake_totals = list(cached_data['cake_totals'].values())
    else:
        cake_query = (
            db.session.query(db.func.sum(CakeBalance.balance))
            .filter_by(creditor_id=player.id)
            .scalar()
        )
        total_cakes = cake_query or 0
        # Fallback: query all cake totals individually (not optimal but maintains semantics)
        all_cake_totals = []
        for p_stat in all_players_stats:
            p_cakes = (
                db.session.query(db.func.sum(CakeBalance.balance))
                .filter_by(creditor_id=p_stat["player"].id)
                .scalar() or 0
            )
            all_cake_totals.append(p_cakes)

    if total_cakes > 0 and all_cake_totals and total_cakes == max(all_cake_totals):
        badges.append({"emoji": "🎂", "label": "Cake King", "color": "light", "tooltip": f"Most cakes owed by opponents: {total_cakes} cake{'s' if total_cakes != 1 else ''}"})

    # Survivor (most shutouts received but still positive win rate)
    if (
        player_stats["shutouts_received"] >= 3
        and player_stats["win_rate"] > 50
        and player_stats["total_games"] >= 10
    ):
        qualified_survivors = [
            p
            for p in all_players_stats
            if p["shutouts_received"] >= 3
            and p["win_rate"] > 50
            and p["total_games"] >= 10
        ]
        if qualified_survivors:
            max_shutouts_received = max(p["shutouts_received"] for p in qualified_survivors)
            if player_stats["shutouts_received"] == max_shutouts_received:
                badges.append({"emoji": "💪", "label": "Survivor", "color": "success", "tooltip": f"Survived {player_stats['shutouts_received']} shutouts but still winning ({player_stats['win_rate']:.1f}% win rate)"})

    # Activity Badges
    if player_stats["total_games"] >= 50:
        badges.append({"emoji": "🎖️", "label": "Veteran", "color": "secondary", "tooltip": f"{player_stats['total_games']} games played (50+ required)"})

    # Marathon (most games in last 7 days, min 5)
    if 'recent_games' in cached_data:
        recent_games = cached_data['recent_games'].get(player.id, 0)
        all_recent_games = list(cached_data['recent_games'].values())
    else:
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        recent_games = (
            GamePlayer.query.filter_by(player_id=player.id)
            .join(Game)
            .filter(Game.start_time >= seven_days_ago)
            .count()
        )
        # Fallback: query all recent games individually (not optimal but maintains semantics)
        all_recent_games = []
        for p_stat in all_players_stats:
            p_recent = (
                GamePlayer.query.filter_by(player_id=p_stat["player"].id)
                .join(Game)
                .filter(Game.start_time >= seven_days_ago)
                .count()
            )
            all_recent_games.append(p_recent)

    if recent_games >= 5 and all_recent_games and recent_games == max(all_recent_games):
        badges.append({"emoji": "📈", "label": "Marathon", "color": "info", "tooltip": f"Most active player: {recent_games} games in the last 7 days"})

    # Night Owl badge (played between 8pm and 6am)
    if cached_data and player.id in cached_data.get('night_owl', set()):
        badges.append({"emoji": "🦉", "label": "Night Owl", "color": "dark", "tooltip": "Played a game between 8pm and 6am"})

    # Early Bird badge (played between 6am and 9am)
    if cached_data and player.id in cached_data.get('early_bird', set()):
        badges.append({"emoji": "🐦", "label": "Early Bird", "color": "warning", "tooltip": "Played a game between 6am and 9am"})

    # Cat badge (lost against majority of players)
    if cached_data and player.id in cached_data.get('cat_data', {}):
        cat_info = cached_data['cat_data'][player.id]
        if cat_info['loss_ratio'] > 0.5 and cat_info['unique_opponents'] >= 3:
            badges.append({"emoji": "🐱", "label": "Cat", "color": "secondary", "tooltip": f"Has many lives: Lost to {cat_info['opponents_lost_to']}/{cat_info['unique_opponents']} opponents"})

    # Addict badge (3+ games per day for a week)
    if cached_data and player.id in cached_data.get('addict', set()):
        badges.append({"emoji": "💉", "label": "Addict", "color": "danger", "tooltip": "Played 21+ games in a 7-day period (avg 3+ per day)"})

    return badges
