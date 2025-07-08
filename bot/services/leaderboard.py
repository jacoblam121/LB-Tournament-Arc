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
from bot.utils.ranking import RankingUtility
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
        # Input validation using shared utility
        if not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        if not isinstance(page_size, int) or page_size < 1 or page_size > 50:
            raise ValueError("page_size must be between 1 and 50")
        if not RankingUtility.validate_leaderboard_type(leaderboard_type):
            raise ValueError("leaderboard_type must be 'overall', 'cluster', or 'event'")
        if not RankingUtility.validate_sort_by(sort_by):
            raise ValueError(f"Invalid sort_by value: {sort_by}")
        
        # Check cache first
        cache_key = f"leaderboard:{leaderboard_type}:{sort_by}:{cluster_name}:{event_name}:{page}:{page_size}:{include_ghosts}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Cleanup cache periodically
        self._cleanup_cache()
        async with self.get_session() as session:
            # Special handling for cluster leaderboards to use EloHierarchyCalculator
            if leaderboard_type == "cluster":
                return await self._get_cluster_leaderboard_page(
                    session, cluster_name, page, page_size, include_ghosts
                )
            
            # Use CTE pattern for overall and event leaderboards
            ranking_cte = RankingUtility.create_player_ranking_cte(
                sort_by=sort_by,
                include_ghosts=include_ghosts,
                leaderboard_type=leaderboard_type,
                cluster_name=cluster_name,
                event_name=event_name
            )
            
            # Count total for pagination
            count_query = select(func.count()).select_from(ranking_cte)
            total_count = await session.scalar(count_query)
            
            # Apply pagination to CTE query
            offset = (page - 1) * page_size
            paginated_query = select(ranking_cte).limit(page_size).offset(offset)
            
            # Execute and map to DTOs
            result = await session.execute(paginated_query)
            entries = []
            for row in result:
                # Better error handling for NULL values
                raw_elo = row.overall_raw_elo
                if raw_elo is None:
                    logger.warning(f"Player ID {row.player_id} ({row.display_name}) has NULL overall_raw_elo. Defaulting to 1000.")
                    raw_elo = 1000
                
                scoring_elo = row.overall_scoring_elo
                if scoring_elo is None:
                    logger.warning(f"Player ID {row.player_id} ({row.display_name}) has NULL overall_scoring_elo. Defaulting to 1000.")
                    scoring_elo = 1000
                
                entry = LeaderboardEntry(
                    rank=row.rank,
                    player_id=row.player_id,
                    display_name=row.display_name + (" (Left Server)" if getattr(row, 'is_ghost', False) else ""),
                    final_score=row.final_score or 0,
                    overall_scoring_elo=scoring_elo,
                    overall_raw_elo=raw_elo,
                    shard_bonus=getattr(row, 'shard_bonus', 0) or 0,
                    shop_bonus=getattr(row, 'shop_bonus', 0) or 0,
                    is_ghost=getattr(row, 'is_ghost', False)
                )
                entries.append(entry)
            
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
    
    async def _get_cluster_leaderboard_page(
        self, session, cluster_name: str, page: int, page_size: int, include_ghosts: bool
    ) -> LeaderboardPage:
        """Get cluster leaderboard page using EloHierarchyCalculator for correct prestige weighting."""
        from bot.operations.elo_hierarchy import EloHierarchyCalculator
        
        # Get cluster ID
        cluster_query = select(Cluster.id).where(Cluster.name == cluster_name)
        cluster_result = await session.execute(cluster_query)
        cluster_id = cluster_result.scalar_one_or_none()
        
        if cluster_id is None:
            # Return empty leaderboard for non-existent cluster
            return LeaderboardPage(
                entries=[],
                current_page=page,
                total_pages=1,
                total_players=0,
                sort_by="raw_elo",
                leaderboard_type="cluster",
                cluster_name=cluster_name,
                event_name=None
            )
        
        # Get all players who have played in this cluster
        # Use safe attribute access for is_ghost since column may not exist
        is_ghost_expr = getattr(Player, 'is_ghost', case((Player.id.isnot(None), False), else_=False)).label('is_ghost')
        
        players_query = (
            select(Player.id, Player.discord_id, Player.display_name, is_ghost_expr)
            .join(PlayerEventStats, Player.id == PlayerEventStats.player_id)
            .join(Event, PlayerEventStats.event_id == Event.id)
            .where(Event.cluster_id == cluster_id)
            .distinct()
        )
        
        if not include_ghosts:
            # Use the safe expression for filtering as well
            ghost_filter = getattr(Player, 'is_ghost', case((Player.id.isnot(None), False), else_=False))
            players_query = players_query.where(ghost_filter == False)
        
        players_result = await session.execute(players_query)
        players = players_result.all()
        
        # Calculate cluster elos for all players using EloHierarchyCalculator
        calculator = EloHierarchyCalculator(session)
        player_entries = []
        
        for player in players:
            cluster_elos = await calculator.calculate_cluster_elo(player.id, cluster_id)
            cluster_elo = cluster_elos.get(cluster_id, 1000)
            
            player_entries.append({
                'player_id': player.id,
                'discord_id': player.discord_id,
                'display_name': player.display_name,
                'raw_elo': cluster_elo,
                'is_ghost': getattr(player, 'is_ghost', False)  # Safe access with False default
            })
        
        # Sort by raw elo descending
        player_entries.sort(key=lambda x: x['raw_elo'], reverse=True)
        
        # Apply pagination
        total_players = len(player_entries)
        total_pages = (total_players + page_size - 1) // page_size if total_players > 0 else 1
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_entries = player_entries[start_idx:end_idx]
        
        # Convert to LeaderboardEntry objects
        entries = []
        for rank, player_data in enumerate(paginated_entries, start=start_idx + 1):
            entry = LeaderboardEntry(
                rank=rank,
                player_id=player_data['player_id'],
                display_name=player_data['display_name'] + (" (Left Server)" if player_data['is_ghost'] else ""),
                final_score=0,  # Not used for cluster leaderboards
                overall_scoring_elo=player_data['raw_elo'],  # Use raw elo for display
                overall_raw_elo=player_data['raw_elo'],
                shard_bonus=0,  # Not used for cluster leaderboards
                shop_bonus=0,   # Not used for cluster leaderboards
                is_ghost=player_data['is_ghost']
            )
            entries.append(entry)
        
        return LeaderboardPage(
            entries=entries,
            current_page=page,
            total_pages=total_pages,
            total_players=total_players,
            sort_by="raw_elo",
            leaderboard_type="cluster",
            cluster_name=cluster_name,
            event_name=None
        )
    
    # REMOVED: _build_ranking_query method - replaced with RankingUtility.create_player_ranking_cte()
    # for Phase 2.3 Implementation Coordination consistency
    
    def clear_cache(self):
        """Clears the entire leaderboard cache."""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Leaderboard cache cleared.")
    
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
        """Get a specific player's rank efficiently using discord_id and CTE pattern."""
        async with self.get_session() as session:
            # Use CTE pattern for consistent ranking (Phase 2.3 coordination)
            ranking_cte = RankingUtility.create_player_ranking_cte(
                sort_by=sort_by,
                include_ghosts=True,  # Include all players for rank calculation
                leaderboard_type="overall"
            )
            
            # Filter for specific player by discord_id
            query = select(ranking_cte.c.rank).where(
                ranking_cte.c.discord_id == discord_id
            )
            
            return await session.scalar(query)