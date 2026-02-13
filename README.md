# ⚽ Foosball Tracker

A web application for tracking office foosball games, built with Flask and htmx.

## Features

- ✅ **Player Management**: Add and manage players with detailed profiles
- ✅ **Game Recording**: Record games with scores, players, and timestamps
- ✅ **Multiple Game Types**: Support for 1v1, 2v2, and 2v1 matches
- ✅ **ELO Rating System**: Dynamic player rankings using ELO algorithm with historical tracking
- ✅ **Leaderboard**: Comprehensive rankings with ELO ratings, win rates, and statistics
- ✅ **Historical Tracking**: Daily leaderboard snapshots to track player progression over time
- ✅ **Tournament System**: Create and manage single-elimination tournaments with bracket visualization
- ✅ **Cake Counter**: Track cake debts from 10-0 shutouts
- ✅ **Statistics Dashboard**: Interactive charts and detailed analytics
- ✅ **Badges & Achievements**: Award players with badges based on performance
- ✅ **Streak Tracking**: Monitor current and best winning streaks
- ✅ **Player Profiles**: Detailed player pages with game history and personal statistics
- ✅ **Game Duration Tracking**: Optional start/end time recording
- ✅ **Responsive Design**: Bootstrap-based UI that works on all devices

## Technology Stack

- **Backend**: Flask + SQLAlchemy
- **Frontend**: htmx + Bootstrap 5
- **Charts**: Chart.js
- **Database**: SQLite (easily configurable for other databases)

## Installation & Setup

### Option 1: Docker Compose (Recommended)

1. **Run with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

2. **Access the Application**:
   Open your browser and go to `http://localhost:5000`

The database will persist in the `instance/` directory, so your data is preserved across container restarts.

### Option 2: Local Python Installation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**:
   ```bash
   python app.py
   ```

3. **Access the Application**:
   Open your browser and go to `http://localhost:5000`

## Usage

### Adding Players
1. Go to the "Players" page
2. Enter a player name and click "Add Player"
3. View all players and their cake balances

### Recording Games
1. Go to the "Games" page
2. Select the game type (1v1, 2v2, or 2v1)
3. Choose players for each team
4. Enter the final scores
5. Optionally add start/end times for duration tracking
6. Click "Record Game"

### Viewing Statistics
- **Home**: Quick stats and recent games
- **Leaderboard**: Player rankings with ELO ratings and cake standings
- **Statistics**: Interactive charts and detailed analytics
- **Player Profiles**: Click any player to see detailed stats, game history, and badges
- **Tournaments**: Create and manage tournament brackets

## The Cake Rule 🎂

When a player wins 10-0 (a shutout), the losing player(s) owe the winner(s) a cake! The application automatically tracks these cake balances, which can be reduced when the debtor gets revenge.

## Database Schema

The application uses SQLite with the following models:

- **Player**: Player information including name, ELO rating (default 1500), and creation timestamp
- **Game**: Game records with scores for both teams, game type (1v1, 2v2, 2v1), start time, optional end time, and computed properties for duration and shutout detection
- **GamePlayer**: Junction table linking players to games with team assignment (1 or 2), winner status, and ELO change for that specific game
- **CakeBalance**: Tracks cake debts between players from 10-0 shutouts
- **LeaderboardHistory**: Daily snapshots of leaderboard positions including rank, ELO rating, and total games played for historical tracking
- **Tournament**: Tournament records with name, status (setup/active/completed), and timestamps
- **TournamentParticipant**: Links players to tournaments with seeding information
- **TournamentMatch**: Tournament bracket matches with players, winners, game links, and bracket structure

### Key Features:
- **ELO Rating System**: Each player has a rating that changes based on game outcomes
- **Historical Tracking**: Daily leaderboard snapshots allow tracking player progression over time
- **Per-Game ELO Changes**: The `elo_change` field in GamePlayer records the rating change for each player in each game
- **Tournament Brackets**: Single-elimination tournaments with proper seeding and match progression

## Architecture

The application uses a modular Flask blueprint architecture with hypermedia-driven design:

### Application Structure:
- **services/**: Business logic layer with dedicated services for ELO calculations, game management, statistics, tournaments, and leaderboard tracking
- **blueprints/**: Flask blueprints organized by feature (pages, players, games, leaderboard, statistics, tournaments)
- **templates/**: Full page templates and HTML fragments for htmx responses
- **models.py**: SQLAlchemy database models (8 models)

### htmx Integration:
All API endpoints (prefixed with `/api/`) return HTML fragments instead of JSON. htmx makes AJAX requests and swaps responses directly into the DOM, providing dynamic updates without full page refreshes or complex JavaScript.

### Database Migrations:
The project uses Flask-Migrate for schema management. After model changes:
```bash
flask db migrate -m "Description of changes"
flask db upgrade
```

After migrations affecting ratings or game history, recalculate ELO ratings:
```bash
python recalculate_elo.py
```

This script recalculates all ELO ratings from scratch and regenerates historical leaderboard snapshots.

## Extending the Application

Potential enhancements:
- Add new statistics and charts
- Implement data export functionality (CSV, JSON)
- Add player vs player head-to-head statistics
- Create tournament scheduling and notifications
- Add mobile-specific optimizations
- Implement team-based tournaments

Enjoy tracking your foosball games! ⚽

---

*Built with Claude Code*