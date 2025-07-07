"""
Leaderboard service for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides efficient leaderboard queries with caching and pagination support.
"""

from typing import Optional, List
from sqlalchemy import select, func, case, and_, text
from bot.services.base import BaseService
from bot.services.rate_limiter import rate_limit
from bot.data_models.leaderboard import LeaderboardPage, LeaderboardEntry
from bot.database.models import Player, Cluster, Event, PlayerEventStats
import time
import logging

logger = logging.getLogger(__name__)


class LeaderboardService(BaseService):
    """Service for leaderboard queries and ranking with caching."""
    
    def __init__(self, session_factory, config_service):
        super().__init__(session_factory)
        self.config_service = config_service
        # TTL cache for leaderboard pages
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 180  # 3 minutes for leaderboards
        self._cache_max_size = 500
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached leaderboard data is still valid."""
        if key not in self._cache_timestamps:
            return False
        return time.time() - self._cache_timestamps[key] < self._cache_ttl
    
    def _cleanup_cache(self):
        """Remove expired entries and enforce size limits."""
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
            sorted_keys = sorted(
                self._cache_timestamps.items(),
                key=lambda x: x[1]
            )
            keys_to_remove = [key for key, _ in sorted_keys[:len(self._cache) - self._cache_max_size]]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
    
    @rate_limit("leaderboard_page", limit=5, window=60)
    async def get_page(
        self,
        leaderboard_type: str = "overall",
        sort_by: str = "final_score",
        cluster_name: Optional[str] = None,
        event_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
        include_ghosts: bool = False
    ) -> LeaderboardPage:
        """Get paginated leaderboard with efficient ranking query and caching."""
        # Input validation
        if not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        if not isinstance(page_size, int) or page_size < 1 or page_size > 50:
            raise ValueError("page_size must be between 1 and 50")
        if leaderboard_type not in ["overall", "cluster", "event"]:
            raise ValueError("leaderboard_type must be 'overall', 'cluster', or 'event'")
        if sort_by not in ["final_score", "scoring_elo", "raw_elo", "shard_bonus", "shop_bonus"]:
            raise ValueError(f"Invalid sort_by value: {sort_by}")
        
        # Check cache first
        cache_key = f"leaderboard:{leaderboard_type}:{sort_by}:{cluster_name}:{event_name}:{page}:{page_size}:{include_ghosts}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Cleanup cache periodically
        self._cleanup_cache()
        async with self.get_session() as session:
            # Build base query with window function for ranking
            base_query = self._build_ranking_query(
                leaderboard_type, sort_by, cluster_name, event_name, include_ghosts
            )
            
            # Count total for pagination
            count_query = select(func.count()).select_from(base_query.subquery())
            total_count = await session.scalar(count_query)
            
            # Apply pagination
            offset = (page - 1) * page_size
            paginated_query = base_query.limit(page_size).offset(offset)
            
            # Execute and map to DTOs
            result = await session.execute(paginated_query)
            entries = [
                LeaderboardEntry(
                    rank=row.rank,
                    player_id=row.player_id,
                    display_name=row.display_name + (" (Left Server)" if getattr(row, 'is_ghost', False) else ""),
                    final_score=row.final_score or 0,
                    overall_scoring_elo=row.overall_scoring_elo or 1000,
                    overall_raw_elo=row.overall_raw_elo or 1000,
                    shard_bonus=getattr(row, 'shard_bonus', 0) or 0,
                    shop_bonus=getattr(row, 'shop_bonus', 0) or 0,
                    is_ghost=getattr(row, 'is_ghost', False)
                )
                for row in result
            ]
            
            leaderboard_page = LeaderboardPage(
                entries=entries,
                current_page=page,
                total_pages=(total_count + page_size - 1) // page_size if total_count > 0 else 1,
                total_players=total_count,
                sort_by=sort_by,
                leaderboard_type=leaderboard_type,
                cluster_name=cluster_name,
                event_name=event_name
            )
            
            # Cache the result
            self._cache[cache_key] = leaderboard_page
            self._cache_timestamps[cache_key] = time.time()
            
            return leaderboard_page
    
    def _build_ranking_query(
        self,
        leaderboard_type: str,
        sort_by: str,
        cluster_name: Optional[str],
        event_name: Optional[str],
        include_ghosts: bool
    ):
        """Build efficient ranking query with window functions."""
        # Map sort columns
        sort_columns = {
            'final_score': Player.final_score,
            'scoring_elo': Player.overall_scoring_elo,
            'raw_elo': Player.overall_raw_elo,
            'shard_bonus': getattr(Player, 'shard_bonus', Player.final_score),  # Fallback if column doesn't exist
            'shop_bonus': getattr(Player, 'shop_bonus', Player.final_score)     # Fallback if column doesn't exist
        }
        
        sort_column = sort_columns.get(sort_by, Player.final_score)
        
        # Base query with ranking
        query = select(
            Player.id.label('player_id'),
            Player.display_name,
            Player.final_score,
            Player.overall_scoring_elo,
            Player.overall_raw_elo,
            getattr(Player, 'shard_bonus', Player.final_score).label('shard_bonus'),
            getattr(Player, 'shop_bonus', Player.final_score).label('shop_bonus'),
            getattr(Player, 'is_ghost', case((Player.id.isnot(None), False), else_=False)).label('is_ghost'),
            func.rank().over(order_by=sort_column.desc()).label('rank')
        )
        
        # Apply filters based on leaderboard type
        if leaderboard_type == "cluster" and cluster_name:
            # Join with cluster-specific data
            query = query.join(
                PlayerEventStats, Player.id == PlayerEventStats.player_id
            ).join(
                Event, PlayerEventStats.event_id == Event.id
            ).join(
                Cluster, Event.cluster_id == Cluster.id
            ).where(Cluster.name == cluster_name)
            
            # Use cluster-specific scoring for ranking
            query = query.with_only_columns(
                Player.id.label('player_id'),
                Player.display_name,
                Player.final_score,
                PlayerEventStats.scoring_elo.label('overall_scoring_elo'),
                PlayerEventStats.raw_elo.label('overall_raw_elo'),
                getattr(Player, 'shard_bonus', Player.final_score).label('shard_bonus'),
                getattr(Player, 'shop_bonus', Player.final_score).label('shop_bonus'),
                getattr(Player, 'is_ghost', case((Player.id.isnot(None), False), else_=False)).label('is_ghost'),
                func.rank().over(order_by=PlayerEventStats.raw_elo.desc()).label('rank')
            )
            
        elif leaderboard_type == "event" and event_name:
            # Join with event-specific data
            query = query.join(
                PlayerEventStats, Player.id == PlayerEventStats.player_id
            ).join(
                Event, PlayerEventStats.event_id == Event.id
            ).where(Event.name == event_name)
            
            # Use event-specific scoring for ranking
            query = query.with_only_columns(
                Player.id.label('player_id'),
                Player.display_name,
                Player.final_score,
                PlayerEventStats.scoring_elo.label('overall_scoring_elo'),
                PlayerEventStats.raw_elo.label('overall_raw_elo'),
                getattr(Player, 'shard_bonus', Player.final_score).label('shard_bonus'),
                getattr(Player, 'shop_bonus', Player.final_score).label('shop_bonus'),
                getattr(Player, 'is_ghost', case((Player.id.isnot(None), False), else_=False)).label('is_ghost'),
                func.rank().over(order_by=PlayerEventStats.raw_elo.desc()).label('rank')
            )
        
        # Filter ghosts unless specifically included
        if not include_ghosts:
            # Use getattr to handle case where is_ghost column might not exist
            if hasattr(Player, 'is_ghost'):
                query = query.where(Player.is_ghost == False)
        
        return query
    
    async def get_cluster_names(self) -> List[str]:
        """Get list of cluster names for autocomplete."""
        async with self.get_session() as session:
            query = select(Cluster.name).where(Cluster.is_active == True).order_by(Cluster.name)
            result = await session.execute(query)
            return [row[0] for row in result]
    
    async def get_event_names(self, cluster_name: Optional[str] = None) -> List[str]:
        """Get list of event names for autocomplete."""
        async with self.get_session() as session:
            query = select(Event.name).where(Event.is_active == True)
            
            if cluster_name:
                query = query.join(Cluster).where(Cluster.name == cluster_name)
            
            query = query.order_by(Event.name)
            result = await session.execute(query)
            return [row[0] for row in result]
    
    async def get_player_rank(
        self,
        discord_id: int,
        sort_by: str = "final_score"
    ) -> Optional[int]:
        """Get a specific player's rank efficiently using discord_id."""
        async with self.get_session() as session:
            # First get the player's internal ID from discord_id
            player_query = select(Player.id).where(Player.discord_id == discord_id)
            player_id = await session.scalar(player_query)
            
            if not player_id:
                return None
            
            # Use CTE for rank calculation
            rank_cte = self._build_ranking_query(
                "overall", sort_by, None, None, True
            ).cte('ranks')
            
            query = select(rank_cte.c.rank).where(
                rank_cte.c.player_id == player_id
            )
            
            return await session.scalar(query)