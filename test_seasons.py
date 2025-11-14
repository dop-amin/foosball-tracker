#!/usr/bin/env python3
"""
Test script to verify season functionality and demonstrate season transitions.
"""

from app import create_app
from models import db, Season, Player, Game, GamePlayer
from services.season_service import get_current_season, get_all_seasons
from datetime import datetime

app = create_app()

def print_separator(title=""):
    print("\n" + "=" * 70)
    if title:
        print(f"  {title}")
        print("=" * 70)


def show_current_season():
    """Display information about the current season."""
    current = get_current_season()
    print(f"\n✓ Current Season: {current.name}")
    print(f"  ID: {current.id}")
    print(f"  Start: {current.start_date.strftime('%Y-%m-%d')}")
    print(f"  End: {current.end_date.strftime('%Y-%m-%d')}")
    print(f"  Is Current: {current.is_current}")
    print(f"  Games in season: {len(current.games)}")
    return current


def show_all_seasons():
    """Display all seasons."""
    seasons = get_all_seasons(order_by_newest=True)
    print(f"\n📅 All Seasons ({len(seasons)} total):")
    for season in seasons:
        marker = "🔹 CURRENT" if season.is_current else "  "
        print(f"{marker} {season.name:12} | Games: {len(season.games):3} | "
              f"{season.start_date.strftime('%Y-%m-%d')} to {season.end_date.strftime('%Y-%m-%d')}")
    return seasons


def show_player_elos():
    """Display current ELO ratings for all players."""
    players = Player.query.all()
    if not players:
        print("\n⚠️  No players found!")
        return

    print(f"\n👥 Player ELO Ratings:")
    for player in sorted(players, key=lambda p: p.elo_rating, reverse=True):
        print(f"  {player.name:20} | ELO: {player.elo_rating}")


def verify_season_data_isolation():
    """Verify that games are properly assigned to seasons."""
    seasons = Season.query.all()
    print(f"\n🔍 Verifying Season Data Isolation:")

    for season in seasons:
        games = Game.query.filter_by(season_id=season.id).all()
        print(f"\n  {season.name}:")
        print(f"    Games: {len(games)}")

        if games:
            # Check if all games have the correct season_id
            correct = all(g.season_id == season.id for g in games)
            print(f"    All games correctly assigned: {'✓' if correct else '✗'}")

            # Show game IDs
            game_ids = [g.id for g in games[:5]]
            if len(games) > 5:
                print(f"    Sample game IDs: {game_ids}... (and {len(games) - 5} more)")
            else:
                print(f"    Game IDs: {game_ids}")


def check_orphaned_games():
    """Check for games without a season_id (should be none)."""
    orphaned = Game.query.filter(Game.season_id == None).all()
    if orphaned:
        print(f"\n⚠️  WARNING: Found {len(orphaned)} games without season_id!")
        for game in orphaned[:5]:
            print(f"     Game ID {game.id}: {game.team1_score}-{game.team2_score}")
    else:
        print(f"\n✓ All games are assigned to a season (no orphaned games)")


if __name__ == "__main__":
    with app.app_context():
        print_separator("SEASON SYSTEM TEST")

        # 1. Show current season
        print_separator("1. Current Season Information")
        current_season = show_current_season()

        # 2. Show all seasons
        print_separator("2. All Seasons")
        all_seasons = show_all_seasons()

        # 3. Show player ELOs
        print_separator("3. Player ELO Ratings")
        show_player_elos()

        # 4. Verify data isolation
        print_separator("4. Season Data Isolation")
        verify_season_data_isolation()

        # 5. Check for orphaned games
        print_separator("5. Orphaned Games Check")
        check_orphaned_games()

        # Summary
        print_separator("SUMMARY")
        print(f"\n✓ Total Seasons: {len(all_seasons)}")
        print(f"✓ Current Season: {current_season.name}")
        print(f"✓ Games in Current Season: {len(current_season.games)}")
        print(f"✓ Total Players: {Player.query.count()}")
        print(f"✓ Total Games: {Game.query.count()}")

        print("\n" + "=" * 70)
        print("  Test Complete!")
        print("=" * 70 + "\n")

        print("\n💡 To test season transition:")
        print("   1. Go to http://localhost:5000/api/season-info")
        print("   2. Create some games and check the leaderboard")
        print("   3. Manually create a new season with Python (see testing guide)")
        print("   4. Verify ELO ratings reset to 1500")
        print("   5. Verify leaderboard shows only new season data\n")
