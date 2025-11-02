"""Statistics calculation service including streaks and badges."""

from datetime import datetime, timedelta, timezone
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


def calculate_badges(player_stats, all_players_stats):
    """Calculate achievement badges for a player based on their stats."""
    badges = []
    player = player_stats["player"]

    # Winning Streaks
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
    cake_query = (
        db.session.query(db.func.sum(CakeBalance.balance))
        .filter_by(creditor_id=player.id)
        .scalar()
    )
    total_cakes = cake_query or 0
    if total_cakes > 0:
        # Check if this is the most cakes
        all_cake_totals = []
        for p_stat in all_players_stats:
            p_cakes = (
                db.session.query(db.func.sum(CakeBalance.balance))
                .filter_by(creditor_id=p_stat["player"].id)
                .scalar() or 0
            )
            all_cake_totals.append(p_cakes)

        if all_cake_totals and total_cakes == max(all_cake_totals):
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
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_games = (
        GamePlayer.query.filter_by(player_id=player.id)
        .join(Game)
        .filter(Game.start_time >= seven_days_ago)
        .count()
    )

    if recent_games >= 5:
        # Check if this is the most recent games
        all_recent_games = []
        for p_stat in all_players_stats:
            p_recent = (
                GamePlayer.query.filter_by(player_id=p_stat["player"].id)
                .join(Game)
                .filter(Game.start_time >= seven_days_ago)
                .count()
            )
            all_recent_games.append(p_recent)

        if all_recent_games and recent_games == max(all_recent_games):
            badges.append({"emoji": "📈", "label": "Marathon", "color": "info", "tooltip": f"Most active player: {recent_games} games in the last 7 days"})

    return badges
