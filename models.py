from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    elo_rating = db.Column(db.Integer, default=1500, nullable=False)  # Global ELO
    elo_1v1 = db.Column(db.Integer, default=1500, nullable=False)  # 1v1 specific ELO
    elo_2v2 = db.Column(db.Integer, default=1500, nullable=False)  # 2v2 specific ELO
    elo_2v1 = db.Column(db.Integer, default=1500, nullable=False)  # 2v1 specific ELO
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Player {self.name}>"


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    game_type = db.Column(db.String(10), nullable=False)  # '1v1', '2v2', '2v1'
    team1_score = db.Column(db.Integer, nullable=False)
    team2_score = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    players = db.relationship(
        "GamePlayer", back_populates="game", cascade="all, delete-orphan"
    )

    @property
    def duration_minutes(self):
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() / 60)
        return None

    @property
    def is_shutout(self):
        return abs(self.team1_score - self.team2_score) >= 10

    def __repr__(self):
        return f"<Game {self.team1_score}-{self.team2_score} ({self.game_type})>"


class GamePlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    team = db.Column(db.Integer, nullable=False)  # 1 or 2
    is_winner = db.Column(db.Boolean, nullable=False)
    elo_change = db.Column(db.Integer, nullable=True)  # ELO rating change for this game

    game = db.relationship("Game", back_populates="players")
    player = db.relationship("Player")

    def __repr__(self):
        return f"<GamePlayer {self.player.name} Team{self.team}>"


class CakeBalance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    creditor_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    balance = db.Column(db.Integer, default=0)

    debtor = db.relationship("Player", foreign_keys=[debtor_id])
    creditor = db.relationship("Player", foreign_keys=[creditor_id])

    def __repr__(self):
        return f"<CakeBalance {self.debtor.name} owes {self.creditor.name}: {self.balance}>"


class LeaderboardHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    snapshot_date = db.Column(db.Date, nullable=False)
    rank = db.Column(db.Integer, nullable=False)
    elo_rating = db.Column(db.Integer, nullable=False)
    total_games = db.Column(db.Integer, nullable=False)

    player = db.relationship("Player")

    __table_args__ = (
        db.UniqueConstraint("player_id", "snapshot_date", name="unique_player_date"),
    )

    def __repr__(self):
        return f"<LeaderboardHistory {self.player.name} rank {self.rank} on {self.snapshot_date}>"


class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default="setup")  # 'setup', 'active', 'completed'

    matches = db.relationship("TournamentMatch", back_populates="tournament", cascade="all, delete-orphan")
    participants = db.relationship("TournamentParticipant", back_populates="tournament", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tournament {self.name} ({self.status})>"


class TournamentParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournament.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    seed = db.Column(db.Integer, nullable=False)  # Tournament seeding position
    eliminated = db.Column(db.Boolean, default=False)

    tournament = db.relationship("Tournament", back_populates="participants")
    player = db.relationship("Player")

    def __repr__(self):
        return f"<TournamentParticipant {self.player.name} seed:{self.seed}>"


class TournamentMatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournament.id"), nullable=False)
    round_number = db.Column(db.Integer, nullable=False)  # 1=finals, 2=semifinals, 3=quarterfinals, etc.
    match_number = db.Column(db.Integer, nullable=False)  # Position in the round
    player1_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=True)  # Null if TBD
    player2_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=True)  # Null if TBD
    winner_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=True)  # Link to actual game played
    next_match_id = db.Column(db.Integer, db.ForeignKey("tournament_match.id"), nullable=True)  # Winner advances to this match

    tournament = db.relationship("Tournament", back_populates="matches")
    player1 = db.relationship("Player", foreign_keys=[player1_id])
    player2 = db.relationship("Player", foreign_keys=[player2_id])
    winner = db.relationship("Player", foreign_keys=[winner_id])
    game = db.relationship("Game")
    next_match = db.relationship("TournamentMatch", remote_side=[id], foreign_keys=[next_match_id])

    def __repr__(self):
        return f"<TournamentMatch R{self.round_number}M{self.match_number}>"


class GameAuditLog(db.Model):
    """Tracks all edits made to games for transparency."""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    edited_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    editor_ip = db.Column(db.String(45), nullable=True)  # IPv4/IPv6 tracking

    # JSON string storing before/after state
    changes = db.Column(db.Text, nullable=False)

    # Human-readable summary: "Changed team2 score from 5 to 6, replaced Player X with Player Y on team1"
    summary = db.Column(db.String(500), nullable=False)

    game = db.relationship("Game", backref="audit_logs")

    def __repr__(self):
        return f"<GameAuditLog game_id={self.game_id} at {self.edited_at}>"
