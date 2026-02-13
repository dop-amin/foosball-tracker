"""ELO rating calculation and management service."""

from models import db, Player, Game, GamePlayer


def calculate_elo_change(
    team1_rating, team2_rating, team1_score, team2_score, k_factor=32
):
    """
    Calculate ELO rating changes for both teams.

    Args:
        team1_rating: Average ELO rating of team 1
        team2_rating: Average ELO rating of team 2
        team1_score: Score of team 1
        team2_score: Score of team 2
        k_factor: K-factor for ELO calculation (default 32)

    Returns:
        Tuple of (team1_change, team2_change)
    """
    # Calculate expected scores
    expected_team1 = 1 / (1 + 10 ** ((team2_rating - team1_rating) / 400))
    expected_team2 = 1 / (1 + 10 ** ((team1_rating - team2_rating) / 400))

    # Actual scores (1 for win, 0 for loss)
    actual_team1 = 1 if team1_score > team2_score else 0
    actual_team2 = 1 if team2_score > team1_score else 0

    # Calculate rating changes
    team1_change = k_factor * (actual_team1 - expected_team1)
    team2_change = k_factor * (actual_team2 - expected_team2)

    return round(team1_change), round(team2_change)


def update_elo_ratings(game):
    """
    Update ELO ratings for all players in a game and store ELO changes.
    Updates both global ELO and game-type-specific ELO ratings.
    """
    # Get team players and their GamePlayer records
    team1_players = []
    team2_players = []
    team1_game_players = []
    team2_game_players = []

    for gp in game.players:
        player = Player.query.get(gp.player_id)
        if gp.team == 1:
            team1_players.append(player)
            team1_game_players.append(gp)
        else:
            team2_players.append(player)
            team2_game_players.append(gp)

    # Get the appropriate ELO field name for this game type
    game_type_elo_field = f"elo_{game.game_type}"

    # Calculate average team ratings for global ELO
    team1_avg_rating_global = sum(p.elo_rating for p in team1_players) / len(team1_players)
    team2_avg_rating_global = sum(p.elo_rating for p in team2_players) / len(team2_players)

    # Calculate average team ratings for game-type-specific ELO
    team1_avg_rating_specific = sum(getattr(p, game_type_elo_field) for p in team1_players) / len(team1_players)
    team2_avg_rating_specific = sum(getattr(p, game_type_elo_field) for p in team2_players) / len(team2_players)

    # Calculate ELO changes for global rating
    team1_change_global, team2_change_global = calculate_elo_change(
        team1_avg_rating_global, team2_avg_rating_global, game.team1_score, game.team2_score
    )

    # Calculate ELO changes for game-type-specific rating
    team1_change_specific, team2_change_specific = calculate_elo_change(
        team1_avg_rating_specific, team2_avg_rating_specific, game.team1_score, game.team2_score
    )

    # Update player ratings (both global and game-type-specific) and store ELO changes
    for i, player in enumerate(team1_players):
        player.elo_rating += team1_change_global
        current_specific = getattr(player, game_type_elo_field)
        setattr(player, game_type_elo_field, current_specific + team1_change_specific)
        team1_game_players[i].elo_change = team1_change_global

    for i, player in enumerate(team2_players):
        player.elo_rating += team2_change_global
        current_specific = getattr(player, game_type_elo_field)
        setattr(player, game_type_elo_field, current_specific + team2_change_specific)
        team2_game_players[i].elo_change = team2_change_global


def recalculate_all_elo_ratings():
    """
    Recalculate ELO ratings for all players from scratch by replaying all games.
    This is useful for initializing ELO ratings or fixing inconsistencies.
    Updates both global and game-type-specific ELO ratings.
    """
    # Reset all player ratings to 1500 (global and game-type-specific)
    players = Player.query.all()
    for player in players:
        player.elo_rating = 1500
        player.elo_1v1 = 1500
        player.elo_2v2 = 1500
        player.elo_2v1 = 1500

    # Get all games in chronological order
    games = Game.query.order_by(Game.start_time).all()

    # Replay each game to update ELO ratings
    for game in games:
        update_elo_ratings(game)

    db.session.commit()
