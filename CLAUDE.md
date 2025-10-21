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

Required packages: Flask, Flask-SQLAlchemy, python-dateutil

## Architecture

### Application Structure

- **app.py**: Monolithic Flask application containing all models, routes, and business logic
- **templates/**: Jinja2 templates with base layout and page-specific views
- **templates/partials/**: HTML fragments returned by htmx API endpoints
- **static/css/**: Custom CSS styles
- **instance/**: SQLite database storage (auto-created, gitignored)

### Data Models (app.py)

**Player** (lines 15-21): Player records with name and creation timestamp

**Game** (lines 24-54): Game records with:
- Scores for both teams
- Game type (1v1, 2v2, 2v1)
- Optional start/end times for duration tracking
- Computed properties: `duration_minutes`, `is_shutout`

**GamePlayer** (lines 57-68): Junction table linking players to games with team assignment and winner status

**CakeBalance** (lines 71-81): Tracks cake debts between players (10-0 shutout rule: losers owe winners a cake)

### Routing Pattern

The application follows a dual-route pattern:

1. **Page Routes** (lines 84-106): Return full HTML pages
   - `/` → index.html
   - `/players` → players.html
   - `/games` → games.html
   - `/leaderboard` → leaderboard.html
   - `/statistics` → statistics.html

2. **API Routes** (lines 109-547): Return HTML fragments for htmx
   - All API routes start with `/api/`
   - Return partial HTML snippets that htmx swaps into the DOM
   - Use HTTP status codes (201 for created, 400 for errors)

### Key Business Logic

**update_cake_balance()** (lines 243-266): Called when a shutout (10-0) occurs. Creates or increments CakeBalance records for each loser-winner pair.

**Leaderboard Calculation** (lines 276-333): Computes player statistics including:
- Win/loss records
- Goals for/against and goal difference
- Shutouts given/received
- Sorted by win rate, then goal difference

**Chart Data Generation** (lines 406-478): Aggregates statistics for Chart.js visualizations:
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

## Database

SQLite database auto-created on first run (app.py:551-552). File location: `instance/foosball.db`

The schema supports:
- Multiple game types (1v1, 2v2, 2v1)
- Team-based gameplay with flexible team sizes
- Bidirectional cake debt tracking
- Optional game duration tracking

## Development Notes

- Database initialization happens automatically via `db.create_all()` in the main block
- No migrations system in place - schema changes require manual database updates
- All date parsing uses python-dateutil for flexibility
- The app runs with `host="0.0.0.0"` to support Docker networking
- SQLAlchemy track modifications is disabled for performance
