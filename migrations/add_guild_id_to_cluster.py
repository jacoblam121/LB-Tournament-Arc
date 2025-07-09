"""
Migration script to add guild_id field to Cluster table for guild-specific validation
"""

import asyncio
from sqlalchemy import text
from bot.database.database import Database
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


async def get_db_dialect(session):
    """Get database dialect name for conditional logic."""
    return session.get_bind().dialect.name


async def upgrade(session):
    """Add guild_id field to Cluster table."""
    
    dialect = await get_db_dialect(session)
    logger.info(f"Running guild_id migration on {dialect} database")
    
    # Add guild_id field to clusters table
    try:
        if dialect == "postgresql":
            # PostgreSQL uses BIGINT for Discord IDs
            await session.execute(text("ALTER TABLE clusters ADD COLUMN guild_id BIGINT"))
        else:
            # SQLite uses INTEGER for Discord IDs
            await session.execute(text("ALTER TABLE clusters ADD COLUMN guild_id INTEGER"))
        
        logger.info("Added guild_id column to clusters table")
    except Exception as e:
        logger.warning(f"Failed to add guild_id column (may already exist): {e}")
    
    # Add index for guild_id for performance
    try:
        await session.execute(text("CREATE INDEX IF NOT EXISTS idx_clusters_guild_id ON clusters(guild_id)"))
        logger.info("Created index: idx_clusters_guild_id")
    except Exception as e:
        logger.warning(f"Failed to create guild_id index: {e}")
    
    await session.commit()
    logger.info("Guild ID migration completed successfully")


async def downgrade(session):
    """Remove guild_id field from Cluster table."""
    
    dialect = await get_db_dialect(session)
    logger.info(f"Rolling back guild_id migration on {dialect} database")
    
    # Drop the index first
    try:
        await session.execute(text("DROP INDEX IF EXISTS idx_clusters_guild_id"))
        logger.info("Dropped index: idx_clusters_guild_id")
    except Exception as e:
        logger.warning(f"Failed to drop guild_id index: {e}")
    
    # Drop the column
    try:
        await session.execute(text("ALTER TABLE clusters DROP COLUMN guild_id"))
        logger.info("Dropped guild_id column from clusters table")
    except Exception as e:
        logger.warning(f"Failed to drop guild_id column: {e}")
    
    await session.commit()
    logger.info("Guild ID migration rolled back successfully")


async def main():
    """Run the migration."""
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        await upgrade(session)
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())