"""
Profile service for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides efficient data aggregation for player profiles with caching and optimized queries.
"""

from typing import Optional, List, Dict, Tuple
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from bot.services.base import BaseService
from bot.services.rate_limiter import rate_limit
from bot.data_models.profile import ProfileData, ClusterStats, MatchRecord
from bot.database.models import Player, PlayerEventStats, EloHistory, TicketLedger, Cluster, Event, MatchParticipant
from bot.constants import EloConstants, PaginationConstants
import logging
import time
from datetime import datetime, timezone

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
        self._cache_ttl = self.config_service.get('system.cache_ttl_profile', 60)  # Default 1 minute for post-match updates
        self._cache_max_size = 1000
    
    async def get_profile_data(self, user_id: int) -> ProfileData:
        """Fetch complete profile data with efficient queries and caching."""
        # Check cache first
        cache_key = f"profile:{user_id}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Cleanup cache periodically
        self._cleanup_cache()
        
        try:
            async with self.get_session() as session:
                # First, create CTE that ranks all players to fix window function scope issue
                # The previous query filtered to single user before ranking, breaking cross-server ranking
                ranking_cte = select(
                    Player.id,
                    Player.discord_id,
                    Player.display_name,
                    Player.final_score,
                    Player.overall_scoring_elo,
                    Player.overall_raw_elo,
                    Player.shard_bonus,
                    Player.shop_bonus,
                    case((Player.id.isnot(None), False), else_=False).label('is_ghost'),
                    case((Player.id.isnot(None), None), else_=None).label('profile_color'),
                    Player.matches_played,
                    Player.wins,
                    Player.losses,
                    Player.draws,
                    case((Player.matches_played > 0, (Player.wins * 100.0 / Player.matches_played)), else_=0.0).label('win_rate'),
                    Player.current_streak,
                    func.rank().over(order_by=Player.final_score.desc()).label('server_rank'),
                    func.count(Player.id).over().label('total_players')
                ).cte('ranked_players')
                
                # Then filter for specific user from the ranked results
                player_query = select(ranking_cte).where(ranking_cte.c.discord_id == user_id)
                
                result = await session.execute(player_query)
                player_row = result.first()
                
                if not player_row:
                    raise PlayerNotFoundError(f"Player {user_id} not found")
                
                # Extract values from CTE result
                player_id = player_row.id
                display_name = player_row.display_name
                final_score = player_row.final_score or 0
                overall_scoring_elo = player_row.overall_scoring_elo or EloConstants.STARTING_ELO
                overall_raw_elo = player_row.overall_raw_elo or EloConstants.STARTING_ELO
                shard_bonus = player_row.shard_bonus or 0
                shop_bonus = player_row.shop_bonus or 0
                is_ghost = player_row.is_ghost or False
                profile_color = player_row.profile_color
                matches_played = player_row.matches_played or 0
                wins = player_row.wins or 0
                losses = player_row.losses or 0
                draws = player_row.draws or 0
                win_rate = (player_row.win_rate or 0) / 100.0  # Already calculated as percentage in SQL, convert to decimal
                current_streak = player_row.current_streak
                server_rank = player_row.server_rank
                total_players = player_row.total_players
                
                # Check if player has left server (ghost status will be determined at command layer)
                # Service layer should not access Discord API per architectural principles
                
                # Fetch cluster stats with efficient JOIN
                cluster_stats = await self._fetch_cluster_stats(session, player_id)
                
                # Calculate Overall Elo using "Weighted Generalist" formula
                calculated_overall_raw_elo, calculated_overall_scoring_elo = self._calculate_overall_elo(cluster_stats)
                
                # Fetch match history
                recent_matches = await self._fetch_recent_matches(session, player_id)
                
                # Use database values for match statistics (already aggregated in Player model)
                match_stats = {
                    'total': matches_played,
                    'wins': wins,
                    'losses': losses,
                    'draws': draws,
                    'win_rate': win_rate,  # Already converted to decimal above
                    'streak': self._format_current_streak_value(current_streak)
                }
                
                # Get current ticket balance
                ticket_balance = await self._get_ticket_balance(session, player_id)
                
                # Build ProfileData with CTE-extracted values and correct rankings
                profile_data = ProfileData(
                    player_id=player_id,
                    display_name=display_name,
                    is_ghost=is_ghost,
                    final_score=final_score,  # Use actual final_score from database
                    overall_scoring_elo=overall_scoring_elo,  # Use database value (updated by match processing)
                    overall_raw_elo=overall_raw_elo,  # Use database value (updated by match processing)
                    server_rank=server_rank,  # Now correctly calculated across all players
                    total_players=total_players,  # Now correctly shows total player count
                    ticket_balance=ticket_balance,
                    shard_bonus=shard_bonus,
                    shop_bonus=shop_bonus,
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
                    profile_color=profile_color
                )
                
                # Cache the result
                self._cache[cache_key] = profile_data
                self._cache_timestamps[cache_key] = time.time()
                
                return profile_data
                
        except PlayerNotFoundError:
            # Re-raise known exceptions
            raise
        except Exception as e:
            logger.error(f"Database error fetching profile for user {user_id}: {e}")
            raise Exception("Unable to load profile data. Please try again later.")
    
    async def _fetch_cluster_stats(self, session: AsyncSession, player_id: int) -> List[ClusterStats]:
        """Fetch cluster statistics efficiently, including clusters with no player activity."""
        # Simplified approach: get all clusters first, then get player stats separately
        
        # Get all active clusters
        clusters_query = select(Cluster.id, Cluster.name).where(Cluster.is_active == True)
        clusters_result = await session.execute(clusters_query)
        all_clusters = [(row.id, row.name) for row in clusters_result]
        
        # Get cluster ranks for the player FIRST (since ClusterStats is frozen)
        cluster_ranks = await self._fetch_cluster_ranks(session, player_id)
        
        # Get player's cluster stats - get latest elo per cluster and total matches
        # First get the latest elo values per cluster
        latest_elo_query = select(
            Cluster.id,
            PlayerEventStats.raw_elo,
            PlayerEventStats.scoring_elo,
            func.row_number().over(
                partition_by=Cluster.id,
                order_by=PlayerEventStats.updated_at.desc()
            ).label('rn')
        ).select_from(PlayerEventStats).join(
            Event, PlayerEventStats.event_id == Event.id
        ).join(
            Cluster, Event.cluster_id == Cluster.id
        ).where(
            PlayerEventStats.player_id == player_id
        ).subquery()
        
        # Get match counts per cluster
        match_count_query = select(
            Cluster.id,
            func.count(PlayerEventStats.id).label('matches')
        ).select_from(PlayerEventStats).join(
            Event, PlayerEventStats.event_id == Event.id
        ).join(
            Cluster, Event.cluster_id == Cluster.id
        ).where(
            PlayerEventStats.player_id == player_id
        ).group_by(Cluster.id).subquery()
        
        # Combine latest elo with match counts
        stats_query = select(
            latest_elo_query.c.id,
            latest_elo_query.c.scoring_elo,
            latest_elo_query.c.raw_elo,
            match_count_query.c.matches
        ).select_from(latest_elo_query).join(
            match_count_query, latest_elo_query.c.id == match_count_query.c.id
        ).where(latest_elo_query.c.rn == 1)
        
        stats_result = await session.execute(stats_query)
        player_stats = {
            row.id: {
                'scoring_elo': row.scoring_elo,
                'raw_elo': row.raw_elo,
                'matches': row.matches
            }
            for row in stats_result
        }
        
        threshold = self.config_service.get('elo.raw_elo_threshold', EloConstants.STARTING_ELO)
        
        # Create ClusterStats with correct ranks from the start (frozen dataclass)
        cluster_stats = []
        for cluster_id, cluster_name in all_clusters:
            stats = player_stats.get(cluster_id, {})
            scoring_elo = stats.get('scoring_elo', EloConstants.STARTING_ELO)
            raw_elo = stats.get('raw_elo', EloConstants.STARTING_ELO)
            matches = stats.get('matches', 0)
            rank = cluster_ranks.get(cluster_id)  # None for unplayed, int for ranked
            
            cluster_stats.append(ClusterStats(
                cluster_name=cluster_name,
                cluster_id=cluster_id,
                scoring_elo=scoring_elo,
                raw_elo=raw_elo,
                matches_played=matches,
                rank_in_cluster=rank,  # Set correct rank during creation
                is_below_threshold=raw_elo < threshold
            ))
        
        # Sort by raw elo descending for proper top/bottom cluster identification
        cluster_stats.sort(key=lambda x: x.raw_elo, reverse=True)
        
        return cluster_stats
    
    def _calculate_overall_elo(self, cluster_stats: List[ClusterStats]) -> Tuple[float, float]:
        """
        Calculate Overall Elo using the "Weighted Generalist" formula.
        
        Formula from high-level overview section 2.6:
        Overall Elo = (Avg_T1 * 0.60) + (Avg_T2 * 0.25) + (Avg_T3 * 0.15)
        
        Where:
        - Tier 1 (60%): Average of player's 10 best Cluster Elos (ranks 1-10)
        - Tier 2 (25%): Average of next 5 best Cluster Elos (ranks 11-15)  
        - Tier 3 (15%): Average of final 5 Cluster Elos (ranks 16-20)
        - Missing clusters use STARTING_ELO (1000)
        
        Args:
            cluster_stats: List of ClusterStats (already sorted by raw_elo descending)
            
        Returns:
            Tuple of (overall_raw_elo, overall_scoring_elo)
        """
        # Extract elos from cluster stats
        raw_elos = [stats.raw_elo for stats in cluster_stats]
        scoring_elos = [stats.scoring_elo for stats in cluster_stats]
        
        # Sort descending to ensure proper tier assignment
        raw_elos.sort(reverse=True)
        scoring_elos.sort(reverse=True)
        
        # Ensure exactly 20 values (pad with STARTING_ELO for unplayed clusters)
        while len(raw_elos) < 20:
            raw_elos.append(EloConstants.STARTING_ELO)
            scoring_elos.append(EloConstants.STARTING_ELO)
        
        # Calculate tier averages
        # Tier 1: Ranks 1-10 (indices 0-9)
        tier1_raw = sum(raw_elos[0:10]) / 10
        tier1_scoring = sum(scoring_elos[0:10]) / 10
        
        # Tier 2: Ranks 11-15 (indices 10-14)  
        tier2_raw = sum(raw_elos[10:15]) / 5
        tier2_scoring = sum(scoring_elos[10:15]) / 5
        
        # Tier 3: Ranks 16-20 (indices 15-19)
        tier3_raw = sum(raw_elos[15:20]) / 5
        tier3_scoring = sum(scoring_elos[15:20]) / 5
        
        # Apply weighted formula: 60% + 25% + 15% = 100%
        overall_raw = (tier1_raw * EloConstants.TIER_1_WEIGHT) + (tier2_raw * EloConstants.TIER_2_WEIGHT) + (tier3_raw * EloConstants.TIER_3_WEIGHT)
        overall_scoring = (tier1_scoring * EloConstants.TIER_1_WEIGHT) + (tier2_scoring * EloConstants.TIER_2_WEIGHT) + (tier3_scoring * EloConstants.TIER_3_WEIGHT)
        
        return overall_raw, overall_scoring
    
    async def _fetch_cluster_ranks(self, session: AsyncSession, player_id: int) -> Dict[int, int]:
        """Fetch player's rank within each cluster using window function."""
        
        # First get the latest elo per player per cluster
        latest_elo_subquery = select(
            Cluster.id.label('cluster_id'),
            PlayerEventStats.player_id,
            PlayerEventStats.raw_elo,
            func.row_number().over(
                partition_by=[Cluster.id, PlayerEventStats.player_id],
                order_by=PlayerEventStats.updated_at.desc()
            ).label('rn')
        ).select_from(PlayerEventStats).join(
            Event, PlayerEventStats.event_id == Event.id
        ).join(
            Cluster, Event.cluster_id == Cluster.id
        ).where(
            Cluster.is_active == True
        ).subquery()
        
        # Then rank players within each cluster based on their latest elo
        ranking_query = select(
            latest_elo_subquery.c.cluster_id,
            latest_elo_subquery.c.player_id,
            func.rank().over(
                partition_by=latest_elo_subquery.c.cluster_id,
                order_by=latest_elo_subquery.c.raw_elo.desc()
            ).label('rank_in_cluster')
        ).where(
            latest_elo_subquery.c.rn == 1
        )
        
        # Execute and get ranks for our specific player
        result = await session.execute(
            ranking_query.where(latest_elo_subquery.c.player_id == player_id)
        )
        
        return {row.cluster_id: row.rank_in_cluster for row in result}
    
    async def _fetch_recent_matches(self, session: AsyncSession, player_id: int, limit: int = 5) -> List[MatchRecord]:
        """Fetch recent match history with opponent information efficiently using batch queries."""
        
        # Step 1: Query recent match history with opponent information from EloHistory
        # Use LEFT JOIN to get opponent from EloHistory.opponent_id when available
        query = select(
            EloHistory.match_id,
            EloHistory.elo_change,
            EloHistory.recorded_at,
            Event.name.label('event_name'),
            Player.display_name.label('opponent_name'),
            Player.id.label('opponent_id'),
            # Determine result based on elo change (simplified)
            case(
                (EloHistory.elo_change > 0, 'win'),
                (EloHistory.elo_change < 0, 'loss'),
                else_='draw'
            ).label('result')
        ).select_from(EloHistory).join(
            Event, EloHistory.event_id == Event.id
        ).outerjoin(
            Player, EloHistory.opponent_id == Player.id
        ).where(
            EloHistory.player_id == player_id
        ).order_by(
            EloHistory.recorded_at.desc()
        ).limit(limit)
        
        result = await session.execute(query)
        rows = result.all()
        
        # Step 2: Identify matches that need opponent lookup from MatchParticipant
        matches_needing_opponents = []
        for row in rows:
            if not row.opponent_id or not row.opponent_name:
                if row.match_id:
                    matches_needing_opponents.append(row.match_id)
        
        # Step 3: Batch fetch all missing opponents (ELIMINATES N+1 PATTERN)
        opponent_map = {}
        if matches_needing_opponents:
            batch_query = select(
                MatchParticipant.match_id,
                Player.display_name,
                Player.id
            ).select_from(MatchParticipant).join(
                Player, MatchParticipant.player_id == Player.id
            ).where(
                and_(
                    MatchParticipant.match_id.in_(matches_needing_opponents),
                    MatchParticipant.player_id != player_id
                )
            )
            
            batch_result = await session.execute(batch_query)
            # Build lookup map - take first opponent found per match (handles multiple participants)
            for batch_row in batch_result:
                if batch_row.match_id not in opponent_map:
                    opponent_map[batch_row.match_id] = {
                        'name': batch_row.display_name,
                        'id': batch_row.id
                    }
        
        # Step 4: Process all rows using the batched opponent data
        matches = []
        for row in rows:
            # Make recorded_at timezone-aware (UTC) for proper timestamp display
            played_at = row.recorded_at
            if played_at and played_at.tzinfo is None:
                played_at = played_at.replace(tzinfo=timezone.utc)
            
            # Determine opponent using batch-fetched data
            if row.match_id in opponent_map:
                # Use batch-fetched opponent data
                opponent_info = opponent_map[row.match_id]
                opponent_name = opponent_info['name']
                opponent_id = opponent_info['id']
            elif row.opponent_name and row.opponent_id:
                # Use opponent from EloHistory join
                opponent_name = row.opponent_name
                opponent_id = row.opponent_id
            elif not row.opponent_id and row.match_id:
                # No opponent found even in batch - likely FFA with multiple opponents
                opponent_name = "Multiple Opponents"
                opponent_id = 0
            else:
                # Fallback for edge cases
                opponent_name = "Unknown"
                opponent_id = 0
            
            matches.append(MatchRecord(
                match_id=row.match_id or 0,  # Handle null match_id for legacy records
                opponent_name=opponent_name,
                opponent_id=opponent_id,
                result=row.result,
                elo_change=row.elo_change,
                event_name=row.event_name,
                played_at=played_at
            ))
        
        return matches
    
    async def _calculate_streak_from_history(self, session: AsyncSession, player_id: int) -> int:
        """Calculate current streak from EloHistory records, counting distinct matches."""
        # Get recent elo history with match_id, ordered by most recent first
        # GROUP BY match_id to get one record per match, using the sum of elo changes
        history_query = select(
            EloHistory.match_id,
            func.sum(EloHistory.elo_change).label('total_elo_change'),
            func.max(EloHistory.recorded_at).label('latest_recorded_at')
        ).where(
            EloHistory.player_id == player_id,
            EloHistory.match_id.isnot(None)  # Only include records with match_id
        ).group_by(
            EloHistory.match_id
        ).order_by(
            func.max(EloHistory.recorded_at).desc()
        ).limit(20)  # Look at last 20 matches
        
        result = await session.execute(history_query)
        match_results = result.all()
        
        if not match_results:
            return 0
        
        # Extract the total elo changes per match
        elo_changes = [row.total_elo_change for row in match_results]
        
        # Find the first non-zero elo change to determine streak type
        streak_type = None  # True for wins, False for losses
        for elo_change in elo_changes:
            if elo_change > 0:
                streak_type = True
                break
            elif elo_change < 0:
                streak_type = False
                break
        
        if streak_type is None:
            return 0  # All draws
        
        # Count consecutive results of the same type
        streak_count = 0
        for elo_change in elo_changes:
            if streak_type and elo_change > 0:  # Win streak
                streak_count += 1
            elif not streak_type and elo_change < 0:  # Loss streak
                streak_count += 1
            elif elo_change != 0:  # Different result breaks streak
                break
            # Draws (elo_change == 0) don't break streak but don't extend it
        
        return streak_count if streak_type else -streak_count

    async def update_player_streak(self, player_id: int, session: AsyncSession):
        """Calculate and update a player's current streak from match history."""
        player = await session.get(Player, player_id)
        if not player:
            return
        
        # Calculate new streak from history
        new_streak = await self._calculate_streak_from_history(session, player_id)
        player.current_streak = new_streak
        
        # Add to session and flush (don't commit - let caller handle transaction)
        session.add(player)
        await session.flush([player])
        
        # Invalidate cache after database update
        self.invalidate_cache(player_id)

    def _format_current_streak(self, player: Player) -> str:
        """Format current streak from Player model for display."""
        # Use the current_streak field from Player model if available
        if hasattr(player, 'current_streak') and player.current_streak is not None:
            streak_value = player.current_streak
            if streak_value > 0:
                return f"W{streak_value}"  # Win streak: W3, W1, etc.
            elif streak_value < 0:
                return f"L{abs(streak_value)}"  # Loss streak: L1, L4, etc.
            else:
                return "W0"  # No streak (0) - show baseline W0
        
        # Fallback: no streak data available - show baseline
        return "W0"
    
    def _format_current_streak_value(self, current_streak: int) -> str:
        """Format current streak value for display."""
        if current_streak is not None:
            if current_streak > 0:
                return f"W{current_streak}"  # Win streak: W3, W1, etc.
            elif current_streak < 0:
                return f"L{abs(current_streak)}"  # Loss streak: L1, L4, etc.
            else:
                return "W0"  # No streak (0) - show baseline W0
        
        # Fallback: no streak data available - show baseline
        return "W0"
    
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