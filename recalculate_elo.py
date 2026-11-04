#!/usr/bin/env python3
"""
Script to recalculate ELO ratings and populate historical leaderboard snapshots.
Run this after any migration that affects player ratings or game history.

Every season is replayed separately (each starting at 1500), rebuilding:
1. Per-game ELO changes and the current season's player ratings
2. Cake balances
3. Historical leaderboard snapshots (daily position tracking)
"""

from app import create_app
from models import LeaderboardHistory
from services.recalculation_service import recalculate_all_derived_data
from services.season_service import get_current_season

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("=" * 60)
        print("RECALCULATING ELO RATINGS, CAKE BALANCES AND SNAPSHOTS")
        print("=" * 60)
        print("\nReplaying all games season by season...")
        try:
            # Ensure the current season exists
            get_current_season()
            recalculate_all_derived_data()
            snapshot_count = LeaderboardHistory.query.count()
            print(f"      ✓ Recalculated successfully ({snapshot_count} historical snapshots)")
        except Exception as e:
            print(f"      ✗ Error recalculating derived data: {e}")
            import traceback
            traceback.print_exc()
            exit(1)

        print("\n" + "=" * 60)
        print("ALL DONE! ✓")
        print("=" * 60)
