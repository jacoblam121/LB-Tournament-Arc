#!/usr/bin/env python3
"""
Phase 1.1 Model Updates Migration
Adds event-specific fields to PlayerEventStats and creates ChallengeParticipant table

This is an additive-only migration that preserves existing data while adding:
1. Meta-game economy fields to PlayerEventStats
2. ChallengeParticipant model for N-player challenge support
3. Participants relationship to Challenge model

Migration is designed to be idempotent and safe to run multiple times.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import List, Dict, Any
import shutil

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, select, insert
from sqlalchemy.exc import OperationalError

from bot.config import Config
from bot.database.models import Base, Challenge, ConfirmationStatus
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)

# Migration configuration
BACKUP_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
MIGRATION_NAME = "phase_1.1_model_updates"

async def create_database_backup() -> str:
    """Create a backup of the current database"""
    try:
        backup_path = f"tournament_backup_{MIGRATION_NAME}_{BACKUP_TIMESTAMP}.db"
        shutil.copy2("tournament.db", backup_path)
        logger.info(f"Database backup created: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise

async def get_engine():
    """Create async database engine"""
    database_url = Config.DATABASE_URL
    if database_url.startswith('sqlite:///'):
        database_url = database_url.replace('sqlite:///', 'sqlite+aiosqlite:///')
    
    return create_async_engine(database_url, echo=False)

async def table_exists(session: AsyncSession, table_name: str) -> bool:
    """Check if a table exists in the database"""
    if 'sqlite' in str(session.bind.url):
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table_name}
        )
    else:
        # PostgreSQL/MySQL query would be different
        raise NotImplementedError("Only SQLite is currently supported")
    
    return result.scalar() is not None

async def column_exists(session: AsyncSession, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    if 'sqlite' in str(session.bind.url):
        result = await session.execute(
            text(f"PRAGMA table_info({table_name})")
        )
        columns = result.fetchall()
        return any(col[1] == column_name for col in columns)
    else:
        raise NotImplementedError("Only SQLite is currently supported")

async def add_columns_to_player_event_stats(session: AsyncSession) -> bool:
    """Add meta-game economy fields to PlayerEventStats table"""
    try:
        # Check if PlayerEventStats table exists
        if not await table_exists(session, 'player_event_stats'):
            logger.info("PlayerEventStats table does not exist yet - will be created by models")
            return True
        
        # Add columns if they don't exist
        columns_to_add = [
            ('final_score', 'INTEGER'),
            ('shard_bonus', 'INTEGER DEFAULT 0'),
            ('shop_bonus', 'INTEGER DEFAULT 0')
        ]
        
        for column_name, column_def in columns_to_add:
            if not await column_exists(session, 'player_event_stats', column_name):
                logger.info(f"Adding column {column_name} to player_event_stats")
                await session.execute(
                    text(f"ALTER TABLE player_event_stats ADD COLUMN {column_name} {column_def}")
                )
                await session.commit()
            else:
                logger.info(f"Column {column_name} already exists in player_event_stats")
        
        return True
        
    except Exception as e:
        logger.error(f"Error adding columns to player_event_stats: {e}")
        await session.rollback()
        return False

async def create_challenge_participants_table(session: AsyncSession) -> bool:
    """Create the challenge_participants table"""
    try:
        # Check if table already exists
        if await table_exists(session, 'challenge_participants'):
            logger.info("challenge_participants table already exists")
            return True
        
        logger.info("Creating challenge_participants table")
        
        # Create the table
        await session.execute(text("""
            CREATE TABLE challenge_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenge_id INTEGER NOT NULL,
                player_id INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                responded_at DATETIME,
                team_id VARCHAR(50),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (challenge_id) REFERENCES challenges(id),
                FOREIGN KEY (player_id) REFERENCES players(id),
                UNIQUE (challenge_id, player_id)
            )
        """))
        
        # Create indexes
        await session.execute(text(
            "CREATE INDEX idx_challenge_participants_challenge_id ON challenge_participants(challenge_id)"
        ))
        await session.execute(text(
            "CREATE INDEX idx_challenge_participants_player_id ON challenge_participants(player_id)"
        ))
        
        await session.commit()
        logger.info("challenge_participants table created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error creating challenge_participants table: {e}")
        await session.rollback()
        return False

async def migrate_existing_challenges(session: AsyncSession) -> bool:
    """Migrate existing 1v1 challenges to use ChallengeParticipant records"""
    try:
        # Check if we have any challenges to migrate
        result = await session.execute(
            text("SELECT COUNT(*) FROM challenges WHERE challenger_id IS NOT NULL")
        )
        challenge_count = result.scalar()
        
        if challenge_count == 0:
            logger.info("No existing challenges to migrate")
            return True
        
        logger.info(f"Migrating {challenge_count} existing challenges to use ChallengeParticipant")
        
        # Get all challenges with challenger/challenged IDs
        result = await session.execute(
            text("""
                SELECT id, challenger_id, challenged_id, status 
                FROM challenges 
                WHERE challenger_id IS NOT NULL AND challenged_id IS NOT NULL
            """)
        )
        challenges = result.fetchall()
        
        migrated = 0
        for challenge in challenges:
            challenge_id, challenger_id, challenged_id, status = challenge
            
            # Determine participant status based on challenge status
            if status in ['completed', 'accepted']:
                participant_status = 'confirmed'
            elif status == 'declined':
                participant_status = 'rejected'
            else:
                participant_status = 'pending'
            
            # Check if participants already exist
            existing = await session.execute(
                text("""
                    SELECT COUNT(*) FROM challenge_participants 
                    WHERE challenge_id = :challenge_id
                """),
                {"challenge_id": challenge_id}
            )
            
            if existing.scalar() > 0:
                logger.debug(f"Challenge {challenge_id} already has participants")
                continue
            
            # Create participant records
            await session.execute(
                text("""
                    INSERT INTO challenge_participants 
                    (challenge_id, player_id, status, created_at) 
                    VALUES (:challenge_id, :player_id, :status, CURRENT_TIMESTAMP)
                """),
                [
                    {"challenge_id": challenge_id, "player_id": challenger_id, "status": participant_status},
                    {"challenge_id": challenge_id, "player_id": challenged_id, "status": participant_status}
                ]
            )
            migrated += 1
        
        await session.commit()
        logger.info(f"Successfully migrated {migrated} challenges")
        return True
        
    except Exception as e:
        logger.error(f"Error migrating existing challenges: {e}")
        await session.rollback()
        return False

async def verify_migration(session: AsyncSession) -> Dict[str, Any]:
    """Verify the migration was successful"""
    results = {}
    
    try:
        # Check PlayerEventStats columns
        if await table_exists(session, 'player_event_stats'):
            results['player_event_stats_columns'] = {
                'final_score': await column_exists(session, 'player_event_stats', 'final_score'),
                'shard_bonus': await column_exists(session, 'player_event_stats', 'shard_bonus'),
                'shop_bonus': await column_exists(session, 'player_event_stats', 'shop_bonus')
            }
        else:
            results['player_event_stats_columns'] = "Table not created yet"
        
        # Check ChallengeParticipant table
        results['challenge_participants_table'] = await table_exists(session, 'challenge_participants')
        
        if results['challenge_participants_table']:
            # Count migrated records
            result = await session.execute(
                text("SELECT COUNT(*) FROM challenge_participants")
            )
            results['challenge_participants_count'] = result.scalar()
        
        return results
        
    except Exception as e:
        logger.error(f"Error verifying migration: {e}")
        return {"error": str(e)}

async def main():
    """Run the migration"""
    logger.info(f"Starting {MIGRATION_NAME} migration...")
    
    # Create backup
    backup_path = await create_database_backup()
    logger.info(f"Backup created at: {backup_path}")
    
    # Create rollback script
    rollback_script = f"rollback_{MIGRATION_NAME}_{BACKUP_TIMESTAMP}.sh"
    with open(rollback_script, 'w') as f:
        f.write(f"""#!/bin/bash
# Rollback script for {MIGRATION_NAME}
echo "Rolling back {MIGRATION_NAME} migration..."
cp "{backup_path}" "tournament.db"
echo "Rollback complete. Database restored from {backup_path}"
""")
    os.chmod(rollback_script, 0o755)
    logger.info(f"Rollback script created: {rollback_script}")
    
    # Run migration
    engine = await get_engine()
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        success = True
        
        # Step 1: Add columns to PlayerEventStats
        logger.info("Step 1: Adding columns to PlayerEventStats...")
        if not await add_columns_to_player_event_stats(session):
            success = False
            logger.error("Failed to add columns to PlayerEventStats")
        
        # Step 2: Create ChallengeParticipant table
        if success:
            logger.info("Step 2: Creating ChallengeParticipant table...")
            if not await create_challenge_participants_table(session):
                success = False
                logger.error("Failed to create ChallengeParticipant table")
        
        # Step 3: Migrate existing challenges
        if success:
            logger.info("Step 3: Migrating existing challenges...")
            if not await migrate_existing_challenges(session):
                success = False
                logger.error("Failed to migrate existing challenges")
        
        # Verify migration
        if success:
            logger.info("Verifying migration...")
            results = await verify_migration(session)
            logger.info(f"Migration verification results: {results}")
            
            # Create migration report
            report_path = f"migration_report_{MIGRATION_NAME}_{BACKUP_TIMESTAMP}.txt"
            with open(report_path, 'w') as f:
                f.write(f"{MIGRATION_NAME} Migration Report\n")
                f.write(f"{'=' * 50}\n")
                f.write(f"Timestamp: {datetime.now()}\n")
                f.write(f"Backup: {backup_path}\n")
                f.write(f"Rollback Script: {rollback_script}\n")
                f.write(f"\nVerification Results:\n")
                for key, value in results.items():
                    f.write(f"  {key}: {value}\n")
            
            logger.info(f"Migration report saved to: {report_path}")
    
    await engine.dispose()
    
    if success:
        logger.info(f"{MIGRATION_NAME} migration completed successfully!")
    else:
        logger.error(f"{MIGRATION_NAME} migration failed! Run {rollback_script} to restore backup.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())