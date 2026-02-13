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

    # Calculate average team ratings
    team1_avg_rating = sum(p.elo_rating for p in team1_players) / len(team1_players)
    team2_avg_rating = sum(p.elo_rating for p in team2_players) / len(team2_players)

    # Calculate ELO changes
    team1_change, team2_change = calculate_elo_change(
        team1_avg_rating, team2_avg_rating, game.team1_score, game.team2_score
    )

    # Update player ratings and store ELO changes
    for i, player in enumerate(team1_players):
        player.elo_rating += team1_change
        team1_game_players[i].elo_change = team1_change

    for i, player in enumerate(team2_players):
        player.elo_rating += team2_change
        team2_game_players[i].elo_change = team2_change


def recalculate_all_elo_ratings(season_id=None):
    """
    Recalculate ELO ratings for all players from scratch by replaying games.

    Args:
        season_id: Optional season ID to filter games. If provided, only games
                   in that season are processed. If None, all games are processed
                   for all-time view.

    This is useful for initializing ELO ratings or fixing inconsistencies.
    """
    # Reset all player ratings to 1500
    players = Player.query.all()
    for player in players:
        player.elo_rating = 1500

    # Get games in chronological order, optionally filtered by season
    query = Game.query.order_by(Game.start_time)
    if season_id is not None:
        query = query.filter_by(season_id=season_id)

    games = query.all()

    # Replay each game to update ELO ratings
    for game in games:
        update_elo_ratings(game)

    db.session.commit()
