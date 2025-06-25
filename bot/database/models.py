from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, 
    ForeignKey, Float, BigInteger, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from typing import Optional

Base = declarative_base()

class ChallengeStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class MatchResult(Enum):
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"

class Cluster(Base):
    __tablename__ = 'clusters'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    number = Column(Integer, nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    events = relationship("Event", back_populates="cluster")
    
    def __repr__(self):
        return f"<Cluster(number={self.number}, name='{self.name}')>"

class Event(Base):
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    cluster_id = Column(Integer, ForeignKey('clusters.id'), nullable=False)
    
    # Scoring configuration
    scoring_type = Column(String(20), nullable=False)  # 1v1, FFA, Team, Leaderboard
    crownslayer_pool = Column(Integer, default=300)
    
    # Game configuration (inherited from Game model)
    is_active = Column(Boolean, default=True)
    min_players = Column(Integer, default=2)
    max_players = Column(Integer, default=8)
    allow_challenges = Column(Boolean, default=True)
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    cluster = relationship("Cluster", back_populates="events")
    
    # Unique constraint within cluster
    __table_args__ = (UniqueConstraint('cluster_id', 'name'),)
    
    def __repr__(self):
        cluster_name = getattr(self.cluster, 'name', 'Unknown') if self.cluster else 'None'
        return f"<Event(name='{self.name}', cluster='{cluster_name}', type='{self.scoring_type}')>"

class Player(Base):
    __tablename__ = 'players'
    
    id = Column(Integer, primary_key=True)
    discord_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    display_name = Column(String(100))
    
    # Tournament stats
    elo_rating = Column(Integer, default=1000)
    tickets = Column(Integer, default=0)
    matches_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    
    # Metadata
    registered_at = Column(DateTime, default=func.now())
    last_active = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationships
    sent_challenges = relationship("Challenge", foreign_keys="Challenge.challenger_id", back_populates="challenger")
    received_challenges = relationship("Challenge", foreign_keys="Challenge.challenged_id", back_populates="challenged")
    
    @property
    def win_rate(self) -> float:
        if self.matches_played == 0:
            return 0.0
        return (self.wins / self.matches_played) * 100
    
    @property
    def is_provisional(self) -> bool:
        return self.matches_played < 5
    
    def __repr__(self):
        return f"<Player(discord_id={self.discord_id}, username='{self.username}', elo={self.elo_rating})>"

class Game(Base):
    __tablename__ = 'games'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    
    # Game configuration
    is_active = Column(Boolean, default=True)
    min_players = Column(Integer, default=2)
    max_players = Column(Integer, default=2)
    
    # Tournament settings
    allow_challenges = Column(Boolean, default=True)
    ticket_cost = Column(Integer, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    # challenges = relationship("Challenge", back_populates="game")  # Deprecated
    
    def __repr__(self):
        return f"<Game(name='{self.name}', active={self.is_active})>"

class Challenge(Base):
    __tablename__ = 'challenges'
    
    id = Column(Integer, primary_key=True)
    
    # Players
    challenger_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    challenged_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    
    # Challenge details
    game_id = Column(Integer, ForeignKey('games.id'), nullable=True, default=1)  # Legacy - kept for DB compatibility
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    status = Column(SQLEnum(ChallengeStatus), default=ChallengeStatus.PENDING)
    
    # Stakes
    ticket_wager = Column(Integer, default=0)
    elo_at_stake = Column(Boolean, default=True)
    
    # Messages and channels
    discord_message_id = Column(BigInteger)
    discord_channel_id = Column(BigInteger)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)
    accepted_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Match results (filled when challenge is completed)
    challenger_result = Column(SQLEnum(MatchResult))
    challenged_result = Column(SQLEnum(MatchResult))
    
    # Elo changes (calculated after match)
    challenger_elo_change = Column(Integer, default=0)
    challenged_elo_change = Column(Integer, default=0)
    
    # Admin notes
    admin_notes = Column(Text)
    
    # Relationships
    challenger = relationship("Player", foreign_keys=[challenger_id], back_populates="sent_challenges")
    challenged = relationship("Player", foreign_keys=[challenged_id], back_populates="received_challenges")
    game = relationship("Game")  # Legacy - for DB compatibility
    event = relationship("Event")
    
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_active(self) -> bool:
        return self.status in [ChallengeStatus.PENDING, ChallengeStatus.ACCEPTED]
    
    def __repr__(self):
        return f"<Challenge(id={self.id}, challenger={self.challenger_id}, challenged={self.challenged_id}, status={self.status.value})>"

class Tournament(Base):
    __tablename__ = 'tournaments'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    
    # Tournament configuration
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    max_participants = Column(Integer)
    entry_fee = Column(Integer, default=0)
    
    # Tournament status
    is_active = Column(Boolean, default=False)
    is_registration_open = Column(Boolean, default=False)
    
    # Scheduling
    registration_opens = Column(DateTime)
    registration_closes = Column(DateTime)
    tournament_starts = Column(DateTime)
    tournament_ends = Column(DateTime)
    
    # Prize configuration
    first_place_tickets = Column(Integer, default=0)
    second_place_tickets = Column(Integer, default=0)
    third_place_tickets = Column(Integer, default=0)
    
    # Discord integration
    discord_channel_id = Column(BigInteger)
    discord_role_id = Column(BigInteger)
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    created_by = Column(Integer, ForeignKey('players.id'))
    
    # Relationships
    event = relationship("Event")
    creator = relationship("Player")
    
    def __repr__(self):
        return f"<Tournament(name='{self.name}', active={self.is_active})>"

class EloHistory(Base):
    __tablename__ = 'elo_history'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    
    # Elo change details
    old_elo = Column(Integer, nullable=False)
    new_elo = Column(Integer, nullable=False)
    elo_change = Column(Integer, nullable=False)
    
    # Match context
    challenge_id = Column(Integer, ForeignKey('challenges.id'))
    opponent_id = Column(Integer, ForeignKey('players.id'))
    match_result = Column(SQLEnum(MatchResult), nullable=False)
    
    # K-factor used in calculation
    k_factor = Column(Integer, nullable=False)
    
    # Timestamp
    recorded_at = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("Player", foreign_keys=[player_id])
    challenge = relationship("Challenge")
    opponent = relationship("Player", foreign_keys=[opponent_id])
    
    def __repr__(self):
        return f"<EloHistory(player_id={self.player_id}, change={self.elo_change}, new_elo={self.new_elo})>"

class Ticket(Base):
    __tablename__ = 'tickets'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    
    # Ticket transaction details
    amount = Column(Integer, nullable=False)  # Positive for gains, negative for losses
    transaction_type = Column(String(50), nullable=False)  # 'challenge_win', 'challenge_loss', 'admin_grant', etc.
    
    # Context
    challenge_id = Column(Integer, ForeignKey('challenges.id'))
    description = Column(String(255))
    
    # Admin tracking
    granted_by = Column(Integer, ForeignKey('players.id'))  # For admin transactions
    
    # Timestamp
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("Player", foreign_keys=[player_id])
    challenge = relationship("Challenge")
    admin = relationship("Player", foreign_keys=[granted_by])
    
    def __repr__(self):
        return f"<Ticket(player_id={self.player_id}, amount={self.amount}, type='{self.transaction_type}')>"