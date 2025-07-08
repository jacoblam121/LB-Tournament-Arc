"""
Shared ranking utilities for Phase 2.3 Implementation Coordination

Provides consistent ranking patterns for both ProfileService and LeaderboardService
following the CTE approach established in Phase 2.2.
"""

from typing import Optional, Dict, Any
from sqlalchemy import select, func, case, Integer
from sqlalchemy.sql import Select
from bot.database.models import Player, PlayerEventStats, Event, Cluster


class RankingUtility:
    """Shared ranking logic for consistent CTE pattern usage."""
    
    @staticmethod
    def create_player_ranking_cte(
        sort_by: str = "final_score",
        include_ghosts: bool = False,
        leaderboard_type: str = "overall",
        cluster_name: Optional[str] = None,
        event_name: Optional[str] = None
    ) -> Select:
        """
        Create a CTE that ranks all players using the consistent pattern from Phase 2.2.
        
        This ensures both ProfileService and LeaderboardService use the same ranking logic
        and addresses the coordination issues identified in Phase 2.3.
        
        FIXED: Eliminates duplicate player rows for cluster/event leaderboards through proper aggregation.
        FIXED: Honors sort_by parameter for all leaderboard types.
        FIXED: Resolves column name conflicts between Player and PlayerEventStats.
        """
        # Base columns for player information (excluding conflicting elo columns for cluster/event)
        base_columns = [
            Player.id.label('player_id'),
            Player.discord_id,
            Player.display_name,
            getattr(Player, 'is_ghost', case((Player.id.isnot(None), False), else_=False)).label('is_ghost'),
            getattr(Player, 'profile_color', case((Player.id.isnot(None), None), else_=None)).label('profile_color'),
        ]
        
        # Handle different leaderboard types with proper aggregation
        if leaderboard_type == "overall":
            # Overall leaderboard uses Player table columns directly
            query_columns = base_columns + [
                Player.final_score,
                Player.overall_scoring_elo,
                Player.overall_raw_elo,
                getattr(Player, 'shard_bonus', Player.final_score).label('shard_bonus'),
                getattr(Player, 'shop_bonus', Player.final_score).label('shop_bonus'),
            ]
            
            # Add match stats if available
            if hasattr(Player, 'matches_played'):
                query_columns.extend([
                    Player.matches_played,
                    Player.wins,
                    Player.losses,
                    Player.draws,
                    case((Player.matches_played > 0, (Player.wins * 100.0 / Player.matches_played)), else_=0.0).label('win_rate'),
                    getattr(Player, 'current_streak', case((Player.id.isnot(None), None), else_=None)).label('current_streak'),
                ])
            
            # Define sort column mapping for overall leaderboard
            sort_columns = {
                'final_score': Player.final_score,
                'scoring_elo': Player.overall_scoring_elo,
                'raw_elo': Player.overall_raw_elo,
                'shard_bonus': getattr(Player, 'shard_bonus', Player.final_score),
                'shop_bonus': getattr(Player, 'shop_bonus', Player.final_score)
            }
            sort_column = sort_columns.get(sort_by, Player.final_score)
            
            # Create base query
            query = select(*query_columns)
            
            # Add ranking columns
            query = query.add_columns(
                func.rank().over(order_by=sort_column.desc()).label('rank'),
                func.count(Player.id).over().label('total_players')
            )
            
        elif leaderboard_type in ("cluster", "event"):
            # Note: Cluster leaderboards are now handled specially in LeaderboardService
            # This code path is primarily for event leaderboards now
            
            if leaderboard_type == "cluster":
                # This should not be called anymore since cluster leaderboards
                # are handled in LeaderboardService._get_cluster_leaderboard_page()
                # Keeping this as a fallback for compatibility
                stats_subquery = (
                    select(
                        PlayerEventStats.player_id,
                        func.avg(PlayerEventStats.scoring_elo).label('avg_scoring_elo'),
                        func.avg(PlayerEventStats.raw_elo).label('avg_raw_elo'),
                        func.sum(PlayerEventStats.matches_played).label('total_matches'),
                        func.sum(PlayerEventStats.wins).label('total_wins'),
                        func.sum(PlayerEventStats.losses).label('total_losses'),
                        func.sum(PlayerEventStats.draws).label('total_draws'),
                        func.avg(PlayerEventStats.scoring_elo).label('avg_final_score'),
                        func.cast(0, Integer).label('total_shard_bonus'),
                        func.cast(0, Integer).label('total_shop_bonus')
                    )
                    .join(Event, PlayerEventStats.event_id == Event.id)
                    .join(Cluster, Event.cluster_id == Cluster.id)
                    .where(Cluster.name == cluster_name)
                    .group_by(PlayerEventStats.player_id)
                    .cte('cluster_stats')
                )
            else:  # event
                # Event leaderboard: direct stats from the specific event (already latest)
                stats_subquery = (
                    select(
                        PlayerEventStats.player_id,
                        PlayerEventStats.scoring_elo.label('avg_scoring_elo'),
                        PlayerEventStats.raw_elo.label('avg_raw_elo'),
                        PlayerEventStats.matches_played.label('total_matches'),
                        PlayerEventStats.wins.label('total_wins'),
                        PlayerEventStats.losses.label('total_losses'),
                        PlayerEventStats.draws.label('total_draws'),
                        PlayerEventStats.scoring_elo.label('avg_final_score'),
                        func.cast(0, Integer).label('total_shard_bonus'),
                        func.cast(0, Integer).label('total_shop_bonus')
                    )
                    .join(Event, PlayerEventStats.event_id == Event.id)
                    .where(Event.name == event_name)
                    .cte('event_stats')
                )
            
            # Define sort column mapping for cluster/event leaderboards using aggregated stats
            sort_columns = {
                'final_score': stats_subquery.c.avg_final_score,
                'scoring_elo': stats_subquery.c.avg_scoring_elo,
                'raw_elo': stats_subquery.c.avg_raw_elo,
                'shard_bonus': stats_subquery.c.total_shard_bonus,
                'shop_bonus': stats_subquery.c.total_shop_bonus
            }
            sort_column = sort_columns.get(sort_by, stats_subquery.c.avg_raw_elo)
            
            # Build final query columns using aggregated stats (no conflicts)
            query_columns = base_columns + [
                stats_subquery.c.avg_final_score.label('final_score'),
                stats_subquery.c.avg_scoring_elo.label('overall_scoring_elo'),
                stats_subquery.c.avg_raw_elo.label('overall_raw_elo'),
                stats_subquery.c.total_shard_bonus.label('shard_bonus'),
                stats_subquery.c.total_shop_bonus.label('shop_bonus'),
                stats_subquery.c.total_matches.label('matches_played'),
                stats_subquery.c.total_wins.label('wins'),
                stats_subquery.c.total_losses.label('losses'),
                stats_subquery.c.total_draws.label('draws'),
                case((
                    stats_subquery.c.total_matches > 0,
                    (stats_subquery.c.total_wins * 100.0 / stats_subquery.c.total_matches)
                ), else_=0.0).label('win_rate')
            ]
            
            # Create query joining Player with aggregated stats
            query = (
                select(*query_columns)
                .select_from(Player)
                .join(stats_subquery, Player.id == stats_subquery.c.player_id)
            )
            
            # Add ranking columns with proper sort column
            query = query.add_columns(
                func.rank().over(order_by=sort_column.desc()).label('rank'),
                func.count(Player.id).over().label('total_players')
            )
        
        # Filter ghosts unless specifically included
        if not include_ghosts and hasattr(Player, 'is_ghost'):
            query = query.where(Player.is_ghost == False)
        
        # Filter out players with no matches played (old test accounts)
        # Only apply this filter for overall leaderboard
        if leaderboard_type == "overall":
            query = query.where(Player.matches_played > 0)
        
        return query.cte('ranked_players')
    
    @staticmethod
    def get_sort_column_mapping() -> Dict[str, Any]:
        """Get consistent sort column mapping used across services."""
        return {
            'final_score': Player.final_score,
            'scoring_elo': Player.overall_scoring_elo,
            'raw_elo': Player.overall_raw_elo,
            'shard_bonus': getattr(Player, 'shard_bonus', Player.final_score),
            'shop_bonus': getattr(Player, 'shop_bonus', Player.final_score)
        }
    
    @staticmethod
    def validate_sort_by(sort_by: str) -> bool:
        """Validate sort_by parameter against allowed values."""
        allowed_sorts = ['final_score', 'scoring_elo', 'raw_elo', 'shard_bonus', 'shop_bonus']
        return sort_by in allowed_sorts
    
    @staticmethod
    def validate_leaderboard_type(leaderboard_type: str) -> bool:
        """Validate leaderboard_type parameter against allowed values."""
        allowed_types = ['overall', 'cluster', 'event']
        return leaderboard_type in allowed_types