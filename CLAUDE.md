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

- **app.py**: Monolithic Flask application containing all models, routes, and business logic
- **templates/**: Jinja2 templates with base layout and page-specific views
- **templates/partials/**: HTML fragments returned by htmx API endpoints
- **static/css/**: Custom CSS styles
- **instance/**: SQLite database storage (auto-created, gitignored)

### Data Models (app.py)

**Player** (app.py:18-25): Player records with name, ELO rating (default 1500), and creation timestamp

**Game** (app.py:28-57): Game records with:
- Scores for both teams
- Game type (1v1, 2v2, 2v1)
- Start time (required) and optional end time for duration tracking
- Computed properties: `duration_minutes`, `is_shutout`

**GamePlayer** (app.py:60-72): Junction table linking players to games with:
- Team assignment (1 or 2)
- Winner status (boolean)
- ELO change for this specific game (nullable integer)

**CakeBalance** (app.py:75-85): Tracks cake debts between players (10-0 shutout rule: losers owe winners a cake)

**LeaderboardHistory** (app.py:87-102): Stores daily snapshots of leaderboard positions for historical tracking with:
- Player ID reference
- Snapshot date (one per day)
- Rank (leaderboard position on that date)
- ELO rating at that point
- Total games played at that point
- Unique constraint on (player_id, snapshot_date)

### Routing Pattern

The application follows a dual-route pattern:

1. **Page Routes** (app.py:88-116): Return full HTML pages
   - `/` → index.html
   - `/players` → players.html
   - `/games` → games.html
   - `/leaderboard` → leaderboard.html
   - `/statistics` → statistics.html
   - `/players/<int:player_id>` → player_detail.html (individual player page)

2. **API Routes** (app.py:119-840): Return HTML fragments for htmx
   - All API routes start with `/api/`
   - Return partial HTML snippets that htmx swaps into the DOM
   - Use HTTP status codes (201 for created, 400 for errors)
   - Most endpoints support pagination via `?page=N&per_page=N` query parameters

### Key Business Logic

**ELO Rating System** (app.py:206-290):
- `calculate_elo_change()` (app.py:206-232): Calculates rating changes using standard ELO formula with K-factor of 32
- `update_elo_ratings()` (app.py:235-271): Updates player ELO ratings after each game and stores the change in GamePlayer records
- `recalculate_all_elo_ratings()` (app.py:273-290): Recalculates all ELO ratings from scratch by replaying games chronologically
- Team ratings are averaged before calculation for 2v2 and 2v1 games
- ELO changes are stored per-player per-game for historical tracking

**update_cake_balance()** (app.py:366-389): Called when a shutout (10-0) occurs. Creates or increments CakeBalance records for each loser-winner pair.

**Leaderboard Calculation** (app.py:409-482): Computes player statistics including:
- Win/loss records and win rate percentage
- Goals for/against and goal difference
- Shutouts given/received
- Current ELO rating
- Sorted by ELO rating (highest first)
- Supports pagination

**Chart Data Generation** (app.py:698-770): Aggregates statistics for Chart.js visualizations:
- Games over time (last 30 days)
- Average game duration by type
- Game type distribution
- Player win rates

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

- Database initialization happens automatically via `db.create_all()` in the main block (app.py:843-845)
- ELO ratings are recalculated on startup to ensure consistency
- Schema changes should use Flask-Migrate migrations (see Database Migrations section)
- All date parsing uses python-dateutil for flexible date format handling
- The app runs with `host="0.0.0.0"` to support Docker networking
- SQLAlchemy track modifications is disabled for performance
- When recording games, ELO ratings are updated immediately and cake balances are updated for shutouts
- If you are returning status messages do this with HTTP status code 200