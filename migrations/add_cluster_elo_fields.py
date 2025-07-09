"""
Add cluster ELO fields to MatchParticipant table

This migration adds cluster ELO tracking fields to the match_participants table
to support displaying cluster ELO changes alongside event ELO changes in match results.
"""

import asyncio
from sqlalchemy import text
from bot.database.database import Database
from bot.config import Config
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


async def upgrade(session):
    """Add cluster ELO fields to match_participants table."""
    
    # Define columns to add
    columns = [
        ("cluster_id", "ALTER TABLE match_participants ADD COLUMN cluster_id INTEGER REFERENCES clusters(id)"),
        ("cluster_elo_before", "ALTER TABLE match_participants ADD COLUMN cluster_elo_before INTEGER"),
        ("cluster_elo_after", "ALTER TABLE match_participants ADD COLUMN cluster_elo_after INTEGER"),
        ("cluster_elo_change", "ALTER TABLE match_participants ADD COLUMN cluster_elo_change INTEGER DEFAULT 0")
    ]
    
    # Execute each column addition
    for column_name, column_sql in columns:
        try:
            await session.execute(text(column_sql))
            logger.info(f"Added column: {column_name}")
        except Exception as e:
            logger.warning(f"Failed to add column {column_name}: {e}")
    
    # Add index for cluster_id for performance
    try:
        await session.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_match_participants_cluster ON match_participants(cluster_id)"
        ))
        logger.info("Created index: idx_match_participants_cluster")
    except Exception as e:
        logger.warning(f"Failed to create cluster index: {e}")
    
    await session.commit()
    logger.info("Cluster ELO fields migration completed")


async def downgrade(session):
    """Remove cluster ELO fields from match_participants table."""
    
    # Drop the index first
    try:
        await session.execute(text("DROP INDEX IF EXISTS idx_match_participants_cluster"))
        logger.info("Dropped index: idx_match_participants_cluster")
    except Exception as e:
        logger.warning(f"Failed to drop cluster index: {e}")
    
    # Define columns to drop
    columns = ["cluster_elo_change", "cluster_elo_after", "cluster_elo_before", "cluster_id"]
    
    # Drop each column
    for column_name in columns:
        try:
            await session.execute(text(f"ALTER TABLE match_participants DROP COLUMN {column_name}"))
            logger.info(f"Dropped column: {column_name}")
        except Exception as e:
            logger.warning(f"Failed to drop column {column_name}: {e}")
    
    await session.commit()
    logger.info("Cluster ELO fields rolled back")


async def main():
    """Run the migration."""
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        await upgrade(session)
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())