from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, 
    ForeignKey, Float, BigInteger, Enum as SQLEnum, UniqueConstraint, CheckConstraint, event
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
    
    # UI Aggregation fields
    base_event_name = Column(String(200), nullable=True, index=True)  # Base name without scoring type suffix for grouping
    
    # Scoring configuration
    scoring_type = Column(String(20), nullable=True)  # 1v1, FFA, Team, Leaderboard - DEPRECATED: moving to match level
    score_direction = Column(String(10), nullable=True)  # "HIGH" or "LOW" for leaderboard events
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
    player_stats = relationship("PlayerEventStats", back_populates="event", cascade="all, delete-orphan")
    
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
    
    # Tournament stats (global legacy stats)
    elo_rating = Column(Integer, default=1000)  # Legacy global Elo, supplemented by per-event stats
    tickets = Column(Integer, default=0)        # Current ticket balance (cache of TicketLedger)
    matches_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    
    # Meta-game fields for leverage system and streak tracking
    active_leverage_token = Column(String(50), nullable=True)  # e.g., "2x_standard", "1.5x_forced"
    current_streak = Column(Integer, default=0)               # Current win/loss streak
    max_streak = Column(Integer, default=0)                   # Highest win streak achieved
    
    # Metadata
    registered_at = Column(DateTime, default=func.now())
    last_active = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
    
    # Challenge relationships now managed via ChallengeParticipant table
    event_stats = relationship("PlayerEventStats", back_populates="player", cascade="all, delete-orphan")
    ticket_history = relationship("TicketLedger", back_populates="player", cascade="all, delete-orphan", foreign_keys="TicketLedger.player_id")
    
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
    
    # Players managed via ChallengeParticipant table (N-player support)
    
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
    # DEPRECATED: Legacy 2-player result fields - kept for backward compatibility only
    # NEW DEVELOPMENT: Use Match and MatchParticipant tables for all results
    # DO NOT WRITE to these fields for new challenges
    challenger_result = Column(SQLEnum(MatchResult))  # DEPRECATED - see Phase 2.1.1
    challenged_result = Column(SQLEnum(MatchResult))  # DEPRECATED - see Phase 2.1.1
    
    # Elo changes (calculated after match)
    # DEPRECATED: Legacy Elo change tracking - kept for backward compatibility only  
    # NEW DEVELOPMENT: Use MatchParticipant.elo_change for all Elo tracking
    challenger_elo_change = Column(Integer, default=0)  # DEPRECATED - see Phase 2.1.1
    challenged_elo_change = Column(Integer, default=0)  # DEPRECATED - see Phase 2.1.1
    
    # Admin notes
    admin_notes = Column(Text)
    
    # Relationships
    game = relationship("Game")  # Legacy - for DB compatibility
    event = relationship("Event")
    participants = relationship("ChallengeParticipant", back_populates="challenge", cascade="all, delete-orphan")
    
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_active(self) -> bool:
        return self.status in [ChallengeStatus.PENDING, ChallengeStatus.ACCEPTED]
    
    def __repr__(self):
        return f"<Challenge(id={self.id}, event_id={self.event_id}, status={self.status.value})>"

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
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False, index=True)  # CRITICAL: Per-event audit trail
    
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
    
    # Database constraints for data integrity - RELAXED to allow admin adjustments
    __table_args__ = (
        # Removed overly strict constraint to allow both challenge_id and match_id to be NULL
        # This supports admin adjustments and per-event Elo changes not tied to specific matches
    )
    
    # Relationships
    player = relationship("Player", foreign_keys=[player_id])
    event = relationship("Event")  # CRITICAL: Event context for per-event audit trail
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
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # Results proposed, awaiting confirmation
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

# ============================================================================
# Phase B: Confirmation System Models
# ============================================================================

class ConfirmationStatus(Enum):
    """Status of a player's confirmation for match results"""
    PENDING = "pending"      # Not yet responded
    CONFIRMED = "confirmed"  # Player confirmed the results
    REJECTED = "rejected"    # Player rejected the results

class ChallengeRole(Enum):
    """Role of a participant in a challenge"""
    CHALLENGER = "challenger"  # Challenge initiator (lowercase for SQL compatibility)
    CHALLENGED = "challenged"  # Challenge recipient (lowercase for SQL compatibility)

class ChallengeParticipant(Base):
    """
    Represents a participant in an N-player challenge.
    
    This model enables challenges to support multiple players (FFA, teams)
    beyond the traditional 1v1 format. Each participant can accept/decline
    independently and be assigned to teams for team-based challenges.
    """
    __tablename__ = 'challenge_participants'
    
    id = Column(Integer, primary_key=True)
    challenge_id = Column(Integer, ForeignKey('challenges.id'), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False, index=True)
    
    # Participant status (for accept/decline tracking)
    status = Column(SQLEnum(ConfirmationStatus), default=ConfirmationStatus.PENDING, nullable=False)
    responded_at = Column(DateTime, nullable=True)
    
    # Team support (nullable for non-team challenges)
    team_id = Column(String(50), nullable=True)  # Team identifier (A, B, Red, Blue, etc.)
    
    # Participant role (required for challenge logic)
    role = Column(SQLEnum(ChallengeRole), nullable=True)  # Start nullable for migration
    
    # Note: Will be made NOT NULL after migration completes
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    challenge = relationship("Challenge", back_populates="participants")
    player = relationship("Player")
    
    # Constraints - prevent duplicate participants
    __table_args__ = (
        UniqueConstraint('challenge_id', 'player_id', name='unique_player_per_challenge'),
    )
    
    def __repr__(self):
        return f"<ChallengeParticipant(challenge_id={self.challenge_id}, player_id={self.player_id}, status={self.status.value})>"

class MatchResultProposal(Base):
    """
    Represents a proposed set of match results awaiting confirmation.
    
    When a match result is reported, it creates a proposal that all
    participants must confirm before the results become final.
    """
    __tablename__ = 'match_result_proposals'
    
    id = Column(Integer, primary_key=True)
    
    # Core relationships
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=False, unique=True)
    proposer_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    
    # Proposed results (JSON format for flexibility)
    # Format: [{"player_id": 123, "placement": 1}, {"player_id": 456, "placement": 2}]
    proposed_results = Column(Text, nullable=False)
    
    # Timing
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=False)
    
    # Status tracking
    is_active = Column(Boolean, default=True)  # False if expired or finalized
    
    # Discord integration (for tracking where proposal was made)
    discord_channel_id = Column(BigInteger)
    discord_message_id = Column(BigInteger)
    
    # Relationships
    match = relationship("Match")
    proposer = relationship("Player")
    
    def __repr__(self):
        return f"<MatchResultProposal(match_id={self.match_id}, proposer_id={self.proposer_id}, active={self.is_active})>"

class MatchConfirmation(Base):
    """
    Tracks each participant's confirmation/rejection of proposed match results.
    
    Each participant in a match gets one confirmation record when results
    are proposed. They can confirm or reject with an optional reason.
    """
    __tablename__ = 'match_confirmations'
    
    id = Column(Integer, primary_key=True)
    
    # Core relationships
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False, index=True)
    
    # Confirmation details
    status = Column(SQLEnum(ConfirmationStatus), default=ConfirmationStatus.PENDING, nullable=False)
    responded_at = Column(DateTime, nullable=True)
    rejection_reason = Column(String(500), nullable=True)  # Optional reason if rejected
    
    # Discord tracking (for audit trail)
    discord_user_id = Column(BigInteger)  # Who actually clicked confirm/reject
    discord_message_id = Column(BigInteger)  # Message where they responded
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    match = relationship("Match")
    player = relationship("Player")
    
    # Database constraints
    __table_args__ = (
        UniqueConstraint('match_id', 'player_id', name='unique_confirmation_per_player_match'),
    )
    
    def __repr__(self):
        return f"<MatchConfirmation(match_id={self.match_id}, player_id={self.player_id}, status={self.status.value})>"

# ============================================================================
# Phase 1.1: Per-Event Elo Tracking and Meta-Game Foundation
# ============================================================================

class PlayerEventStats(Base):
    """
    Per-event Elo tracking with dual-track system for hierarchical tournament structure.
    
    This model enables per-event Elo ratings while maintaining a dual-track system:
    - raw_elo: True skill rating (can go below 1000)
    - scoring_elo: Display rating (floored at 1000)
    """
    __tablename__ = 'player_event_stats'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    
    # Dual-track Elo system
    raw_elo = Column(Integer, default=1000)
    scoring_elo = Column(Integer, default=1000)  # max(raw_elo, 1000)
    
    # Event-specific stats
    matches_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    
    # Leaderboard Event fields (for scoring_type="Leaderboard")
    all_time_leaderboard_elo = Column(Integer, nullable=True)  # From personal best Z-score conversion
    
    # Meta-game economy fields (cumulative accumulators)
    final_score = Column(Integer, nullable=True)  # Total score points accumulated in this event
    shard_bonus = Column(Integer, default=0)      # Total Shard of the Crown bonuses earned
    shop_bonus = Column(Integer, default=0)       # Total shop-purchased bonuses applied
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    player = relationship("Player", back_populates="event_stats")
    event = relationship("Event", back_populates="player_stats")
    
    # K-factor tracking
    @property
    def is_provisional(self) -> bool:
        return self.matches_played < 5
    
    @property
    def k_factor(self) -> int:
        return 40 if self.is_provisional else 20
    
    def update_scoring_elo(self):
        """Apply dual-track Elo floor rule"""
        self.scoring_elo = max(self.raw_elo, 1000)

    __table_args__ = (
        UniqueConstraint('player_id', 'event_id', name='uq_player_event_stats'),
    )
    
    def __repr__(self):
        return f"<PlayerEventStats(player_id={self.player_id}, event_id={self.event_id}, raw_elo={self.raw_elo}, scoring_elo={self.scoring_elo})>"

class PlayerEventPersonalBest(Base):
    """
    Tracks personal best scores for leaderboard events.
    
    For leaderboard events, this stores the best score achieved by each player.
    The score interpretation depends on the event's score_direction:
    - HIGH: Higher scores are better (e.g., points, kills)
    - LOW: Lower scores are better (e.g., time, speedruns)
    """
    __tablename__ = 'player_event_personal_bests'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    
    best_score = Column(Float, nullable=False)  # Actual score (points, time, etc.)
    timestamp_achieved = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("Player")
    event = relationship("Event")
    
    __table_args__ = (
        UniqueConstraint('player_id', 'event_id'),
    )
    
    def __repr__(self):
        return f"<PlayerEventPersonalBest(player_id={self.player_id}, event_id={self.event_id}, best_score={self.best_score})>"

class WeeklyScores(Base):
    """
    Temporary weekly leaderboard data for leaderboard events.
    
    Stores weekly scores that are archived and cleared periodically.
    Used for calculating weekly leaderboard rankings.
    """
    __tablename__ = 'weekly_scores'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    
    score = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("Player")
    event = relationship("Event")
    
    def __repr__(self):
        return f"<WeeklyScores(player_id={self.player_id}, event_id={self.event_id}, score={self.score})>"

class PlayerWeeklyLeaderboardElo(Base):
    """
    Historical weekly leaderboard Elo results.
    
    Permanent log of weekly Elo calculations for leaderboard events.
    Preserves historical data for audits and retrospectives.
    """
    __tablename__ = 'player_weekly_leaderboard_elo'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    
    week_number = Column(Integer, nullable=False)  # Season week number
    weekly_elo_score = Column(Integer, nullable=False)
    
    # Relationships
    player = relationship("Player")
    event = relationship("Event")
    
    __table_args__ = (
        UniqueConstraint('player_id', 'event_id', 'week_number'),
    )
    
    def __repr__(self):
        return f"<PlayerWeeklyLeaderboardElo(player_id={self.player_id}, event_id={self.event_id}, week={self.week_number}, elo={self.weekly_elo_score})>"

class TicketLedger(Base):
    """
    Atomic ticket transaction ledger for the meta-game economy.
    
    This model provides atomic ticket balance tracking with full audit trail.
    Each transaction records the change amount, reason, and balance after transaction.
    """
    __tablename__ = 'ticket_ledger'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    
    change_amount = Column(Integer, nullable=False)  # Can be positive or negative
    reason = Column(String(255), nullable=False)     # e.g., "MATCH_WIN", "ADMIN_GRANT", "SHOP_PURCHASE"
    balance_after = Column(Integer, nullable=False)  # Computed atomically with SELECT FOR UPDATE
    
    # Optional references for context tracking
    related_match_id = Column(Integer, ForeignKey('matches.id'), nullable=True)
    related_challenge_id = Column(Integer, ForeignKey('challenges.id'), nullable=True)
    admin_user_id = Column(Integer, ForeignKey('players.id'), nullable=True)  # For admin transactions
    
    # Metadata
    timestamp = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("Player", back_populates="ticket_history", foreign_keys=[player_id])
    match = relationship("Match", foreign_keys=[related_match_id])
    challenge = relationship("Challenge", foreign_keys=[related_challenge_id])
    admin_user = relationship("Player", foreign_keys=[admin_user_id])
    
    def __repr__(self):
        return f"<TicketLedger(player_id={self.player_id}, amount={self.change_amount}, balance_after={self.balance_after}, reason='{self.reason}')>"

# ============================================================================
# SQLAlchemy Event Listeners for Automatic Dual-Track Enforcement
# ============================================================================

@event.listens_for(PlayerEventStats, "before_insert")
@event.listens_for(PlayerEventStats, "before_update")
def _apply_dual_track_floor(mapper, connection, target):
    """Automatically apply scoring Elo floor on every insert/update"""
    target.scoring_elo = max(target.raw_elo, 1000)