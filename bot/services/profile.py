"""
Profile service for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides efficient data aggregation for player profiles with caching and optimized queries.
"""

from typing import Optional, List, Dict
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from bot.services.base import BaseService
from bot.services.rate_limiter import rate_limit
from bot.data_models.profile import ProfileData, ClusterStats, MatchRecord
from bot.database.models import Player, PlayerEventStats, EloHistory, TicketLedger, Cluster, Event
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class PlayerNotFoundError(Exception):
    """Raised when player doesn't exist in database."""
    pass


class ProfileService(BaseService):
    """Service for aggregating player profile data with efficient queries and caching."""
    
    def __init__(self, session_factory, config_service):
        super().__init__(session_factory)
        self.config_service = config_service
        # TTL cache with size limits to prevent memory leaks
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_max_size = 1000
    
    async def get_profile_data(self, user_id: int) -> ProfileData:
        """Fetch complete profile data with efficient queries and caching."""
        # Check cache first
        cache_key = f"profile:{user_id}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Cleanup cache periodically
        self._cleanup_cache()
        
        async with self.get_session() as session:
            # Main player query with current stats and ranking
            player_query = select(
                Player,
                func.rank().over(order_by=Player.final_score.desc()).label('server_rank'),
                func.count(Player.id).over().label('total_players')
            ).where(Player.discord_id == user_id)
            
            result = await session.execute(player_query)
            player_row = result.first()
            
            if not player_row:
                raise PlayerNotFoundError(f"Player {user_id} not found")
            
            player, server_rank, total_players = player_row
            
            # Check if player has left server (ghost status will be determined at command layer)
            # Service layer should not access Discord API per architectural principles
            
            # Fetch cluster stats with efficient JOIN
            cluster_stats = await self._fetch_cluster_stats(session, player.id)
            
            # Fetch match history
            recent_matches = await self._fetch_recent_matches(session, player.id)
            
            # Calculate match statistics using Player model legacy fields
            match_stats = {
                'total': player.matches_played,
                'wins': player.wins,
                'losses': player.losses,
                'draws': player.draws,
                'win_rate': player.win_rate / 100.0,  # Convert percentage to decimal
                'streak': self._calculate_current_streak(player)
            }
            
            # Get current ticket balance
            ticket_balance = await self._get_ticket_balance(session, player.id)
            
            # Build ProfileData with actual database values
            profile_data = ProfileData(
                player_id=player.id,
                display_name=player.display_name,
                is_ghost=getattr(player, 'is_ghost', False),  # Handle case where field might not exist
                final_score=player.final_score or 0,
                overall_scoring_elo=player.overall_scoring_elo or 1000,
                overall_raw_elo=player.overall_raw_elo or 1000,
                server_rank=server_rank,
                total_players=total_players,
                ticket_balance=ticket_balance,
                shard_bonus=player.shard_bonus or 0,
                shop_bonus=player.shop_bonus or 0,
                total_matches=match_stats['total'],
                wins=match_stats['wins'],
                losses=match_stats['losses'],
                draws=match_stats['draws'],
                win_rate=match_stats['win_rate'],
                current_streak=match_stats['streak'],
                top_clusters=cluster_stats[:3],
                bottom_clusters=cluster_stats[-3:] if len(cluster_stats) > 3 else [],
                all_clusters=cluster_stats,
                recent_matches=recent_matches,
                profile_color=getattr(player, 'profile_color', None)
            )
            
            # Cache the result
            self._cache[cache_key] = profile_data
            self._cache_timestamps[cache_key] = time.time()
            
            return profile_data
    
    async def _fetch_cluster_stats(self, session: AsyncSession, player_id: int) -> List[ClusterStats]:
        """Fetch cluster statistics efficiently, including clusters with no player activity."""
        # Simplified approach: get all clusters first, then get player stats separately
        
        # Get all active clusters
        clusters_query = select(Cluster.id, Cluster.name).where(Cluster.is_active == True)
        clusters_result = await session.execute(clusters_query)
        all_clusters = [(row.id, row.name) for row in clusters_result]
        
        # Get player's cluster stats where they exist
        stats_query = select(
            Cluster.id,
            PlayerEventStats.scoring_elo,
            PlayerEventStats.raw_elo,
            func.count().label('matches')
        ).select_from(PlayerEventStats).join(
            Event, PlayerEventStats.event_id == Event.id
        ).join(
            Cluster, Event.cluster_id == Cluster.id
        ).where(
            PlayerEventStats.player_id == player_id
        ).group_by(
            Cluster.id, PlayerEventStats.scoring_elo, PlayerEventStats.raw_elo
        )
        
        stats_result = await session.execute(stats_query)
        player_stats = {
            row.id: {
                'scoring_elo': row.scoring_elo,
                'raw_elo': row.raw_elo,
                'matches': row.matches
            }
            for row in stats_result
        }
        
        threshold = self.config_service.get('elo.scoring_elo_threshold', 1000)
        
        # Combine clusters with player stats, using defaults for clusters without stats
        cluster_stats = []
        for cluster_id, cluster_name in all_clusters:
            stats = player_stats.get(cluster_id, {})
            scoring_elo = stats.get('scoring_elo', 1000)
            raw_elo = stats.get('raw_elo', 1000)
            matches = stats.get('matches', 0)
            
            cluster_stats.append(ClusterStats(
                cluster_name=cluster_name,
                cluster_id=cluster_id,
                scoring_elo=scoring_elo,
                raw_elo=raw_elo,
                matches_played=matches,
                rank_in_cluster=1,  # Simplified rank - would need separate query for accurate ranking
                is_below_threshold=raw_elo < threshold
            ))
        
        # Sort by scoring elo descending
        cluster_stats.sort(key=lambda x: x.scoring_elo, reverse=True)
        
        return cluster_stats
    
    async def _fetch_recent_matches(self, session: AsyncSession, player_id: int, limit: int = 5) -> List[MatchRecord]:
        """Fetch recent match history efficiently."""
        
        # Query recent match history
        query = select(
            EloHistory.match_id,
            EloHistory.elo_change,
            EloHistory.recorded_at,
            Event.name.label('event_name'),
            # Determine result based on elo change (simplified)
            case(
                (EloHistory.elo_change > 0, 'win'),
                (EloHistory.elo_change < 0, 'loss'),
                else_='draw'
            ).label('result')
        ).select_from(EloHistory).join(
            Event, EloHistory.event_id == Event.id
        ).where(
            EloHistory.player_id == player_id
        ).order_by(
            EloHistory.recorded_at.desc()
        ).limit(limit)
        
        result = await session.execute(query)
        
        return [
            MatchRecord(
                match_id=row.match_id or 0,  # Handle null match_id for legacy records
                opponent_name="Unknown",  # TODO: Fetch from match participants table
                opponent_id=0,           # TODO: Fetch from match participants table
                result=row.result,
                elo_change=row.elo_change,
                event_name=row.event_name,
                played_at=row.recorded_at
            )
            for row in result
        ]
    
    def _calculate_current_streak(self, player: Player) -> Optional[str]:
        """Calculate current streak from Player model with W/L prefix formatting."""
        # Use the current_streak field from Player model if available
        if hasattr(player, 'current_streak') and player.current_streak is not None:
            streak_value = player.current_streak
            if streak_value > 0:
                return f"W{streak_value}"  # Win streak: W3, W1, etc.
            elif streak_value < 0:
                return f"L{abs(streak_value)}"  # Loss streak: L1, L4, etc.
            else:
                return None  # No streak (0)
        
        # Fallback: no streak data available
        return None
    
    async def _get_ticket_balance(self, session: AsyncSession, player_id: int) -> int:
        """Get current ticket balance from ledger."""
        try:
            # Sum all ticket transactions for this player
            query = select(
                func.coalesce(func.sum(TicketLedger.change_amount), 0).label('balance')
            ).where(TicketLedger.player_id == player_id)
            
            result = await session.execute(query)
            balance = result.scalar() or 0
            
            return max(0, balance)  # Ensure non-negative balance
        except Exception as e:
            logger.error(f"Error fetching ticket balance for player {player_id}: {e}")
            return 0
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self._cache_timestamps:
            return False
        return time.time() - self._cache_timestamps[cache_key] < self._cache_ttl
    
    def _cleanup_cache(self):
        """Remove expired cache entries and enforce size limits."""
        current_time = time.time()
        
        # Remove expired entries
        expired_keys = [
            key for key, timestamp in self._cache_timestamps.items()
            if current_time - timestamp >= self._cache_ttl
        ]
        
        for key in expired_keys:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        
        # Enforce size limit by removing oldest entries
        if len(self._cache) > self._cache_max_size:
            # Sort by timestamp and remove oldest entries
            sorted_items = sorted(
                self._cache_timestamps.items(),
                key=lambda x: x[1]
            )
            
            # Remove oldest entries until under size limit
            entries_to_remove = len(self._cache) - self._cache_max_size
            for key, _ in sorted_items[:entries_to_remove]:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
    
    def invalidate_cache(self, user_id: int):
        """Invalidate cache for specific user."""
        cache_key = f"profile:{user_id}"
        self._cache.pop(cache_key, None)
        self._cache_timestamps.pop(cache_key, None)