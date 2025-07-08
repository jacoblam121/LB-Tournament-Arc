"""
Player Stats Synchronization Service

Handles synchronization of event-specific stats to overall player stats.
This service bridges the gap between PlayerEventStats and Player table,
ensuring overall ELO and final scores are properly calculated and updated.
"""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import Player, PlayerEventStats
from bot.operations.elo_hierarchy import EloHierarchyCalculator
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


class PlayerStatsSyncService:
    """Service for synchronizing player statistics from events to overall stats."""
    
    async def update_player_overall_stats(self, session: AsyncSession, player_id: int) -> None:
        """
        Calculates and updates a player's overall ELO and final score.
        
        This method:
        1. Uses EloHierarchyCalculator to aggregate event ELOs
        2. Updates overall_raw_elo and overall_scoring_elo
        3. Calculates final_score = scoring_elo + bonuses
        
        Args:
            session: Database session
            player_id: ID of the player to update
        """
        player = await session.get(Player, player_id)
        if not player:
            logger.error(f"Player {player_id} not found for stats sync")
            return
        
        # Calculate new overall ELO using the hierarchy calculator
        calculator = EloHierarchyCalculator(session)
        hierarchy_data = await calculator.calculate_player_hierarchy(player_id)
        
        # Update overall ELO stats using the correct fields
        player.overall_raw_elo = hierarchy_data.get('overall_raw_elo', hierarchy_data['overall_elo'])
        player.overall_scoring_elo = hierarchy_data.get('overall_scoring_elo', max(1000, hierarchy_data['overall_elo']))
        
        # Calculate final score (scoring_elo + bonuses)
        # For now, shard_bonus and shop_bonus default to 0 until implemented
        player.final_score = (
            player.overall_scoring_elo + 
            (player.shard_bonus or 0) + 
            (player.shop_bonus or 0)
        )
        
        # Add updated player to session (caller handles commit)
        session.add(player)
        
        logger.info(
            f"Updated player {player_id} overall stats: "
            f"raw_elo={player.overall_raw_elo}, "
            f"scoring_elo={player.overall_scoring_elo}, "
            f"final_score={player.final_score}"
        )
    
    async def sync_match_participants(
        self, 
        session: AsyncSession, 
        participant_ids: List[int]
    ) -> None:
        """
        Synchronize stats for all participants in a match.
        
        Args:
            session: Database session
            participant_ids: List of player IDs who participated in the match
        """
        for player_id in participant_ids:
            await self.update_player_overall_stats(session, player_id)
        
        logger.info(f"Synchronized stats for {len(participant_ids)} match participants")
    
    async def sync_all_players(self, session: AsyncSession) -> int:
        """
        Synchronize stats for all players in the database.
        Useful for initial migration or fixing data inconsistencies.
        
        Args:
            session: Database session
            
        Returns:
            Number of players updated
        """
        from sqlalchemy import select
        
        # Get all active players
        result = await session.execute(
            select(Player).where(Player.is_active == True)
        )
        players = result.scalars().all()
        
        count = 0
        for player in players:
            await self.update_player_overall_stats(session, player.id)
            count += 1
            
            # Commit in batches to avoid long transactions
            if count % 50 == 0:
                await session.commit()
                logger.info(f"Synced {count} players...")
        
        logger.info(f"Completed sync for {count} total players")
        return count