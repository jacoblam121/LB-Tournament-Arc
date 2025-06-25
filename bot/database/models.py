from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, 
    ForeignKey, Float, BigInteger, Enum as SQLEnum, UniqueConstraint, CheckConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

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
    
    # Match context - Non-destructive migration approach
    challenge_id = Column(Integer, ForeignKey('challenges.id'), nullable=True)  # Legacy: kept for backward compatibility
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=True)  # New: for N-player matches
    opponent_id = Column(Integer, ForeignKey('players.id'))  # For 1v1 context, null for FFA
    match_result = Column(SQLEnum(MatchResult), nullable=False)
    
    # K-factor used in calculation
    k_factor = Column(Integer, nullable=False)
    
    # Timestamp
    recorded_at = Column(DateTime, default=func.now())
    
    # Database constraints for data integrity
    __table_args__ = (
        CheckConstraint(
            '(challenge_id IS NOT NULL AND match_id IS NULL) OR (challenge_id IS NULL AND match_id IS NOT NULL)',
            name='elo_history_context_check'
        ),
    )
    
    # Relationships
    player = relationship("Player", foreign_keys=[player_id])
    challenge = relationship("Challenge")  # Legacy relationship
    match = relationship("Match")  # New relationship for N-player matches
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

# ============================================================================
# Phase 2A2: Match Models for N-Player Support
# ============================================================================

class MatchStatus(Enum):
    """Status of a match from creation to completion"""
    PENDING = "pending"      # Match created, waiting for participants
    ACTIVE = "active"        # Match in progress
    COMPLETED = "completed"  # Match finished with results
    CANCELLED = "cancelled"  # Match cancelled by admin

class MatchFormat(Enum):
    """Type of match format"""
    ONE_V_ONE = "1v1"       # Traditional 1v1 match
    FFA = "ffa"             # Free-for-all (every player for themselves)
    TEAM = "team"           # Team-based match
    LEADERBOARD = "leaderboard"  # Leaderboard/campaign style

class Match(Base):
    """
    Represents a completed or in-progress match between N players.
    
    This model handles the actual game results, separate from the invitation
    workflow handled by Challenge. Supports all match types including FFA.
    """
    __tablename__ = 'matches'
    
    id = Column(Integer, primary_key=True)
    
    # Match configuration
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    match_format = Column(SQLEnum(MatchFormat), nullable=False)
    status = Column(SQLEnum(MatchStatus), default=MatchStatus.PENDING)
    
    # Optional challenge link (for 1v1 matches originating from challenges)
    challenge_id = Column(Integer, ForeignKey('challenges.id'), nullable=True)
    
    # Match timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Admin and meta information
    admin_notes = Column(Text)
    created_by = Column(Integer, ForeignKey('players.id'), nullable=True)  # Who initiated the match (nullable for system-created)
    
    # Discord integration
    discord_channel_id = Column(BigInteger)  # Where results were reported
    discord_message_id = Column(BigInteger)  # Result message
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    event = relationship("Event")
    challenge = relationship("Challenge")  # Optional - only for 1v1 from challenges
    created_by_player = relationship("Player", foreign_keys=[created_by])
    participants = relationship("MatchParticipant", back_populates="match", cascade="all, delete-orphan")
    
    @property
    def is_active(self) -> bool:
        """Check if match is currently active"""
        return self.status in [MatchStatus.PENDING, MatchStatus.ACTIVE]
    
    @property
    def participant_count(self) -> int:
        """Get number of participants in this match"""
        return len(self.participants)
    
    @property
    def duration_minutes(self) -> Optional[float]:
        """Calculate match duration in minutes if completed"""
        if not self.started_at or not self.completed_at:
            return None
        delta = self.completed_at - self.started_at
        return delta.total_seconds() / 60
    
    def get_winner(self) -> Optional['MatchParticipant']:
        """Get the participant with placement = 1 (first place)"""
        for participant in self.participants:
            if participant.placement == 1:
                return participant
        return None
    
    def get_participants_by_placement(self) -> List['MatchParticipant']:
        """Get participants ordered by placement (1st, 2nd, 3rd, etc.)"""
        return sorted(self.participants, key=lambda p: p.placement or 999)
    
    def __repr__(self):
        return f"<Match(id={self.id}, format={self.match_format.value}, status={self.status.value}, participants={self.participant_count})>"

class MatchParticipant(Base):
    """
    Represents a single participant in a match with their results.
    
    This model tracks individual player performance including placement,
    score changes, and team affiliation for team-based matches.
    """
    __tablename__ = 'match_participants'
    
    id = Column(Integer, primary_key=True)
    
    # Core relationships
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False, index=True)
    
    # Team support (nullable for non-team matches)
    team_id = Column(String(50), nullable=True)  # Team identifier (A, B, Red, Blue, etc.)
    team_name = Column(String(100), nullable=True)  # Human-readable team name
    
    # Match results
    placement = Column(Integer, nullable=True)  # 1st place = 1, 2nd = 2, etc. Null for incomplete
    
    # Scoring changes
    elo_change = Column(Integer, default=0)  # Elo rating change from this match
    pp_change = Column(Integer, default=0)   # Performance Points change
    points_earned = Column(Integer, default=0)  # Points earned (for leaderboard events)
    
    # Pre-match ratings (for calculation verification)
    elo_before = Column(Integer, nullable=True)
    elo_after = Column(Integer, nullable=True)
    
    # Match-specific stats (optional, for future extension)
    custom_stats = Column(Text)  # JSON string for game-specific statistics
    
    # Admin tracking
    manually_adjusted = Column(Boolean, default=False)  # True if admin manually set results
    adjustment_reason = Column(String(255))  # Reason for manual adjustment
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Database constraints and indexes for data integrity and performance
    __table_args__ = (
        CheckConstraint('placement > 0', name='positive_placement_check'),
        UniqueConstraint('match_id', 'player_id', name='unique_player_per_match'),
        # Note: No unique constraint on placement to allow ties (multiple players with same placement)
    )
    
    # Relationships
    match = relationship("Match", back_populates="participants")
    player = relationship("Player")
    
    @property
    def total_rating_change(self) -> int:
        """Get total rating change (Elo + PP)"""
        return self.elo_change + self.pp_change
    
    @property
    def is_winner(self) -> bool:
        """Check if this participant won (placement = 1)"""
        return self.placement == 1
    
    @property
    def placement_suffix(self) -> str:
        """Get placement with ordinal suffix (1st, 2nd, 3rd, etc.)"""
        if not self.placement:
            return "Unranked"
        
        if 10 <= self.placement % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(self.placement % 10, "th")
        
        return f"{self.placement}{suffix}"
    
    def get_match_result(self) -> MatchResult:
        """Convert placement to MatchResult enum for compatibility"""
        if not self.placement:
            return MatchResult.DRAW  # Incomplete/unranked
        elif self.placement == 1:
            return MatchResult.WIN
        else:
            return MatchResult.LOSS
    
    def __repr__(self):
        team_info = f", team={self.team_id}" if self.team_id else ""
        return f"<MatchParticipant(player_id={self.player_id}, placement={self.placement}, elo_change={self.elo_change}{team_info})>"