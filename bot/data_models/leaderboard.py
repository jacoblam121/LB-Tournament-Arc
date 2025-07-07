"""
Leaderboard data models for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides immutable data transfer objects for leaderboard-related data aggregation.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class LeaderboardEntry:
    """Single leaderboard row."""
    rank: int
    player_id: int
    display_name: str
    final_score: int
    overall_scoring_elo: int
    overall_raw_elo: int
    shard_bonus: int
    shop_bonus: int
    is_ghost: bool


@dataclass(frozen=True)
class LeaderboardPage:
    """Paginated leaderboard data."""
    entries: List[LeaderboardEntry]
    current_page: int
    total_pages: int
    total_players: int
    sort_by: str
    leaderboard_type: str
    cluster_name: Optional[str] = None
    event_name: Optional[str] = None