#!/usr/bin/env python3
"""
Script to recalculate ELO ratings and populate historical leaderboard snapshots.
Run this after any migration that affects player ratings or game history.

This script performs two operations:
1. Recalculates all ELO ratings from scratch by replaying games chronologically
2. Populates historical leaderboard snapshots (daily position tracking)
"""

from app import create_app
from models import LeaderboardHistory
from services.elo_service import recalculate_all_elo_ratings
from services.leaderboard_service import recalculate_historical_snapshots

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        print("=" * 60)
        print("RECALCULATING ELO RATINGS AND HISTORICAL SNAPSHOTS")
        print("=" * 60)

        # Step 1: Recalculate ELO ratings
        print("\n[1/2] Recalculating ELO ratings for all players...")
        print("      This replays all games in chronological order...")
        try:
            recalculate_all_elo_ratings()
            print("      ✓ ELO ratings recalculated successfully!")
        except Exception as e:
            print(f"      ✗ Error recalculating ELO ratings: {e}")
            import traceback
            traceback.print_exc()
            exit(1)

        # Step 2: Populate historical leaderboard snapshots
        print("\n[2/2] Populating historical leaderboard snapshots...")
        print("      This creates daily position snapshots from game history...")
        try:
            recalculate_historical_snapshots()
            snapshot_count = LeaderboardHistory.query.count()
            print(f"      ✓ Successfully created {snapshot_count} historical snapshots!")
        except Exception as e:
            print(f"      ✗ Error populating historical data: {e}")
            import traceback
            traceback.print_exc()
            exit(1)

        print("\n" + "=" * 60)
        print("ALL DONE! ✓")
        print("=" * 60)
