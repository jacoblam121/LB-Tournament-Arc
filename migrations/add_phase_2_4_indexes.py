"""
Add performance indexes for Phase 2.4 - EloHierarchyCalculator Integration

Creates indexes to optimize queries used by the hierarchy calculator and leaderboards.
"""

import asyncio
from sqlalchemy import text
from bot.database.database import Database
from bot.config import Config
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


async def upgrade(session):
    """Add performance indexes for Phase 2.4."""
    
    # Define indexes to create
    indexes = [
        # For EloHistory queries
        ("idx_elo_history_player_recorded", 
         "CREATE INDEX IF NOT EXISTS idx_elo_history_player_recorded ON elo_history(player_id, recorded_at DESC)"),
        ("idx_elo_history_players", 
         "CREATE INDEX IF NOT EXISTS idx_elo_history_players ON elo_history(player_id, opponent_id)"),
        
        # For MatchParticipant queries
        ("idx_match_participant_match", 
         "CREATE INDEX IF NOT EXISTS idx_match_participant_match ON match_participant(match_id, placement)"),
        
        # For PlayerEventStats queries (used by EloHierarchyCalculator)
        ("idx_player_event_stats_event", 
         "CREATE INDEX IF NOT EXISTS idx_player_event_stats_event ON player_event_stats(event_id, updated_at DESC)"),
        ("idx_player_event_stats_player_elo", 
         "CREATE INDEX IF NOT EXISTS idx_player_event_stats_player_elo ON player_event_stats(player_id, scoring_elo DESC)"),
        
        # For leaderboard sorting
        ("idx_player_final_score", 
         "CREATE INDEX IF NOT EXISTS idx_player_final_score ON players(final_score DESC) WHERE is_ghost = FALSE"),
        ("idx_player_scoring_elo", 
         "CREATE INDEX IF NOT EXISTS idx_player_scoring_elo ON players(overall_scoring_elo DESC) WHERE is_ghost = FALSE"),
        ("idx_player_raw_elo", 
         "CREATE INDEX IF NOT EXISTS idx_player_raw_elo ON players(overall_raw_elo DESC) WHERE is_ghost = FALSE"),
        
        # For EloHierarchyCalculator cluster aggregation
        ("idx_event_cluster", 
         "CREATE INDEX IF NOT EXISTS idx_event_cluster ON events(cluster_id, is_active)")
    ]
    
    # Execute each index creation
    for index_name, index_sql in indexes:
        try:
            await session.execute(text(index_sql))
            logger.info(f"Created index: {index_name}")
        except Exception as e:
            logger.warning(f"Failed to create index {index_name}: {e}")
    
    await session.commit()
    logger.info("Phase 2.4 performance indexes migration completed")


async def downgrade(session):
    """Remove Phase 2.4 performance indexes."""
    
    # Define indexes to drop
    indexes = [
        "idx_elo_history_player_recorded",
        "idx_elo_history_players",
        "idx_match_participant_match",
        "idx_player_event_stats_event",
        "idx_player_event_stats_player_elo",
        "idx_player_final_score",
        "idx_player_scoring_elo",
        "idx_player_raw_elo",
        "idx_event_cluster"
    ]
    
    # Drop each index
    for index_name in indexes:
        try:
            await session.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
            logger.info(f"Dropped index: {index_name}")
        except Exception as e:
            logger.warning(f"Failed to drop index {index_name}: {e}")
    
    await session.commit()
    logger.info("Phase 2.4 indexes rolled back")


async def main():
    """Run the migration."""
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        await upgrade(session)
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())