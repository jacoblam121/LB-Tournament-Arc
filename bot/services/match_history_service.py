"""
Match History Service for Phase 3.5 - Enhanced Match History System

Provides comprehensive match history commands with efficient cursor-based pagination 
and multi-view support for player, cluster, and event history.
"""

from typing import NamedTuple, Optional, List, Dict, Union
from datetime import datetime
from enum import IntEnum
from dataclasses import dataclass
from sqlalchemy import select, union_all, literal, or_, and_, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from bot.services.base import BaseService
from bot.database.models import (
    Player, Match, MatchParticipant, LeaderboardScore, Event, Cluster,
    ScoreType, MatchStatus, HistoryEntryType as ModelHistoryEntryType
)
from collections import defaultdict
import logging
import base64
import json

logger = logging.getLogger(__name__)

# Data structures for Phase 3.5 - using IntEnum for proper sorting
class HistoryEntryType(IntEnum):
    """Use numeric values for consistent ordering across databases"""
    MATCH = 1
    LEADERBOARD = 2

class HistoryCursor(NamedTuple):
    """Cursor for efficient pagination without OFFSET"""
    timestamp: datetime
    type: HistoryEntryType  # Entry type to prevent ID collisions across tables
    id: int  # Primary key (unique within each table)
    
    def encode(self) -> str:
        """Encode cursor to base64 string for client use"""
        data = {
            'timestamp': self.timestamp.isoformat(),
            'type': self.type.value,
            'id': self.id
        }
        json_str = json.dumps(data)
        return base64.b64encode(json_str.encode()).decode()
    
    @classmethod
    def decode(cls, cursor_str: str) -> 'HistoryCursor':
        """Decode cursor from base64 string"""
        try:
            json_str = base64.b64decode(cursor_str.encode()).decode()
            data = json.loads(json_str)
            return cls(
                timestamp=datetime.fromisoformat(data['timestamp']),
                type=HistoryEntryType(data['type']),
                id=data['id']
            )
        except Exception as e:
            logger.warning(f"Failed to decode cursor: {e}")
            return None

@dataclass
class ParticipantData:
    """Data for a single match participant"""
    player_id: int
    display_name: str
    placement: int
    elo_change: Optional[int] = None

@dataclass
class HistoryEntry:
    """Unified entry for both matches and leaderboard scores"""
    id: int
    type: HistoryEntryType
    timestamp: datetime
    event_name: str
    event_id: int
    cluster_name: str
    cluster_id: int
    
    # Match-specific fields (None for leaderboard entries)
    opponent_names: Optional[List[str]] = None
    opponent_ids: Optional[List[int]] = None
    result: Optional[str] = None  # "win", "loss"
    elo_change: Optional[int] = None
    placement: Optional[int] = None
    match_format: Optional[str] = None
    
    # Enhanced participant data for event-centric views
    all_participants: Optional[List[ParticipantData]] = None
    
    # Leaderboard-specific fields (None for match entries)
    score: Optional[float] = None
    score_direction: Optional[str] = None  # "HIGH" or "LOW"
    
    def to_cursor(self) -> HistoryCursor:
        """Convert entry to cursor for pagination"""
        return HistoryCursor(
            timestamp=self.timestamp,
            type=self.type,
            id=self.id
        )

@dataclass 
class HistoryPage:
    """Page of history entries with pagination info"""
    entries: List[HistoryEntry]
    has_next: bool
    next_cursor: Optional[str] = None
    
    # Removed total_entries and total_pages to maintain O(1) performance

class MatchHistoryService(BaseService):
    """Service for comprehensive match history with cursor-based pagination"""
    
    # Performance limits to prevent memory exhaustion
    MAX_HISTORY_LIMIT = 100
    MAX_CLUSTER_LIMIT = 50
    DEFAULT_PAGE_SIZE = 6
    
    def __init__(self, session_factory):
        super().__init__(session_factory)
    
    async def _batch_load_participants(self, session: AsyncSession, match_ids: List[int]) -> Dict[int, List]:
        """
        Batch load all participants for given match IDs to avoid N+1 queries.
        
        Args:
            session: Database session
            match_ids: List of match IDs to load participants for
            
        Returns:
            Dictionary mapping match_id to list of (participant, display_name) tuples
        """
        if not match_ids:
            return {}
        
        participants_query = (
            select(MatchParticipant, Player.display_name)
            .join(Player, MatchParticipant.player_id == Player.id)
            .where(MatchParticipant.match_id.in_(match_ids))
            .order_by(MatchParticipant.match_id, MatchParticipant.placement.asc())
        )
        
        result = await session.execute(participants_query)
        participants_by_match = defaultdict(list)
        
        for participant, display_name in result.all():
            participants_by_match[participant.match_id].append((participant, display_name))
        
        return participants_by_match
    
    async def _batch_load_all_participants(self, session: AsyncSession, match_ids: List[int]) -> Dict[int, List[ParticipantData]]:
        """
        Batch load ALL participants for given match IDs for event-centric views.
        
        Args:
            session: Database session
            match_ids: List of match IDs to load participants for
            
        Returns:
            Dictionary mapping match_id to list of ParticipantData sorted by placement
        """
        if not match_ids:
            return {}
        
        participants_query = (
            select(MatchParticipant, Player.display_name)
            .join(Player, MatchParticipant.player_id == Player.id)
            .where(MatchParticipant.match_id.in_(match_ids))
            .order_by(MatchParticipant.match_id, MatchParticipant.placement.asc())
        )
        
        result = await session.execute(participants_query)
        participants_by_match = defaultdict(list)
        
        for participant, display_name in result.all():
            participant_data = ParticipantData(
                player_id=participant.player_id,
                display_name=display_name,
                placement=participant.placement,
                elo_change=participant.elo_change
            )
            participants_by_match[participant.match_id].append(participant_data)
        
        return participants_by_match
    
    async def get_match_participants(self, match_id: int) -> List[tuple]:
        """
        Get all participants for a specific match with their placements and elo changes.
        
        Args:
            match_id: The match ID to get participants for
            
        Returns:
            List of (participant, display_name) tuples sorted by placement
        """
        async with self.get_session() as session:
            participants_query = (
                select(MatchParticipant, Player.display_name)
                .join(Player, MatchParticipant.player_id == Player.id)
                .where(MatchParticipant.match_id == match_id)
                .order_by(MatchParticipant.placement.asc())
            )
            
            result = await session.execute(participants_query)
            return result.all()
    
    async def get_player_history(self, player_id: int, page_size: int = DEFAULT_PAGE_SIZE, 
                               cursor: Optional[str] = None) -> HistoryPage:
        """
        Get paginated history for a single player combining matches and leaderboard scores.
        
        Args:
            player_id: Database player ID
            page_size: Number of entries per page (max MAX_HISTORY_LIMIT)
            cursor: Pagination cursor (encoded)
            
        Returns:
            HistoryPage with entries and pagination info
        """
        safe_page_size = min(page_size, self.MAX_HISTORY_LIMIT)
        decoded_cursor = HistoryCursor.decode(cursor) if cursor else None
        
        async with self.get_session() as session:
            # Build UNION query with timestamp aliasing
            matches_query = self._build_player_matches_query(player_id, decoded_cursor)
            leaderboard_query = self._build_player_leaderboard_query(player_id, decoded_cursor)
            
            # UNION with proper ordering
            union_query = union_all(matches_query, leaderboard_query).alias("history")
            final_query = (
                select(union_query)
                .order_by(
                    union_query.c.timestamp.desc(),
                    union_query.c.type.desc(),  # Order by type to prevent ID collisions
                    union_query.c.id.desc()
                )
                .limit(safe_page_size + 1)  # Fetch one extra to detect has_next
            )
            
            result = await session.execute(final_query)
            rows = result.all()
            
            # Extract match IDs for batch loading participants (avoid N+1 queries)
            match_ids = [row.id for row in rows[:safe_page_size] if row.type == HistoryEntryType.MATCH.value]
            participants_map = await self._batch_load_participants(session, match_ids)
            
            # Process results
            entries = []
            for i, row in enumerate(rows):
                if i >= safe_page_size:  # This is the +1 entry for has_next detection
                    break
                    
                if row.type == HistoryEntryType.MATCH.value:
                    entry = self._build_match_entry_batch(row, participants_map.get(row.id, []))
                else:  # LEADERBOARD
                    entry = self._build_leaderboard_entry(row)
                
                if entry:
                    entries.append(entry)
            
            # Pagination info
            has_next = len(rows) > safe_page_size
            next_cursor = None
            if has_next and entries:
                next_cursor = entries[-1].to_cursor().encode()
            
            return HistoryPage(
                entries=entries,
                has_next=has_next,
                next_cursor=next_cursor
            )
    
    async def get_cluster_history(self, cluster_id: int, page_size: int = DEFAULT_PAGE_SIZE,
                                cursor: Optional[str] = None) -> HistoryPage:
        """Get match history for ALL players in a cluster"""
        safe_page_size = min(page_size, self.MAX_CLUSTER_LIMIT)
        decoded_cursor = HistoryCursor.decode(cursor) if cursor else None
        
        async with self.get_session() as session:
            # Build UNION query for cluster
            matches_query = self._build_cluster_matches_query(cluster_id, decoded_cursor)
            leaderboard_query = self._build_cluster_leaderboard_query(cluster_id, decoded_cursor)
            
            # UNION with proper ordering
            union_query = union_all(matches_query, leaderboard_query).alias("history")
            final_query = (
                select(union_query)
                .order_by(
                    union_query.c.timestamp.desc(),
                    union_query.c.type.desc(),
                    union_query.c.id.desc()
                )
                .limit(safe_page_size + 1)
            )
            
            result = await session.execute(final_query)
            rows = result.all()
            
            # Extract match IDs for batch loading participants (avoid N+1 queries)
            match_ids = [row.id for row in rows[:safe_page_size] if row.type == HistoryEntryType.MATCH.value]
            # For cluster history, load ALL participants to get complete match data (same as event history)
            all_participants_map = await self._batch_load_all_participants(session, match_ids)
            
            # Process results
            entries = []
            for i, row in enumerate(rows):
                if i >= safe_page_size:
                    break
                    
                if row.type == HistoryEntryType.MATCH.value:
                    # Use complete participant data for both match entry and event display
                    all_participants = all_participants_map.get(row.id, [])
                    entry = self._build_match_entry_from_participants(row, all_participants)
                    # Populate complete participant data for event-centric display
                    entry.all_participants = all_participants
                else:
                    entry = self._build_leaderboard_entry(row)
                
                if entry:
                    entries.append(entry)
            
            has_next = len(rows) > safe_page_size
            next_cursor = None
            if has_next and entries:
                next_cursor = entries[-1].to_cursor().encode()
            
            return HistoryPage(
                entries=entries,
                has_next=has_next,
                next_cursor=next_cursor
            )
    
    async def get_event_history(self, event_id: int, page_size: int = DEFAULT_PAGE_SIZE,
                              cursor: Optional[str] = None) -> HistoryPage:
        """Get match history for ALL players in an event (auto-sorted by cluster)"""
        safe_page_size = min(page_size, self.MAX_CLUSTER_LIMIT)
        decoded_cursor = HistoryCursor.decode(cursor) if cursor else None
        
        async with self.get_session() as session:
            # Build UNION query for event
            matches_query = self._build_event_matches_query(event_id, decoded_cursor)
            leaderboard_query = self._build_event_leaderboard_query(event_id, decoded_cursor)
            
            # UNION with cluster sorting
            union_query = union_all(matches_query, leaderboard_query).alias("history")
            final_query = (
                select(union_query)
                .order_by(
                    union_query.c.cluster_id.asc(),  # Auto-sort by cluster first
                    union_query.c.timestamp.desc(),
                    union_query.c.type.desc(),
                    union_query.c.id.desc()
                )
                .limit(safe_page_size + 1)
            )
            
            result = await session.execute(final_query)
            rows = result.all()
            
            # Extract match IDs for batch loading participants (avoid N+1 queries)
            match_ids = [row.id for row in rows[:safe_page_size] if row.type == HistoryEntryType.MATCH.value]
            # For event history, load ALL participants to get complete match data
            all_participants_map = await self._batch_load_all_participants(session, match_ids)
            
            # Process results
            entries = []
            for i, row in enumerate(rows):
                if i >= safe_page_size:
                    break
                    
                if row.type == HistoryEntryType.MATCH.value:
                    # Use complete participant data for both match entry and event display
                    all_participants = all_participants_map.get(row.id, [])
                    entry = self._build_match_entry_from_participants(row, all_participants)
                    # Populate complete participant data for event-centric display
                    entry.all_participants = all_participants
                else:
                    entry = self._build_leaderboard_entry(row)
                
                if entry:
                    entries.append(entry)
            
            has_next = len(rows) > safe_page_size
            next_cursor = None
            if has_next and entries:
                next_cursor = entries[-1].to_cursor().encode()
            
            return HistoryPage(
                entries=entries,
                has_next=has_next,
                next_cursor=next_cursor
            )
    
    def _build_player_matches_query(self, player_id: int, cursor: Optional[HistoryCursor]):
        """Build matches query for a specific player"""
        query = (
            select(
                Match.id,
                literal(HistoryEntryType.MATCH.value).label("type"),
                Match.created_at.label("timestamp"),
                Event.name.label("event_name"),
                Event.id.label("event_id"),
                Cluster.name.label("cluster_name"),
                Cluster.id.label("cluster_id"),
                Match.match_format.label("match_format"),
                MatchParticipant.placement.label("placement"),
                MatchParticipant.elo_change.label("elo_change"),
                literal(None).label("score"),
                literal(None).label("score_direction")
            )
            .select_from(Match)
            .join(MatchParticipant, Match.id == MatchParticipant.match_id)
            .join(Event, Match.event_id == Event.id)
            .join(Cluster, Event.cluster_id == Cluster.id)
            .where(
                MatchParticipant.player_id == player_id,
                Match.status == MatchStatus.COMPLETED
            )
        )
        
        # Apply cursor filter if provided
        if cursor:
            query = query.where(
                or_(
                    Match.created_at < cursor.timestamp,
                    and_(
                        Match.created_at == cursor.timestamp,
                        literal(HistoryEntryType.MATCH.value) > cursor.type.value
                    ),
                    and_(
                        Match.created_at == cursor.timestamp,
                        literal(HistoryEntryType.MATCH.value) == cursor.type.value,
                        Match.id > cursor.id
                    )
                )
            )
        
        return query
    
    def _build_player_leaderboard_query(self, player_id: int, cursor: Optional[HistoryCursor]):
        """Build leaderboard query for a specific player"""
        query = (
            select(
                LeaderboardScore.id,
                literal(HistoryEntryType.LEADERBOARD.value).label("type"),
                LeaderboardScore.submitted_at.label("timestamp"),
                Event.name.label("event_name"),
                Event.id.label("event_id"),
                Cluster.name.label("cluster_name"),
                Cluster.id.label("cluster_id"),
                literal(None).label("match_format"),
                literal(None).label("placement"),
                literal(None).label("elo_change"),
                LeaderboardScore.score.label("score"),
                Event.score_direction.label("score_direction")
            )
            .select_from(LeaderboardScore)
            .join(Event, LeaderboardScore.event_id == Event.id)
            .join(Cluster, Event.cluster_id == Cluster.id)
            .where(
                LeaderboardScore.player_id == player_id,
                LeaderboardScore.score_type == ScoreType.ALL_TIME
            )
        )
        
        # Apply cursor filter if provided
        if cursor:
            query = query.where(
                or_(
                    LeaderboardScore.submitted_at < cursor.timestamp,
                    and_(
                        LeaderboardScore.submitted_at == cursor.timestamp,
                        literal(HistoryEntryType.LEADERBOARD.value) > cursor.type.value
                    ),
                    and_(
                        LeaderboardScore.submitted_at == cursor.timestamp,
                        literal(HistoryEntryType.LEADERBOARD.value) == cursor.type.value,
                        LeaderboardScore.id > cursor.id
                    )
                )
            )
        
        return query
    
    def _build_cluster_matches_query(self, cluster_id: int, cursor: Optional[HistoryCursor]):
        """Build matches query for all players in a cluster"""
        return (
            select(
                Match.id,
                literal(HistoryEntryType.MATCH.value).label("type"),
                Match.created_at.label("timestamp"),
                Event.name.label("event_name"),
                Event.id.label("event_id"),
                Cluster.name.label("cluster_name"),
                Cluster.id.label("cluster_id"),
                Match.match_format.label("match_format"),
                literal(None).label("placement"),  # Will be filled per player
                literal(None).label("elo_change"),   # Will be filled per player
                literal(None).label("score"),
                literal(None).label("score_direction")
            )
            .select_from(Match)
            .join(Event, Match.event_id == Event.id)
            .join(Cluster, Event.cluster_id == Cluster.id)
            .where(
                Cluster.id == cluster_id,
                Match.status == MatchStatus.COMPLETED
            )
        )
    
    def _build_cluster_leaderboard_query(self, cluster_id: int, cursor: Optional[HistoryCursor]):
        """Build leaderboard query for all players in a cluster"""
        return (
            select(
                LeaderboardScore.id,
                literal(HistoryEntryType.LEADERBOARD.value).label("type"),
                LeaderboardScore.submitted_at.label("timestamp"),
                Event.name.label("event_name"),
                Event.id.label("event_id"),
                Cluster.name.label("cluster_name"),
                Cluster.id.label("cluster_id"),
                literal(None).label("match_format"),
                literal(None).label("placement"),
                literal(None).label("elo_change"),
                LeaderboardScore.score.label("score"),
                Event.score_direction.label("score_direction")
            )
            .select_from(LeaderboardScore)
            .join(Event, LeaderboardScore.event_id == Event.id)
            .join(Cluster, Event.cluster_id == Cluster.id)
            .where(
                Cluster.id == cluster_id,
                LeaderboardScore.score_type == ScoreType.ALL_TIME
            )
        )
    
    def _build_event_matches_query(self, event_id: int, cursor: Optional[HistoryCursor]):
        """Build matches query for all players in an event"""
        return (
            select(
                Match.id,
                literal(HistoryEntryType.MATCH.value).label("type"),
                Match.created_at.label("timestamp"),
                Event.name.label("event_name"),
                Event.id.label("event_id"),
                Cluster.name.label("cluster_name"),
                Cluster.id.label("cluster_id"),
                Match.match_format.label("match_format"),
                literal(None).label("placement"),
                literal(None).label("elo_change"),
                literal(None).label("score"),
                literal(None).label("score_direction")
            )
            .select_from(Match)
            .join(Event, Match.event_id == Event.id)
            .join(Cluster, Event.cluster_id == Cluster.id)
            .where(
                Event.id == event_id,
                Match.status == MatchStatus.COMPLETED
            )
        )
    
    def _build_event_leaderboard_query(self, event_id: int, cursor: Optional[HistoryCursor]):
        """Build leaderboard query for all players in an event"""
        return (
            select(
                LeaderboardScore.id,
                literal(HistoryEntryType.LEADERBOARD.value).label("type"),
                LeaderboardScore.submitted_at.label("timestamp"),
                Event.name.label("event_name"),
                Event.id.label("event_id"),
                Cluster.name.label("cluster_name"),
                Cluster.id.label("cluster_id"),
                literal(None).label("match_format"),
                literal(None).label("placement"),
                literal(None).label("elo_change"),
                LeaderboardScore.score.label("score"),
                Event.score_direction.label("score_direction")
            )
            .select_from(LeaderboardScore)
            .join(Event, LeaderboardScore.event_id == Event.id)
            .join(Cluster, Event.cluster_id == Cluster.id)
            .where(
                LeaderboardScore.event_id == event_id,
                LeaderboardScore.score_type == ScoreType.ALL_TIME
            )
        )
    
    async def _build_match_entry(self, session: AsyncSession, row) -> HistoryEntry:
        """Build a HistoryEntry for a match row with opponent information"""
        # Get all participants for this match to find opponents
        participants_query = (
            select(MatchParticipant, Player.display_name)
            .join(Player, MatchParticipant.player_id == Player.id)
            .where(MatchParticipant.match_id == row.id)
        )
        
        participants_result = await session.execute(participants_query)
        participants = participants_result.all()
        
        # Find the current player and opponents
        current_participant = None
        opponents = []
        
        for participant, display_name in participants:
            if hasattr(row, 'placement') and row.placement == participant.placement:
                current_participant = participant
            else:
                opponents.append((participant, display_name))
        
        # Determine result from placement or elo_change (no draws)
        result = "loss"  # Default to loss
        if hasattr(row, 'placement') and row.placement:
            result = "win" if row.placement == 1 else "loss"
        elif hasattr(row, 'elo_change') and row.elo_change:
            result = "win" if row.elo_change > 0 else "loss"
        
        return HistoryEntry(
            id=row.id,
            type=HistoryEntryType.MATCH,
            timestamp=row.timestamp,
            event_name=row.event_name,
            event_id=row.event_id,
            cluster_name=row.cluster_name,
            cluster_id=row.cluster_id,
            opponent_names=[display_name for _, display_name in opponents],
            opponent_ids=[participant.player_id for participant, _ in opponents],
            result=result,
            elo_change=getattr(row, 'elo_change', None),
            placement=getattr(row, 'placement', None),
            match_format=getattr(row, 'match_format', None)
        )
    
    def _build_match_entry_from_participants(self, row, participants: List[ParticipantData]) -> HistoryEntry:
        """Build a HistoryEntry for a match row with ParticipantData objects"""
        # Find the current player and opponents from ParticipantData
        current_participant = None
        opponents = []
        
        for p_data in participants:
            # For player-specific history, match by placement
            if hasattr(row, 'placement') and row.placement is not None and row.placement == p_data.placement:
                current_participant = p_data
            else:
                opponents.append(p_data)
        
        # Determine result from placement or elo_change (no draws)
        result = "loss"  # Default to loss
        if hasattr(row, 'placement') and row.placement:
            result = "win" if row.placement == 1 else "loss"
        elif hasattr(row, 'elo_change') and row.elo_change:
            result = "win" if row.elo_change > 0 else "loss"
        
        return HistoryEntry(
            id=row.id,
            type=HistoryEntryType.MATCH,
            timestamp=row.timestamp,
            event_name=row.event_name,
            event_id=row.event_id,
            cluster_name=row.cluster_name,
            cluster_id=row.cluster_id,
            opponent_names=[p.display_name for p in opponents],
            opponent_ids=[p.player_id for p in opponents],
            result=result,
            elo_change=getattr(row, 'elo_change', None),
            placement=getattr(row, 'placement', None),
            match_format=getattr(row, 'match_format', None)
        )
    
    def _build_match_entry_batch(self, row, participants: List) -> HistoryEntry:
        """Build a HistoryEntry for a match row with preloaded participant information (no DB query)"""
        # Find the current player and opponents from preloaded participants
        current_participant = None
        opponents = []
        
        for participant, display_name in participants:
            if hasattr(row, 'placement') and row.placement == participant.placement:
                current_participant = participant
            else:
                opponents.append((participant, display_name))
        
        # Determine result from placement or elo_change (no draws)
        result = "loss"  # Default to loss
        if hasattr(row, 'placement') and row.placement:
            result = "win" if row.placement == 1 else "loss"
        elif hasattr(row, 'elo_change') and row.elo_change:
            result = "win" if row.elo_change > 0 else "loss"
        
        return HistoryEntry(
            id=row.id,
            type=HistoryEntryType.MATCH,
            timestamp=row.timestamp,
            event_name=row.event_name,
            event_id=row.event_id,
            cluster_name=row.cluster_name,
            cluster_id=row.cluster_id,
            opponent_names=[display_name for _, display_name in opponents],
            opponent_ids=[participant.player_id for participant, _ in opponents],
            result=result,
            elo_change=getattr(row, 'elo_change', None),
            placement=getattr(row, 'placement', None),
            match_format=getattr(row, 'match_format', None)
        )
    
    def _build_leaderboard_entry(self, row) -> HistoryEntry:
        """Build a HistoryEntry for a leaderboard score row"""
        return HistoryEntry(
            id=row.id,
            type=HistoryEntryType.LEADERBOARD,
            timestamp=row.timestamp,
            event_name=row.event_name,
            event_id=row.event_id,
            cluster_name=row.cluster_name,
            cluster_id=row.cluster_id,
            score=getattr(row, 'score', None),
            score_direction=getattr(row, 'score_direction', None)
        )