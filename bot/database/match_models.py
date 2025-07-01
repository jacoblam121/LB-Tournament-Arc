"""
Match Models for N-Player Tournament System

These models separate the invitation workflow (Challenge) from the game results (Match).
This allows support for FFA, Team, and other multi-player scenarios while preserving
existing Challenge functionality for 1v1 invitations.

Design Goals:
- Support N-player matches (FFA, Team battles)
- Maintain Challenge model for invitation workflow
- Enable placement-based result tracking
- Support different scoring systems (Elo, Performance Points)
- Provide flexible team_id for team battles
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text, 
    ForeignKey, Float, BigInteger, Enum as SQLEnum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict

# Import base from existing models
from bot.database.models import Base, MatchResult

class MatchStatus(Enum):
    """Status of a match from creation to completion"""
    PENDING = "pending"      # Match created, waiting for participants
    ACTIVE = "active"        # Match in progress
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # Results submitted, awaiting confirmation
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
    created_by = Column(Integer, ForeignKey('players.id'))  # Who initiated the match
    
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
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    
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