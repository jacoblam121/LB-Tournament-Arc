"""
Add leaderboard fields for Phase 3.1 implementation (FIXED VERSION)

This migration adds the LeaderboardScore model and updates existing models
to support the unified leaderboard system with proper enum types and constraints.

FIXES APPLIED:
- Creates PostgreSQL enum types for ScoreDirection and ScoreType
- Adds proper NOT NULL constraints for weeks_participated
- Includes CHECK constraint for data integrity
- Handles both PostgreSQL and SQLite compatibility
"""

import asyncio
from sqlalchemy import text
from bot.database.database import Database
from bot.config import Config
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


async def get_db_dialect(session):
    """Get database dialect name for conditional logic."""
    return session.get_bind().dialect.name


async def upgrade(session):
    """Add leaderboard fields and LeaderboardScore table with proper enum types."""
    
    dialect = await get_db_dialect(session)
    logger.info(f"Running migration for dialect: {dialect}")
    
    # Create enum types for PostgreSQL
    if dialect == "postgresql":
        try:
            # Create ScoreDirection enum (if not exists)
            await session.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scoredirection') THEN
                        CREATE TYPE scoredirection AS ENUM ('HIGH', 'LOW');
                    END IF;
                END $$;
            """))
            logger.info("Created or verified scoredirection enum type")
            
            # Create ScoreType enum
            await session.execute(text("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scoretype') THEN
                        CREATE TYPE scoretype AS ENUM ('all_time', 'weekly');
                    END IF;
                END $$;
            """))
            logger.info("Created or verified scoretype enum type")
            
            # Update events table to use proper enum type
            await session.execute(text("""
                ALTER TABLE events 
                ALTER COLUMN score_direction TYPE scoredirection 
                USING score_direction::scoredirection;
            """))
            logger.info("Updated events.score_direction to use enum type")
            
        except Exception as e:
            logger.error(f"Failed to create enum types: {e}")
            raise
    
    # Add weekly processing fields to player_event_stats
    weekly_fields = [
        ("weekly_elo_average", "ALTER TABLE player_event_stats ADD COLUMN weekly_elo_average FLOAT DEFAULT 0"),
        ("weeks_participated", "ALTER TABLE player_event_stats ADD COLUMN weeks_participated INTEGER NOT NULL DEFAULT 0")
    ]
    
    for field_name, field_sql in weekly_fields:
        try:
            await session.execute(text(field_sql))
            logger.info(f"Added field: {field_name}")
        except Exception as e:
            logger.warning(f"Failed to add field {field_name}: {e}")
    
    # Create LeaderboardScore table with proper enum types
    try:
        if dialect == "postgresql":
            create_table_sql = """
                CREATE TABLE leaderboard_scores (
                    id SERIAL PRIMARY KEY,
                    player_id INTEGER REFERENCES players(id) NOT NULL,
                    event_id INTEGER REFERENCES events(id) NOT NULL,
                    score FLOAT NOT NULL,
                    score_type scoretype NOT NULL,
                    week_number INTEGER,
                    submitted_at TIMESTAMP DEFAULT NOW()
                );
            """
        else:
            # SQLite fallback with CHECK constraint
            create_table_sql = """
                CREATE TABLE leaderboard_scores (
                    id INTEGER PRIMARY KEY,
                    player_id INTEGER REFERENCES players(id) NOT NULL,
                    event_id INTEGER REFERENCES events(id) NOT NULL,
                    score FLOAT NOT NULL,
                    score_type VARCHAR(20) NOT NULL CHECK (score_type IN ('all_time', 'weekly')),
                    week_number INTEGER,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """
        
        await session.execute(text(create_table_sql))
        logger.info("Created leaderboard_scores table")
    except Exception as e:
        logger.error(f"Failed to create leaderboard_scores table: {e}")
        raise
    
    # Add data integrity CHECK constraint
    try:
        await session.execute(text("""
            ALTER TABLE leaderboard_scores 
            ADD CONSTRAINT ck_leaderboard_score_type_week_consistency 
            CHECK (
                (score_type = 'all_time' AND week_number IS NULL) OR 
                (score_type = 'weekly' AND week_number IS NOT NULL)
            );
        """))
        logger.info("Added data integrity CHECK constraint")
    except Exception as e:
        logger.warning(f"Failed to add CHECK constraint: {e}")
    
    # Add NULL-safe unique constraints
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
    logger.info("Leaderboard fields migration completed successfully")


async def downgrade(session):
    """Remove leaderboard fields and table."""
    
    dialect = await get_db_dialect(session)
    logger.info(f"Running downgrade for dialect: {dialect}")
    
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
    
    # Revert events.score_direction to VARCHAR for PostgreSQL
    if dialect == "postgresql":
        try:
            await session.execute(text("""
                ALTER TABLE events 
                ALTER COLUMN score_direction TYPE VARCHAR(10);
            """))
            logger.info("Reverted events.score_direction to VARCHAR")
        except Exception as e:
            logger.warning(f"Failed to revert score_direction: {e}")
        
        # Drop enum types
        try:
            await session.execute(text("DROP TYPE IF EXISTS scoretype CASCADE"))
            await session.execute(text("DROP TYPE IF EXISTS scoredirection CASCADE"))
            logger.info("Dropped enum types")
        except Exception as e:
            logger.warning(f"Failed to drop enum types: {e}")
    
    await session.commit()
    logger.info("Leaderboard fields migration rolled back successfully")


async def main():
    """Run the migration."""
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        await upgrade(session)
    
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())