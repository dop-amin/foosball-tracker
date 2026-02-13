from datetime import datetime, timedelta
from models import db, Season, Player


def get_quarter_info(date):
    """
    Returns (quarter_num, year) for a given date.

    Args:
        date: datetime object

    Returns:
        tuple: (quarter_num, year) where quarter_num is 1-4
    """
    month = date.month
    year = date.year
    quarter = (month - 1) // 3 + 1
    return quarter, year


def get_quarter_boundaries(year, quarter):
    """
    Returns (start_date, end_date) for a given year and quarter.

    Args:
        year: int
        quarter: int (1-4)

    Returns:
        tuple: (start_date, end_date) as datetime objects
    """
    if quarter not in [1, 2, 3, 4]:
        raise ValueError("Quarter must be between 1 and 4")

    start_month = (quarter - 1) * 3 + 1
    if quarter == 4:
        end_month = 12
        end_day = 31
    else:
        end_month = start_month + 2
        if end_month == 3:
            # February - handle leap years
            if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                end_day = 29
            else:
                end_day = 28
        elif end_month in [1, 3, 5, 7, 8, 10, 12]:
            end_day = 31
        else:
            end_day = 30

    start_date = datetime(year, start_month, 1, 0, 0, 0)
    end_date = datetime(year, end_month, end_day, 23, 59, 59)

    return start_date, end_date


def create_season(year, quarter):
    """
    Creates a new season for the given year and quarter.

    Args:
        year: int
        quarter: int (1-4)

    Returns:
        Season: The newly created season
    """
    name = f"Q{quarter} {year}"
    start_date, end_date = get_quarter_boundaries(year, quarter)

    season = Season(
        name=name,
        start_date=start_date,
        end_date=end_date,
        is_current=False
    )
    db.session.add(season)
    db.session.commit()

    return season


def get_current_season():
    """
    Gets or auto-creates the current season based on the current date.
    If the current date is past the current season's end_date, automatically
    transitions to the next quarter's season.

    Returns:
        Season: The current season
    """
    now = datetime.utcnow()

    # Try to get the current season
    current_season = Season.query.filter_by(is_current=True).first()

    # Check if we need to transition to a new season
    if current_season and now > current_season.end_date:
        # Time to transition to next quarter
        current_quarter, current_year = get_quarter_info(current_season.end_date + timedelta(days=1))
        new_season = create_season(current_year, current_quarter)
        transition_to_season(new_season)
        return new_season

    # If no current season exists, create one for the current quarter
    if not current_season:
        quarter, year = get_quarter_info(now)
        season = create_season(year, quarter)
        transition_to_season(season)
        return season

    return current_season


def transition_to_season(season):
    """
    Transitions to a new season by:
    1. Unmarking all other seasons as current
    2. Marking the given season as current
    3. Resetting all player ELO ratings to 1500

    Args:
        season: Season object to transition to
    """
    # Unmark all seasons as current
    Season.query.update({Season.is_current: False})

    # Mark this season as current
    season.is_current = True

    # Reset all player ELO ratings to 1500
    players = Player.query.all()
    for player in players:
        player.elo_rating = 1500

    db.session.commit()


def get_season_for_date(date):
    """
    Returns the season that contains the given date.
    If no season exists for that date, creates one.

    Args:
        date: datetime object

    Returns:
        Season: The season containing this date
    """
    # Find existing season that contains this date
    season = Season.query.filter(
        Season.start_date <= date,
        Season.end_date >= date
    ).first()

    if season:
        return season

    # No season found, create one for this date's quarter
    quarter, year = get_quarter_info(date)
    return create_season(year, quarter)
