"""
Z-Score Statistical Conversion Service for Phase 3.3

This service handles the conversion of raw leaderboard scores to standardized Elo ratings
using Z-score normalization. It provides efficient background processing with Redis-based
locking for race condition prevention and database-level aggregation for performance.

Key Features:
- Database-level Z-score calculation using SQL aggregation
- Redis-based distributed locking with automatic expiration
- Background processing to avoid blocking score submission
- Configurable base Elo and sigma scaling parameters
- Support for both HIGH and LOW score directions
"""

import asyncio
import logging
from typing import Dict, Optional
from sqlalchemy import select, func, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from bot.services.base import BaseService
from bot.database.models import Event, LeaderboardScore, PlayerEventStats, ScoreDirection, ScoreType
from bot.utils.redis_utils import RedisUtils
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

class LeaderboardScoringService(BaseService):
    """Service for Z-score statistical conversion and Elo calculation."""
    
    def __init__(self, session_factory, config_service, on_calculation_start=None, on_calculation_complete=None):
        super().__init__(session_factory)
        self.config_service = config_service
        self.base_elo = config_service.get('elo.leaderboard_base_elo', 1000)
        self.elo_per_sigma = config_service.get('leaderboard_system.elo_per_sigma', 200)
        self.redis_client = None
        self.redis_enabled = REDIS_AVAILABLE
        # Optional monitoring callbacks for background task observability
        self.on_calculation_start = on_calculation_start
        self.on_calculation_complete = on_calculation_complete
        if not self.redis_enabled:
            logger.warning("Redis library not installed. Distributed locking disabled for Z-score calculations.")
    
    async def _get_redis_client(self):
        """Get Redis client for distributed locking. Returns None if Redis is unavailable."""
        if not self.redis_enabled:
            return None
            
        if self.redis_client is None:
            try:
                # Use centralized Redis utilities
                self.redis_client = await RedisUtils.create_redis_client()
                if self.redis_client is None:
                    logger.warning("No secure Redis URL configured. Z-score calculations will run without locking.")
                    self.redis_enabled = False
                    return None
                    
                logger.info("Successfully connected to Redis for distributed locking.")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}. Z-score calculations will run without locking.")
                self.redis_client = None
                self.redis_enabled = False
        return self.redis_client
    
    async def calculate_all_time_elos_background(self, event_id: int):
        """
        Background task for efficient Elo calculation using database aggregation.
        
        This method uses Redis locking to prevent duplicate calculations and employs
        database-level aggregation for optimal performance.
        """
        redis_client = await self._get_redis_client()
        
        # If Redis is available, use distributed locking
        if redis_client:
            lock_key = f"elo_calculation_lock:{event_id}"
            
            # Try to acquire lock with 30-second expiry for debouncing
            is_locked = await redis_client.set(lock_key, "1", ex=30, nx=True)
            
            if not is_locked:
                logger.info(f"Elo calculation for event {event_id} throttled - lock exists")
                return
        else:
            # Redis not available - proceed without locking (risk of race conditions in multi-instance setup)
            logger.debug(f"Running Elo calculation for event {event_id} without Redis locking")
        
        # Optional monitoring hook - calculation start
        if self.on_calculation_start:
            try:
                self.on_calculation_start(event_id)
            except Exception as e:
                logger.warning(f"Monitoring callback on_calculation_start failed: {e}")
        
        start_time = None
        success = False
        try:
            import time
            start_time = time.monotonic()
            
            async with self.get_session() as session:
                async with session.begin():
                    
                    # Ultra-efficient database-level calculation
                    await self._execute_zscore_calculation(session, event_id)
                    
                    logger.info(f"Completed background Elo calculation for event {event_id}")
                    success = True
        
        except Exception as e:
            # Log error but don't re-raise in background task to prevent event loop instability
            logger.error(f"Background Elo calculation failed for event {event_id}: {e}", exc_info=True)
            # Background tasks should fail gracefully without affecting main application flow
        
        # Optional monitoring hook - calculation complete
        if self.on_calculation_complete:
            try:
                duration = time.monotonic() - start_time if start_time else 0
                self.on_calculation_complete(event_id, duration, success)
            except Exception as e:
                logger.warning(f"Monitoring callback on_calculation_complete failed: {e}")
        
        # Lock expires naturally for debouncing - no manual deletion needed
    
    async def _execute_zscore_calculation(self, session: AsyncSession, event_id: int):
        """Execute the Z-score calculation using database-level aggregation."""
        
        # Get database dialect for cross-database compatibility
        dialect = session.bind.dialect.name
        
        if dialect == 'postgresql':
            # PostgreSQL-specific implementation with UPSERT pattern
            update_query = text("""
                WITH stats AS (
                    SELECT 
                        AVG(score) as mean_score,
                        STDDEV_POP(score) as std_dev,
                        COUNT(*) as player_count
                    FROM leaderboard_scores 
                    WHERE event_id = :event_id AND score_type = 'all_time'
                ),
                z_scores AS (
                    SELECT 
                        ls.player_id,
                        ls.event_id,
                        CASE 
                            WHEN s.std_dev > 0 THEN
                                CASE 
                                    WHEN e.score_direction = 'HIGH' THEN (ls.score - s.mean_score) / s.std_dev
                                    ELSE (s.mean_score - ls.score) / s.std_dev
                                END
                            ELSE 0
                        END as z_score
                    FROM leaderboard_scores ls
                    CROSS JOIN stats s
                    JOIN events e ON ls.event_id = e.id
                    WHERE ls.event_id = :event_id AND ls.score_type = 'all_time'
                )
                INSERT INTO player_event_stats (player_id, event_id, all_time_leaderboard_elo)
                SELECT 
                    z.player_id,
                    z.event_id,
                    :base_elo + (z.z_score * :elo_per_sigma)
                FROM z_scores z
                ON CONFLICT (player_id, event_id) 
                DO UPDATE SET 
                    all_time_leaderboard_elo = EXCLUDED.all_time_leaderboard_elo
            """)
        else:
            # SQLite fallback with UPSERT pattern
            update_query = text("""
                INSERT INTO player_event_stats (player_id, event_id, all_time_leaderboard_elo)
                SELECT 
                    ls.player_id,
                    ls.event_id,
                    :base_elo + (
                        CASE 
                            WHEN stats.std_dev > 0 THEN
                                CASE 
                                    WHEN e.score_direction = 'HIGH' THEN 
                                        ((ls.score - stats.mean_score) / stats.std_dev) * :elo_per_sigma
                                    ELSE 
                                        ((stats.mean_score - ls.score) / stats.std_dev) * :elo_per_sigma
                                END
                            ELSE 0
                        END
                    )
                FROM leaderboard_scores ls
                JOIN events e ON ls.event_id = e.id
                CROSS JOIN (
                    SELECT 
                        AVG(score) as mean_score,
                        CASE 
                            WHEN COUNT(score) > 1 THEN SQRT(AVG(score * score) - AVG(score) * AVG(score))
                            ELSE 0.0
                        END as std_dev
                    FROM leaderboard_scores 
                    WHERE event_id = :event_id AND score_type = 'all_time'
                ) stats
                WHERE ls.event_id = :event_id 
                AND ls.score_type = 'all_time'
                ON CONFLICT (player_id, event_id) 
                DO UPDATE SET 
                    all_time_leaderboard_elo = excluded.all_time_leaderboard_elo
            """)
        
        await session.execute(update_query, {
            'event_id': event_id,
            'base_elo': self.base_elo,
            'elo_per_sigma': self.elo_per_sigma
        })
    
    
    def _calculate_z_score(self, score: float, mean: float, std_dev: float, direction: ScoreDirection) -> float:
        """Convert raw score to Z-score based on direction."""
        if std_dev == 0:
            return 0.0
        
        if direction == ScoreDirection.HIGH:
            return (score - mean) / std_dev
        else:  # ScoreDirection.LOW - invert so better times get positive Z-scores
            return (mean - score) / std_dev
    
    def _z_score_to_elo(self, z_score: float) -> int:
        """Convert Z-score to Elo rating."""
        return round(self.base_elo + (z_score * self.elo_per_sigma))
    
    async def get_event_statistics(self, event_id: int) -> Optional[Dict]:
        """Get statistical summary for an event."""
        async with self.get_session() as session:
            stats_query = select(
                func.count(LeaderboardScore.id).label('total_scores'),
                func.avg(LeaderboardScore.score).label('mean_score'),
                func.min(LeaderboardScore.score).label('min_score'),
                func.max(LeaderboardScore.score).label('max_score'),
                func.stddev_pop(LeaderboardScore.score).label('std_dev')
            ).where(
                LeaderboardScore.event_id == event_id,
                LeaderboardScore.score_type == ScoreType.ALL_TIME
            )
            
            result = await session.execute(stats_query)
            stats = result.one_or_none()
            
            if not stats or stats.total_scores == 0:
                return None
            
            return {
                'total_scores': stats.total_scores,
                'mean_score': float(stats.mean_score) if stats.mean_score else 0,
                'min_score': float(stats.min_score) if stats.min_score else 0,
                'max_score': float(stats.max_score) if stats.max_score else 0,
                'std_dev': float(stats.std_dev) if stats.std_dev else 0
            }
    
    async def close(self):
        """Clean up Redis connection."""
        if self.redis_client and self.redis_enabled:
            await self.redis_client.close()