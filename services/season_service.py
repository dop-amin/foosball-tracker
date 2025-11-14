from datetime import datetime, timedelta
from models import db, Season, Player


def get_quarter_info(date):
    """Get quarter number and year for a given date."""
    quarter = (date.month - 1) // 3 + 1
    year = date.year
    return quarter, year


def get_quarter_start_end(year, quarter):
    """Get start and end dates for a given quarter."""
    start_month = (quarter - 1) * 3 + 1
    start_date = datetime(year, start_month, 1, 0, 0, 0)

    # Calculate end date (last day of the quarter)
    if quarter == 4:
        end_date = datetime(year + 1, 1, 1, 0, 0, 0) - timedelta(seconds=1)
    else:
        end_month = start_month + 3
        end_date = datetime(year, end_month, 1, 0, 0, 0) - timedelta(seconds=1)

    return start_date, end_date


def create_season(year, quarter):
    """Create a new season for the given year and quarter."""
    season_name = f"Q{quarter} {year}"

    # Check if season already exists
    existing = Season.query.filter_by(name=season_name).first()
    if existing:
        return existing

    start_date, end_date = get_quarter_start_end(year, quarter)

    season = Season(
        name=season_name,
        start_date=start_date,
        end_date=end_date,
        is_current=False
    )

    db.session.add(season)
    db.session.commit()

    return season


def get_current_season():
    """Get or create the current season based on today's date."""
    # First check if there's a season marked as current
    current = Season.query.filter_by(is_current=True).first()
    if current:
        # Verify it's actually current
        now = datetime.utcnow()
        if current.start_date <= now <= current.end_date:
            return current
        # If not, mark it as not current
        current.is_current = False
        db.session.commit()

    # Find or create the season for the current date
    now = datetime.utcnow()
    quarter, year = get_quarter_info(now)

    # Check if season exists
    season_name = f"Q{quarter} {year}"
    season = Season.query.filter_by(name=season_name).first()

    if not season:
        # Create new season
        season = create_season(year, quarter)

    # Mark as current and reset all players' ELO if transitioning
    if not season.is_current:
        # Unmark all other seasons as current
        Season.query.filter_by(is_current=True).update({Season.is_current: False})

        season.is_current = True
        db.session.commit()

        # Reset all players' ELO ratings to 1500 for the new season
        reset_elo_ratings()

    return season


def get_season_for_date(date):
    """Get the season for a specific date."""
    seasons = Season.query.all()
    for season in seasons:
        if season.start_date <= date <= season.end_date:
            return season

    # If no season exists for this date, create one
    quarter, year = get_quarter_info(date)
    return create_season(year, quarter)


def reset_elo_ratings():
    """Reset all players' ELO ratings to 1500."""
    Player.query.update({Player.elo_rating: 1500})
    db.session.commit()


def get_all_seasons(order_by_newest=True):
    """Get all seasons, ordered by start date."""
    if order_by_newest:
        return Season.query.order_by(Season.start_date.desc()).all()
    return Season.query.order_by(Season.start_date.asc()).all()


def get_season_by_id(season_id):
    """Get a specific season by ID."""
    return Season.query.get(season_id)
