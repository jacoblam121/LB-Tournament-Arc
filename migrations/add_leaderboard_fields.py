"""
Add leaderboard fields for Phase 3.1 implementation

This migration adds the LeaderboardScore model and updates existing models
to support the unified leaderboard system with NULL-safe constraints.
"""

import asyncio
from sqlalchemy import text
from bot.database.database import Database
from bot.config import Config
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


async def upgrade(session):
    """Add leaderboard fields and LeaderboardScore table."""
    
    # Update events table to use enum for score_direction
    try:
        await session.execute(text("""
            ALTER TABLE events 
            ALTER COLUMN score_direction TYPE VARCHAR(10);
        """))
        logger.info("Updated events.score_direction column type")
    except Exception as e:
        logger.warning(f"Failed to update events.score_direction: {e}")
    
    # Add weekly processing fields to player_event_stats
    weekly_fields = [
        ("weekly_elo_average", "ALTER TABLE player_event_stats ADD COLUMN weekly_elo_average FLOAT DEFAULT 0"),
        ("weeks_participated", "ALTER TABLE player_event_stats ADD COLUMN weeks_participated INTEGER DEFAULT 0")
    ]
    
    for field_name, field_sql in weekly_fields:
        try:
            await session.execute(text(field_sql))
            logger.info(f"Added field: {field_name}")
        except Exception as e:
            logger.warning(f"Failed to add field {field_name}: {e}")
    
    # Create LeaderboardScore table
    try:
        await session.execute(text("""
            CREATE TABLE leaderboard_scores (
                id SERIAL PRIMARY KEY,
                player_id INTEGER REFERENCES players(id) NOT NULL,
                event_id INTEGER REFERENCES events(id) NOT NULL,
                score FLOAT NOT NULL,
                score_type VARCHAR(20) NOT NULL,
                week_number INTEGER,
                submitted_at TIMESTAMP DEFAULT NOW()
            );
        """))
        logger.info("Created leaderboard_scores table")
    except Exception as e:
        logger.warning(f"Failed to create leaderboard_scores table: {e}")
    
    # Add NULL-safe unique constraints - CRITICAL FIX from Phase 3.1
    constraints = [
        (
            "uq_weekly_scores",
            """CREATE UNIQUE INDEX uq_weekly_scores ON leaderboard_scores(player_id, event_id, score_type, week_number) 
               WHERE week_number IS NOT NULL;"""
        ),
        (
            "uq_all_time_scores", 
            """CREATE UNIQUE INDEX uq_all_time_scores ON leaderboard_scores(player_id, event_id) 
               WHERE score_type = 'all_time' AND week_number IS NULL;"""
        ),
        (
            "idx_leaderboard_scores_event",
            "CREATE INDEX idx_leaderboard_scores_event ON leaderboard_scores(event_id, score_type);"
        ),
        (
            "idx_leaderboard_scores_week",
            "CREATE INDEX idx_leaderboard_scores_week ON leaderboard_scores(event_id, score_type, week_number);"
        )
    ]
    
    for constraint_name, constraint_sql in constraints:
        try:
            await session.execute(text(constraint_sql))
            logger.info(f"Created constraint/index: {constraint_name}")
        except Exception as e:
            logger.warning(f"Failed to create constraint {constraint_name}: {e}")
    
    await session.commit()
    logger.info("Leaderboard fields migration completed")


async def downgrade(session):
    """Remove leaderboard fields and table."""
    
    # Drop indexes and constraints
    constraints_to_drop = [
        "DROP INDEX IF EXISTS idx_leaderboard_scores_week",
        "DROP INDEX IF EXISTS idx_leaderboard_scores_event", 
        "DROP INDEX IF EXISTS uq_all_time_scores",
        "DROP INDEX IF EXISTS uq_weekly_scores"
    ]
    
    for constraint_sql in constraints_to_drop:
        try:
            await session.execute(text(constraint_sql))
            logger.info(f"Dropped constraint: {constraint_sql}")
        except Exception as e:
            logger.warning(f"Failed to drop constraint: {e}")
    
    # Drop leaderboard_scores table
    try:
        await session.execute(text("DROP TABLE IF EXISTS leaderboard_scores"))
        logger.info("Dropped leaderboard_scores table")
    except Exception as e:
        logger.warning(f"Failed to drop leaderboard_scores table: {e}")
    
    # Remove weekly fields from player_event_stats
    fields_to_drop = ["weeks_participated", "weekly_elo_average"]
    
    for field_name in fields_to_drop:
        try:
            await session.execute(text(f"ALTER TABLE player_event_stats DROP COLUMN {field_name}"))
            logger.info(f"Dropped field: {field_name}")
        except Exception as e:
            logger.warning(f"Failed to drop field {field_name}: {e}")
    
    await session.commit()
    logger.info("Leaderboard fields migration rolled back")


async def main():
    """Run the migration."""
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        await upgrade(session)
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())