import os
import secrets


class Config:
    """Application configuration."""

    SECRET_KEY = secrets.token_hex(32)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_PATH", "sqlite:///foosball.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
