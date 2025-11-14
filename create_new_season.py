#!/usr/bin/env python3
"""
Script to manually create a new season and transition to it.
This is useful for testing season transitions.
"""

from app import create_app
from models import db, Season, Player
from services.season_service import create_season, get_quarter_info, reset_elo_ratings
from datetime import datetime

app = create_app()


def create_next_season(force=False):
    """Create the next season after the current one."""
    with app.app_context():
        # Get current season
        current = Season.query.filter_by(is_current=True).first()

        if not current:
            print("❌ No current season found!")
            return

        print(f"Current season: {current.name}")
        print(f"  Start: {current.start_date}")
        print(f"  End: {current.end_date}")

        # Calculate next season
        if current.name.startswith("Q4"):
            # Q4 -> Q1 of next year
            next_quarter = 1
            next_year = int(current.name.split()[1]) + 1
        else:
            # Q1-Q3 -> next quarter same year
            current_quarter = int(current.name[1])
            next_quarter = current_quarter + 1
            next_year = int(current.name.split()[1])

        next_season_name = f"Q{next_quarter} {next_year}"

        # Check if next season already exists
        existing = Season.query.filter_by(name=next_season_name).first()
        if existing:
            print(f"\n⚠️  Season {next_season_name} already exists!")
            if not force:
                print("Use --force to make it current anyway")
                return
            else:
                print("Making it current...")
                # Mark old season as not current
                current.is_current = False
                # Mark existing season as current
                existing.is_current = True
                db.session.commit()

                # Reset ELO ratings
                reset_elo_ratings()

                print(f"\n✓ Switched to existing season: {next_season_name}")
                print(f"✓ All player ELO ratings reset to 1500")
                return

        print(f"\n📅 Creating new season: {next_season_name}")

        # Create the new season
        new_season = create_season(next_year, next_quarter)

        # Mark old season as not current
        current.is_current = False

        # Mark new season as current
        new_season.is_current = True

        db.session.commit()

        print(f"✓ New season created: {new_season.name}")
        print(f"  Start: {new_season.start_date}")
        print(f"  End: {new_season.end_date}")

        # Reset ELO ratings
        print(f"\n🔄 Resetting ELO ratings...")
        reset_elo_ratings()

        # Show updated player ratings
        players = Player.query.all()
        print(f"✓ Reset {len(players)} players to ELO 1500")

        print(f"\n✓ Season transition complete!")
        print(f"  Old season: {current.name} (marked as not current)")
        print(f"  New season: {new_season.name} (marked as current)")

        print(f"\n💡 Tips:")
        print(f"  - New games will be assigned to {new_season.name}")
        print(f"  - Leaderboard will show only {new_season.name} data")
        print(f"  - History graph will be empty until games are played")
        print(f"  - You can view old season data at: /api/season/{current.id}/leaderboard")


if __name__ == "__main__":
    import sys

    force = "--force" in sys.argv

    print("=" * 70)
    print("  CREATE NEW SEASON")
    print("=" * 70)

    create_next_season(force=force)

    print("\n" + "=" * 70)
