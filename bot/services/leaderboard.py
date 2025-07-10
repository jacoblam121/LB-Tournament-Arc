"""
Leaderboard service for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides efficient leaderboard queries with caching and pagination support.
"""

from typing import Optional, List, TYPE_CHECKING
import asyncio
import time
import logging

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from bot.services.base import BaseService
from bot.data_models.leaderboard import LeaderboardPage, LeaderboardEntry
from bot.database.models import Player, Cluster, Event, PlayerEventStats, ScoreDirection
from bot.utils.ranking import RankingUtility

logger = logging.getLogger(__name__)


class LeaderboardService(BaseService):
    """Service for leaderboard queries and ranking with caching."""
    
    def __init__(self, session_factory, config_service, scoring_service=None):
        super().__init__(session_factory)
        self.config_service = config_service
        self.scoring_service = scoring_service  # Optional dependency injection
        # TTL cache for leaderboard pages
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 180  # 3 minutes for leaderboards
        self._cache_max_size = 500
        self._cache_lock = asyncio.Lock()  # Thread safety for cache operations
        # Background task tracking for proper lifecycle management
        self._background_tasks: set = set()
    
    async def _is_cache_valid(self, key: str) -> bool:
        """Check if cached leaderboard data is still valid."""
        async with self._cache_lock:
            if key not in self._cache_timestamps:
                return False
            return time.time() - self._cache_timestamps[key] < self._cache_ttl
    
    async def _cleanup_cache(self):
        """Remove expired entries and enforce size limits."""
        async with self._cache_lock:
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
        if await self._is_cache_valid(cache_key):
            async with self._cache_lock:
                return self._cache[cache_key]
        
        # Cleanup cache periodically
        await self._cleanup_cache()
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
            async with self._cache_lock:
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
    
    async def clear_cache(self):
        """Clears the entire leaderboard cache."""
        async with self._cache_lock:
            self._cache.clear()
            self._cache_timestamps.clear()
        logger.info("Leaderboard cache cleared.")
    
    async def cleanup(self):
        """Cleanup background tasks and resources for graceful shutdown."""
        if self._background_tasks:
            logger.info(f"Waiting for {len(self._background_tasks)} background tasks to complete...")
            # Cancel all pending background tasks
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for all tasks to complete or be cancelled
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            
            self._background_tasks.clear()
            logger.info("All background tasks cleaned up.")
    
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
    
    async def submit_score(self, discord_id: int, display_name: str, event_id: int, raw_score: float, guild_id: int, max_retries: int = None) -> dict:
        """Submit score with retry logic for race conditions and transaction atomicity."""
        from sqlalchemy.exc import IntegrityError
        from bot.utils.leaderboard_exceptions import TransactionError, DatabaseError
        
        if max_retries is None:
            max_retries = self.config_service.get('leaderboard_system.score_submission_max_retries', 3)
        
        for attempt in range(max_retries):
            try:
                result = await self._submit_score_attempt(discord_id, display_name, event_id, raw_score, guild_id)
                
                # Trigger background Z-score calculation AFTER transaction commits
                if result.get('is_personal_best') and self.scoring_service is not None:
                    # Small delay to ensure database consistency across replicas
                    replica_delay = self.config_service.get('leaderboard_system.replica_consistency_delay', 0.1)
                    await asyncio.sleep(replica_delay)
                    
                    # Create background task now that transaction is committed
                    task = asyncio.create_task(self.scoring_service.calculate_all_time_elos_background(event_id))
                    self._background_tasks.add(task)
                    # Remove task from set when it completes to prevent memory leaks
                    task.add_done_callback(self._background_tasks.discard)
                    logger.info(f"Triggered background Z-score calculation for event {event_id} after PB submission")
                
                return result
                
            except IntegrityError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Score submission failed after {max_retries} attempts: {e}")
                    raise TransactionError("score submission", max_retries)
                # Exponential backoff with cap at 1 second
                await asyncio.sleep(min(0.1 * (2 ** attempt), 1.0))
                logger.warning(f"Score submission retry {attempt + 1} for discord_id {discord_id}, event {event_id}")
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Database error during score submission: {e}")
                    raise DatabaseError("score submission", str(e))
    
    async def _submit_score_attempt(self, discord_id: int, display_name: str, event_id: int, raw_score: float, guild_id: int) -> dict:
        """Single attempt at score submission with database-agnostic approach and transaction atomicity."""
        from bot.database.models import Event, LeaderboardScore, ScoreType, Player
        from bot.utils.leaderboard_exceptions import InvalidEventError, DatabaseError
        
        async with self.get_session() as session:
            async with session.begin():
                
                # Get or create player within the transaction (atomicity fix)
                player_stmt = select(Player).where(Player.discord_id == discord_id)
                player = await session.scalar(player_stmt)
                
                if not player:
                    # Create new player within the same transaction
                    player = Player(
                        discord_id=discord_id,
                        username=display_name,
                        display_name=display_name
                    )
                    session.add(player)
                    await session.flush()  # Get the player.id without committing
                
                # Get event and lock for update WITH guild validation
                from bot.database.models import Cluster
                event_stmt = (
                    select(Event)
                    .join(Event.cluster)
                    .where(
                        Event.id == event_id,
                        # Allow events from clusters with matching guild_id or no guild_id (legacy support)
                        (Cluster.guild_id == guild_id) | (Cluster.guild_id.is_(None)),
                    )
                    .with_for_update()
                )
                event = await session.scalar(event_stmt)
                
                if not event or not event.score_direction:
                    raise InvalidEventError("Event")
                
                # Get previous personal best with lock (database-agnostic approach)
                pb_query = select(LeaderboardScore).where(
                    LeaderboardScore.player_id == player.id,
                    LeaderboardScore.event_id == event_id,
                    LeaderboardScore.score_type == ScoreType.ALL_TIME
                ).with_for_update()
                
                previous_pb = await session.scalar(pb_query)
                previous_best = previous_pb.score if previous_pb else None
                
                # Check if this is a personal best
                is_pb = self._is_personal_best(raw_score, previous_best, event.score_direction)
                
                if is_pb:
                    if previous_pb:
                        # Update existing personal best (database-agnostic)
                        previous_pb.score = raw_score
                        previous_pb.submitted_at = func.now()
                        session.add(previous_pb)
                    else:
                        # Insert new personal best
                        new_pb = LeaderboardScore(
                            player_id=player.id,
                            event_id=event_id,
                            score=raw_score,
                            score_type=ScoreType.ALL_TIME,
                            week_number=None,
                            submitted_at=func.now()
                        )
                        session.add(new_pb)
                    
                    # Update running statistics if it's actually a new PB
                    await self._update_running_statistics(session, event, raw_score, previous_best)
                
                # Handle weekly score - check if one exists for current week
                current_week = self._get_current_week()
                existing_weekly = await session.scalar(
                    select(LeaderboardScore).where(
                        LeaderboardScore.player_id == player.id,
                        LeaderboardScore.event_id == event_id,
                        LeaderboardScore.score_type == ScoreType.WEEKLY,
                        LeaderboardScore.week_number == current_week
                    ).with_for_update()
                )
                
                if existing_weekly:
                    # Update if new score is better
                    if self._is_personal_best(raw_score, existing_weekly.score, event.score_direction):
                        existing_weekly.score = raw_score
                        existing_weekly.submitted_at = func.now()
                else:
                    # Insert new weekly score
                    weekly_score = LeaderboardScore(
                        player_id=player.id,
                        event_id=event_id,
                        score=raw_score,
                        score_type=ScoreType.WEEKLY,
                        week_number=current_week
                    )
                    session.add(weekly_score)
                
                # Get current personal best for return
                updated_pb = await session.scalar(
                    select(LeaderboardScore).where(
                        LeaderboardScore.player_id == player.id,
                        LeaderboardScore.event_id == event_id,
                        LeaderboardScore.score_type == ScoreType.ALL_TIME
                    )
                )
                current_best = updated_pb.score if updated_pb else raw_score
                
                # Background task moved to submit_score() to run AFTER transaction commits
                
                return {
                    'is_personal_best': is_pb,
                    'personal_best': current_best,
                    'previous_best': previous_best if is_pb else None
                }
    
    def _is_personal_best(self, new_score: float, previous_best: Optional[float], direction: ScoreDirection) -> bool:
        """Check if new score is a personal best."""
        if previous_best is None:
            return True
        
        if direction == ScoreDirection.HIGH:
            return new_score > previous_best
        else:  # ScoreDirection.LOW
            return new_score < previous_best
    
    
    async def _update_running_statistics(self, session: "AsyncSession", event: Event, new_score: float, previous_best: Optional[float]):
        """Update running statistics using Welford's algorithm."""
        
        # Initialize running stats if not present
        if event.score_count is None:
            event.score_count = 0
            event.score_mean = 0.0
            event.score_m2 = 0.0
        
        # Handle replacement vs addition
        if previous_best is not None:
            # This is a replacement - first remove the old score, then add the new one
            if event.score_count > 1:
                # Downdate: remove old score's contribution
                old_count = event.score_count
                old_mean = event.score_mean
                old_m2 = event.score_m2
                
                # Remove the old score
                delta = previous_best - old_mean
                new_count_temp = old_count - 1
                
                # Guard against division by zero
                if new_count_temp == 0:
                    # Reset stats if no scores remain
                    event.score_count = 0
                    event.score_mean = 0.0
                    event.score_m2 = 0.0
                else:
                    new_mean_temp = (old_count * old_mean - previous_best) / new_count_temp
                    delta2 = previous_best - new_mean_temp
                    new_m2_temp = old_m2 - delta * delta2
                    
                    # Update with downdated values
                    event.score_count = new_count_temp
                    event.score_mean = new_mean_temp
                    # Guard against negative M2 due to floating-point errors
                    event.score_m2 = max(new_m2_temp, 0.0)
            else:
                # Only one score existed, reset stats
                event.score_count = 0
                event.score_mean = 0.0
                event.score_m2 = 0.0
        
        # Now add the new score using Welford's algorithm
        old_count = event.score_count
        old_mean = event.score_mean
        old_m2 = event.score_m2
        
        new_count = old_count + 1
        delta = new_score - old_mean
        new_mean = old_mean + delta / new_count
        delta2 = new_score - new_mean
        new_m2 = old_m2 + delta * delta2
        
        event.score_count = new_count
        event.score_mean = new_mean
        # Guard against negative M2 due to floating-point errors
        event.score_m2 = max(new_m2, 0.0)
    
    def _get_current_week(self) -> int:
        """Get current ISO year-week number to prevent yearly collisions."""
        from datetime import datetime
        iso_cal = datetime.utcnow().isocalendar()
        # Encode year and week together: YYYYWW (e.g., 202452 for week 52 of 2024)
        return iso_cal.year * 100 + iso_cal.week
    
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