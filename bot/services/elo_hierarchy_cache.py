"""
Cached wrapper for EloHierarchyCalculator - Phase 2.4 Implementation

Provides caching layer for hierarchical Elo calculations to improve performance.
"""

import time
from typing import Dict, Optional, Tuple
from bot.operations.elo_hierarchy import EloHierarchyCalculator
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


class CachedEloHierarchyService:
    """Wrapper for EloHierarchyCalculator with TTL-based caching."""
    
    def __init__(self, session_factory, config_service):
        self.session_factory = session_factory  # Store session factory instead of calculator
        self.config_service = config_service
        self._cache: Dict[int, Tuple[float, Dict]] = {}  # player_id -> (timestamp, data)
        self._cache_max_size = self.config_service.get('system.cache_size_hierarchy', 1000)
    
    async def get_hierarchy(self, player_id: int) -> Dict:
        """Get hierarchy with caching based on TTL."""
        ttl = self.config_service.get('system.cache_ttl_hierarchy', 900)  # 15 minutes default
        
        # Check cache
        if player_id in self._cache:
            timestamp, data = self._cache[player_id]
            if time.time() - timestamp < ttl:
                logger.debug(f"Cache hit for player {player_id}")
                return data
        
        # Calculate fresh
        logger.debug(f"Cache miss for player {player_id}, calculating fresh")
        try:
            async with self.session_factory() as session:
                calculator = EloHierarchyCalculator(session)
                hierarchy_data = await calculator.calculate_player_hierarchy(player_id)
        except Exception as e:
            logger.error(f"Failed to calculate hierarchy for player {player_id}: {e}", exc_info=True)
            # Return default structure to prevent cascading failures
            return {
                'cluster_elos': {},
                'overall_elo': 1000,
                'overall_raw_elo': 1000,
                'overall_scoring_elo': 1000,
                'total_clusters': 0
            }
        
        # Update cache
        self._cache[player_id] = (time.time(), hierarchy_data)
        
        # Cleanup old entries if cache too large
        if len(self._cache) > self._cache_max_size:
            self._cleanup_cache()
        
        return hierarchy_data
    
    def invalidate_user(self, player_id: int):
        """Invalidate cache for specific user."""
        if player_id in self._cache:
            logger.debug(f"Invalidating cache for player {player_id}")
            self._cache.pop(player_id, None)
    
    def invalidate_all(self):
        """Clear entire cache."""
        logger.info("Clearing entire hierarchy cache")
        self._cache.clear()
    
    async def calculate_cluster_elo(
        self, 
        player_id: int, 
        cluster_id: Optional[int] = None
    ) -> Dict[int, int]:
        """Calculate cluster Elo using prestige weighting system."""
        try:
            async with self.session_factory() as session:
                calculator = EloHierarchyCalculator(session)
                return await calculator.calculate_cluster_elo(player_id, cluster_id)
        except Exception as e:
            logger.error(f"Failed to calculate cluster elo for player {player_id}: {e}", exc_info=True)
            # Return empty dict to prevent cascading failures
            return {}
    
    def _cleanup_cache(self):
        """Remove oldest cache entries to stay within size limit."""
        # Sort by timestamp and keep newest entries
        sorted_items = sorted(self._cache.items(), key=lambda x: x[1][0], reverse=True)
        self._cache = dict(sorted_items[:self._cache_max_size])
        logger.debug(f"Cleaned hierarchy cache, kept {len(self._cache)} entries")