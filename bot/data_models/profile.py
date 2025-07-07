"""
Profile data models for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides immutable data transfer objects for profile-related data aggregation.
"""

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass(frozen=True)
class ClusterStats:
    """Stats for a single cluster."""
    cluster_name: str
    cluster_id: int
    scoring_elo: int
    raw_elo: int
    matches_played: int
    rank_in_cluster: int
    is_below_threshold: bool  # For 💀 emoji


@dataclass(frozen=True)
class MatchRecord:
    """Single match history entry."""
    match_id: int
    opponent_name: str
    opponent_id: int
    result: str  # 'win', 'loss', 'draw'
    elo_change: int
    event_name: str
    played_at: datetime


@dataclass(frozen=True)
class ProfileData:
    """Complete profile data for a player."""
    # Basic info
    player_id: int
    display_name: str
    is_ghost: bool  # Left server
    
    # Core stats - using Player model fields
    final_score: int
    overall_scoring_elo: int
    overall_raw_elo: int
    server_rank: int
    total_players: int
    
    # Economy
    ticket_balance: int
    shard_bonus: int          # Total shard bonuses earned
    shop_bonus: int           # Total shop bonuses applied
    
    # Match stats - using Player model legacy fields  
    total_matches: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    current_streak: Optional[str]  # W3, L1, etc. or None if no streak
    
    # Cluster performance
    top_clusters: List[ClusterStats]  # Top 3
    bottom_clusters: List[ClusterStats]  # Bottom 3
    all_clusters: List[ClusterStats]  # All clusters with stats
    
    # Recent activity
    recent_matches: List[MatchRecord]  # Last 5
    
    # Customization
    profile_color: Optional[int]  # Hex color for embed