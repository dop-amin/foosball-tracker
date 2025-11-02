# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Foosball Tracker is a web application for tracking office foosball games, built with Flask and htmx. The application uses a hypermedia-driven architecture where the server returns HTML fragments instead of JSON, enabling dynamic updates without full page refreshes.

## Common Commands

### Running the Application

**Local Development:**
```bash
python app.py
```
The app runs on http://localhost:5000 with debug mode enabled.

**Docker Compose (Recommended):**
```bash
docker-compose up --build
```

### Dependencies

Install dependencies with:
```bash
pip install -r requirements.txt
```

Required packages: Flask, Flask-SQLAlchemy, Flask-Migrate, python-dateutil

### Database Migrations

The project uses Flask-Migrate for database schema management:

```bash
# Create a new migration after model changes
flask db migrate -m "Description of changes"

# Apply migrations
flask db upgrade

# Revert migrations
flask db downgrade
```

**Important**: After any migration that affects player ratings or game history, run the ELO recalculation script to ensure consistency. This script also regenerates historical leaderboard snapshots:
```bash
python recalculate_elo.py
```

This script performs two operations:
1. Recalculates all ELO ratings from scratch by replaying games chronologically
2. Regenerates historical leaderboard snapshots for position tracking over time

## Architecture

### Application Structure

The application follows a modular Flask blueprint architecture:

- **app.py**: Application factory and initialization (uses `create_app()` pattern)
- **config.py**: Configuration settings (database URI, secret key, etc.)
- **models.py**: SQLAlchemy database models (8 models)
- **services/**: Business logic layer
  - `elo_service.py`: ELO rating calculations
  - `leaderboard_service.py`: Leaderboard and historical snapshot management
  - `game_service.py`: Game recording and cake balance logic
  - `statistics_service.py`: Statistics, streaks, and badge calculations
  - `tournament_service.py`: Tournament bracket generation and management
- **blueprints/**: Flask blueprints for route organization
  - `pages.py`: Page routes (return full HTML pages)
  - `players.py`: Player API routes
  - `games.py`: Game API routes
  - `leaderboard.py`: Leaderboard API routes
  - `statistics.py`: Statistics and chart API routes
  - `tournaments.py`: Tournament routes and API
- **templates/**: Jinja2 templates with base layout and page-specific views
- **templates/partials/**: HTML fragments returned by htmx API endpoints
- **static/css/**: Custom CSS styles
- **instance/**: SQLite database storage (auto-created, gitignored)
- **recalculate_elo.py**: Utility script for recalculating ELO and historical data

### Data Models (models.py)

**Player**: Player records with name, ELO rating (default 1500), and creation timestamp

**Game**: Game records with:
- Scores for both teams
- Game type (1v1, 2v2, 2v1)
- Start time (required) and optional end time for duration tracking
- Computed properties: `duration_minutes`, `is_shutout`

**GamePlayer**: Junction table linking players to games with:
- Team assignment (1 or 2)
- Winner status (boolean)
- ELO change for this specific game (nullable integer)

**CakeBalance**: Tracks cake debts between players (10-0 shutout rule: losers owe winners a cake)

**LeaderboardHistory**: Stores daily snapshots of leaderboard positions for historical tracking with:
- Player ID reference
- Snapshot date (one per day)
- Rank (leaderboard position on that date)
- ELO rating at that point
- Total games played at that point
- Unique constraint on (player_id, snapshot_date)

**Tournament**: Tournament records with name, status (setup/active/completed), and timestamps

**TournamentParticipant**: Links players to tournaments with seeding information

**TournamentMatch**: Tournament bracket matches with players, winners, and game links

### Routing Pattern

The application uses Flask blueprints organized by feature:

1. **Page Routes** (blueprints/pages.py): Return full HTML pages
   - `/` → index.html
   - `/players` → players.html
   - `/games` → games.html
   - `/leaderboard` → leaderboard.html
   - `/statistics` → statistics.html
   - `/tournaments` → tournaments.html
   - `/players/<int:player_id>` → player_detail.html
   - `/tournaments/<int:tournament_id>` → tournament_detail.html

2. **API Routes** (blueprints/*/): Return HTML fragments for htmx
   - All API routes start with `/api/`
   - Return partial HTML snippets that htmx swaps into the DOM
   - Use HTTP status codes (201 for created, 400 for errors)
   - Most endpoints support pagination via `?page=N&per_page=N` query parameters

### Key Business Logic

**ELO Rating System** (services/elo_service.py):
- `calculate_elo_change()`: Calculates rating changes using standard ELO formula with K-factor of 32
- `update_elo_ratings()`: Updates player ELO ratings after each game and stores the change in GamePlayer records
- `recalculate_all_elo_ratings()`: Recalculates all ELO ratings from scratch by replaying games chronologically
- Team ratings are averaged before calculation for 2v2 and 2v1 games
- ELO changes are stored per-player per-game for historical tracking

**Leaderboard Management** (services/leaderboard_service.py):
- `create_daily_snapshot()`: Creates daily leaderboard snapshots for position tracking
- `recalculate_historical_snapshots()`: Rebuilds all historical snapshots from game history

**Game Management** (services/game_service.py):
- `update_cake_balance()`: Called when a shutout (10-0) occurs. Creates or increments CakeBalance records

**Statistics & Badges** (services/statistics_service.py):
- `calculate_player_streaks()`: Computes winning streaks for players
- `calculate_badges()`: Awards achievement badges based on player performance

**Tournament System** (services/tournament_service.py):
- `generate_tournament_bracket()`: Creates single-elimination bracket with proper seeding
- `advance_winner()`: Advances tournament winners to next round

## htmx Integration

All API endpoints return HTML fragments, not JSON. htmx makes AJAX requests and swaps responses into the page. Key patterns:

- Forms post to `/api/*` endpoints
- Responses are rendered templates from `templates/partials/`
- Error messages returned as Bootstrap alert HTML with appropriate status codes
- Success responses trigger DOM updates via htmx's swap mechanism
- Pagination uses htmx to load new pages without full refreshes (templates/partials/pagination.html)

## Database

SQLite database auto-created on first run. File location: `instance/foosball.db`

The schema supports:
- Multiple game types (1v1, 2v2, 2v1)
- Team-based gameplay with flexible team sizes
- ELO rating system with per-game change tracking
- Bidirectional cake debt tracking
- Optional game duration tracking

**Migration System**: The project uses Flask-Migrate. Existing migrations in `migrations/versions/`:
- `452ffef4afe1`: Removed `date_played`, made `start_time` required
- `467ce614a99a`: Added `elo_rating` to Player model
- `cfb12dcc8333`: Added `elo_change` to GamePlayer model

## Development Notes

- Database initialization happens automatically via `db.create_all()` in app.py's main block
- ELO ratings are recalculated on startup to ensure consistency
- Schema changes should use Flask-Migrate migrations (see Database Migrations section)
- All date parsing uses python-dateutil for flexible date format handling
- The app runs with `host="0.0.0.0"` to support Docker networking
- SQLAlchemy track modifications is disabled for performance
- When recording games, ELO ratings are updated immediately and cake balances are updated for shutouts
- If you are returning status messages do this with HTTP status code 200
- The application uses an application factory pattern (`create_app()`) for better testability
- Business logic is separated into service modules in the `services/` directory
- Routes are organized by feature using Flask blueprints in the `blueprints/` directory