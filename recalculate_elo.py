#!/usr/bin/env python3
"""
Script to recalculate ELO ratings for all players from historical games.
Run this once after migrating to the ELO system.
"""

from app import app, recalculate_all_elo_ratings

if __name__ == "__main__":
    with app.app_context():
        print("Recalculating ELO ratings for all players...")
        recalculate_all_elo_ratings()
        print("ELO ratings recalculated successfully!")
