"""Quarterly season management.

Game timestamps are naive local times (entered via datetime-local inputs), so
all "now" comparisons here use naive local time as well.
"""

import calendar
from datetime import datetime
from flask import request
from sqlalchemy.exc import IntegrityError
from models import db, Season


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


def season_name(year, quarter):
    """Name of a season, e.g. "Q4 2026". Seasons are identified by name."""
    return f"Q{quarter} {year}"


def season_name_for(date):
    """Name of the season (quarter) containing ``date``."""
    quarter, year = get_quarter_info(date)
    return season_name(year, quarter)


def current_season_name():
    """Name of the season for today's quarter."""
    return season_name_for(datetime.now())


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
    end_month = start_month + 2
    end_day = calendar.monthrange(year, end_month)[1]

    start_date = datetime(year, start_month, 1, 0, 0, 0)
    end_date = datetime(year, end_month, end_day, 23, 59, 59)

    return start_date, end_date


def create_season(year, quarter):
    """
    Creates a new season for the given year and quarter, or returns the existing one.

    The new season is only flushed, not committed, so it becomes part of the
    caller's transaction and disappears again if that transaction is rolled
    back. Call this before making other changes in the session: if another
    request created the same season concurrently, the session is rolled back.
    (A savepoint does not help here: pysqlite commits a SAVEPOINT that is the
    first statement of a transaction when it is released.)

    Args:
        year: int
        quarter: int (1-4)

    Returns:
        Season: The newly created or existing season
    """
    name = season_name(year, quarter)
    existing = Season.query.filter_by(name=name).first()
    if existing:
        return existing

    start_date, end_date = get_quarter_boundaries(year, quarter)
    season = Season(name=name, start_date=start_date, end_date=end_date)
    db.session.add(season)
    try:
        db.session.flush()
    except IntegrityError:
        # Another request created it concurrently
        db.session.rollback()
        return Season.query.filter_by(name=name).one()

    return season


def get_season_for_date(date):
    """
    Returns the season (quarter) that contains the given date, creating it
    if necessary. Seasons are identified by their quarter name, so stored
    boundaries are never needed for the lookup.

    Args:
        date: datetime object

    Returns:
        Season: The season containing this date
    """
    quarter, year = get_quarter_info(date)
    return create_season(year, quarter)


def get_current_season():
    """
    Gets the season of the current quarter, creating (and committing) it if
    it does not exist yet.

    Returns:
        Season: The current season
    """
    season = Season.query.filter_by(name=current_season_name()).first()
    if season is None:
        season = get_season_for_date(datetime.now())
        db.session.commit()
    return season


def season_from_request():
    """Resolve the current request's ``season`` query parameter (default: current)."""
    return resolve_season_param(request.args.get("season"))


def resolve_season_param(season_param):
    """
    Resolve a ``season`` query parameter.

    Args:
        season_param: "current", "all-time" or a season ID

    Returns:
        tuple (Season or None, selected value). None means "all-time".
    """
    if season_param == "all-time":
        return None, "all-time"

    try:
        season = db.session.get(Season, int(season_param))
    except (ValueError, TypeError):
        season = None
    if season is not None:
        return season, season.id

    return get_current_season(), "current"
