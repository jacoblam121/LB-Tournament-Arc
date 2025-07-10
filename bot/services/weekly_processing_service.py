"""
Weekly Processing Service for Phase 3.4 - Manual Weekly Processing System

This service handles the processing of weekly leaderboard scores, calculating weekly Elos,
updating player averages, and applying inactivity penalties. It provides the core logic
for the manual weekly reset system.

Key Features:
- Weekly score processing with Z-score normalization
- 50/50 composite Elo calculation (all-time vs weekly average)
- Inactivity penalty system for missed weeks
- Transaction safety and error handling
- Integration with existing LeaderboardScoringService
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from sqlalchemy import select, func, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from bot.services.base import BaseService
from bot.database.models import (
    Event, LeaderboardScore, PlayerEventStats, Player, ScoreType, ScoreDirection
)

logger = logging.getLogger(__name__)

class WeeklyProcessingService(BaseService):
    """Service for processing weekly leaderboard scores and updating player statistics."""
    
    def __init__(self, session_factory, scoring_service):
        super().__init__(session_factory)
        self.scoring_service = scoring_service  # LeaderboardScoringService dependency
    
    async def process_weekly_scores(self, event_id: int) -> Dict:
        """
        Process weekly scores for a specific event and update player averages.
        
        This method:
        1. Calculates Z-scores for all weekly scores
        2. Converts Z-scores to Elo ratings 
        3. Updates player weekly averages
        4. Applies inactivity penalties for missed weeks
        5. Calculates composite Elo (50/50 all-time vs weekly)
        6. Clears weekly scores for the next week
        
        Args:
            event_id: ID of the event to process
            
        Returns:
            Dict with processing results and statistics
        """
        async with self.get_session() as session:
            async with session.begin():  # Ensure transactional safety
                
                current_week = self._get_current_week()
                
                # Get event details
                event = await session.get(Event, event_id)
                if not event or not event.score_direction:
                    raise ValueError(f"Event {event_id} is not a valid leaderboard event")
                
                # Get all weekly scores for current week
                weekly_scores = await self._get_weekly_scores(session, event_id, current_week)
                
                if not weekly_scores:
                    raise ValueError(f"No weekly scores found for event {event_id}, week {current_week}")
                
                # Calculate weekly Elos using Z-score normalization
                weekly_elo_results = await self._calculate_weekly_elos(
                    session, weekly_scores, event.score_direction
                )
                
                # Update player weekly averages and track active players
                active_player_ids = {score_data['player_id'] for score_data in weekly_elo_results}
                
                # Batch fetch existing PlayerEventStats to avoid N+1 queries
                if active_player_ids:
                    stats_stmt = select(PlayerEventStats).where(
                        PlayerEventStats.event_id == event_id,
                        PlayerEventStats.player_id.in_(active_player_ids)
                    )
                    stats_result = await session.execute(stats_stmt)
                    stats_map = {s.player_id: s for s in stats_result.scalars()}
                else:
                    stats_map = {}
                
                # Update weekly averages using pre-fetched stats
                for score_data in weekly_elo_results:
                    player_id = score_data['player_id']
                    weekly_elo = score_data['weekly_elo']
                    stats = stats_map.get(player_id)
                    
                    if not stats:
                        # Create new stats record
                        stats = PlayerEventStats(
                            player_id=player_id,
                            event_id=event_id,
                            weekly_elo_average=weekly_elo,
                            weeks_participated=1
                        )
                        session.add(stats)
                    else:
                        # Update existing average incrementally
                        current_total = (stats.weekly_elo_average or 0) * (stats.weeks_participated or 0)
                        new_total = current_total + weekly_elo
                        new_weeks = (stats.weeks_participated or 0) + 1
                        
                        stats.weekly_elo_average = new_total / new_weeks
                        stats.weeks_participated = new_weeks
                
                # Apply inactivity penalties to players who missed this week
                await self._penalize_inactive_players(session, event_id, active_player_ids)
                
                # Calculate final composite Elos for all participants
                final_results = []
                all_participants = await self._get_all_event_participants(session, event_id)
                
                # Batch fetch all player objects to avoid N+1 queries
                participant_player_ids = [ps.player_id for ps in all_participants]
                if participant_player_ids:
                    player_results = await session.execute(
                        select(Player).where(Player.id.in_(participant_player_ids))
                    )
                    player_map = {p.id: p for p in player_results.scalars()}
                else:
                    player_map = {}
                
                for player_stats in all_participants:
                    composite_elo = await self._calculate_composite_elo(session, player_stats)
                    
                    # Update the final_score field with composite result for leaderboard ranking
                    player_stats.final_score = composite_elo
                    
                    # Get player info from the pre-fetched map
                    player = player_map.get(player_stats.player_id)
                    if not player:
                        logger.warning(f"Player record not found for player_id {player_stats.player_id}, skipping.")
                        continue
                    
                    final_results.append({
                        'player_id': player.id,
                        'player_name': player.username,
                        'all_time_elo': player_stats.all_time_leaderboard_elo or 1000,
                        'weekly_avg_elo': player_stats.weekly_elo_average or 0,
                        'composite_elo': composite_elo,
                        'weeks_participated': player_stats.weeks_participated or 0,
                        'was_active_this_week': player_stats.player_id in active_player_ids
                    })
                
                # Clear weekly scores for fresh start next week
                await self._clear_weekly_scores(session, event_id, current_week)
                
                # Sort results by composite Elo for leaderboard display
                final_results.sort(key=lambda x: x['composite_elo'], reverse=True)
                
                logger.info(f"Weekly processing completed for event {event_id}, week {current_week}")
                
                return {
                    'event_id': event_id,
                    'week_number': current_week,
                    'active_players': len(active_player_ids),
                    'total_participants': len(final_results),
                    'weekly_scores_processed': len(weekly_scores),
                    'top_players': final_results
                }
    
    async def _get_weekly_scores(self, session: AsyncSession, event_id: int, week_number: int) -> List:
        """Get all weekly scores for the specified event and week."""
        stmt = select(LeaderboardScore).where(
            LeaderboardScore.event_id == event_id,
            LeaderboardScore.score_type == ScoreType.WEEKLY,
            LeaderboardScore.week_number == week_number
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    async def _calculate_weekly_elos(self, session: AsyncSession, weekly_scores: List, 
                                   direction: ScoreDirection) -> List[Dict]:
        """Calculate Z-scores and convert to Elo ratings for weekly scores."""
        if not weekly_scores:
            return []
        
        # Calculate statistical parameters
        scores = [ws.score for ws in weekly_scores]
        mean_score = sum(scores) / len(scores)
        
        if len(scores) > 1:
            variance = sum((score - mean_score) ** 2 for score in scores) / len(scores)
            std_dev = variance ** 0.5
        else:
            std_dev = 1.0  # Default for single score
        
        # Ensure non-zero standard deviation
        if std_dev == 0:
            std_dev = 1.0
        
        results = []
        for weekly_score in weekly_scores:
            # Calculate Z-score based on direction
            z_score = self.scoring_service._calculate_z_score(
                weekly_score.score, mean_score, std_dev, direction
            )
            
            # Convert to Elo rating
            weekly_elo = self.scoring_service._z_score_to_elo(z_score)
            
            results.append({
                'player_id': weekly_score.player_id,
                'score': weekly_score.score,
                'z_score': z_score,
                'weekly_elo': weekly_elo
            })
        
        return results
    
    
    async def _penalize_inactive_players(self, session: AsyncSession, event_id: int, 
                                       active_player_ids: Set[int]):
        """Apply inactivity penalty to players who missed this week."""
        
        # Get all players who have ever participated in this event
        stmt = select(PlayerEventStats).where(
            PlayerEventStats.event_id == event_id,
            PlayerEventStats.weeks_participated > 0
        )
        all_participants = await session.execute(stmt)
        
        for stats in all_participants.scalars():
            if stats.player_id not in active_player_ids:
                # Add 0 to their average (counts as participation with 0 Elo)
                current_total = (stats.weekly_elo_average or 0) * (stats.weeks_participated or 0)
                new_total = current_total + 0  # Add 0 for missed week
                new_weeks = (stats.weeks_participated or 0) + 1
                
                stats.weekly_elo_average = new_total / new_weeks
                stats.weeks_participated = new_weeks
                
                logger.debug(f"Applied inactivity penalty to player {stats.player_id} for event {event_id}")
    
    async def _get_all_event_participants(self, session: AsyncSession, event_id: int) -> List:
        """Get all players who have ever participated in this event."""
        stmt = select(PlayerEventStats).where(
            PlayerEventStats.event_id == event_id,
            PlayerEventStats.weeks_participated > 0
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    async def _calculate_composite_elo(self, session: AsyncSession, player_stats: PlayerEventStats) -> int:
        """Calculate 50/50 composite of all-time and weekly average Elo."""
        
        all_time_elo = player_stats.all_time_leaderboard_elo or 1000
        weekly_avg_elo = player_stats.weekly_elo_average or 0
        
        # 50/50 composite formula
        composite = round((all_time_elo * 0.5) + (weekly_avg_elo * 0.5))
        
        return composite
    
    async def _clear_weekly_scores(self, session: AsyncSession, event_id: int, week_number: int):
        """Clear weekly scores for the specified event and week."""
        stmt = delete(LeaderboardScore).where(
            LeaderboardScore.event_id == event_id,
            LeaderboardScore.score_type == ScoreType.WEEKLY,
            LeaderboardScore.week_number == week_number
        )
        await session.execute(stmt)
        logger.info(f"Cleared weekly scores for event {event_id}, week {week_number}")
    
    def _get_current_week(self, timezone_name: str = 'UTC') -> int:
        """Get current ISO week number."""
        import pytz
        tz = pytz.timezone(timezone_name)
        current_time = datetime.now(tz)
        return current_time.isocalendar()[1]