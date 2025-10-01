# 🏓 Foosball Tracker

A web application for tracking office foosball games, built with Flask and htmx.

## Features

- ✅ **Player Management**: Add and manage players
- ✅ **Game Recording**: Record games with scores, players, and timestamps
- ✅ **Multiple Game Types**: Support for 1v1, 2v2, and 2v1 matches
- ✅ **Leaderboard**: Comprehensive rankings with win rates and statistics
- ✅ **Cake Counter**: Track cake debts from 10-0 shutouts
- ✅ **Statistics Dashboard**: Interactive charts and detailed analytics
- ✅ **Game Duration Tracking**: Optional start/end time recording
- ✅ **Responsive Design**: Bootstrap-based UI that works on all devices

## Technology Stack

- **Backend**: Flask + SQLAlchemy
- **Frontend**: htmx + Bootstrap 5
- **Charts**: Chart.js
- **Database**: SQLite (easily configurable for other databases)

## Installation & Setup

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
- **Leaderboard**: Player rankings and cake standings
- **Statistics**: Interactive charts and detailed analytics

## The Cake Rule 🎂

When a player wins 10-0 (a shutout), the losing player(s) owe the winner(s) a cake! The application automatically tracks these cake balances, which can be reduced when the debtor gets revenge.

## Database Schema

- **Players**: Store player information
- **Games**: Store game details (scores, date, duration, type)
- **GamePlayers**: Link players to games with team assignments
- **CakeBalances**: Track cake debts between players

## Development

The application uses htmx for dynamic updates without page refreshes. All API endpoints return HTML fragments that are swapped into the page, providing a smooth user experience.

To extend the application, you can:
- Add new statistics and charts
- Implement player profiles
- Add tournament functionality
- Create mobile-specific features
- Add export functionality for data analysis

Enjoy tracking your foosball games! 🏓