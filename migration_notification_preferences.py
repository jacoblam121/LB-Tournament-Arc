#!/usr/bin/env python3
"""
Migration: Add notification preferences to Player model
Date: 2025-07-01
Description: Adds dm_challenge_notifications boolean field to players table for opt-in DM notifications
"""

import asyncio
import sqlite3
from datetime import datetime
from bot.config import Config
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)

async def run_migration():
    """Add dm_challenge_notifications column to players table"""
    
    # Get database path from config
    db_path = Config.DATABASE_URL.replace('sqlite:///', '')
    
    logger.info("Starting notification preferences migration...")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(players)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'dm_challenge_notifications' in columns:
            logger.info("Column dm_challenge_notifications already exists, skipping migration")
            return
        
        # Add the new column with default value False (opt-in)
        cursor.execute("""
            ALTER TABLE players 
            ADD COLUMN dm_challenge_notifications BOOLEAN DEFAULT FALSE
        """)
        
        # Update existing players to have the default value explicitly set
        cursor.execute("""
            UPDATE players 
            SET dm_challenge_notifications = FALSE 
            WHERE dm_challenge_notifications IS NULL
        """)
        
        # Commit changes
        conn.commit()
        
        # Verify the migration
        cursor.execute("SELECT COUNT(*) FROM players WHERE dm_challenge_notifications = FALSE")
        updated_count = cursor.fetchone()[0]
        
        logger.info(f"Migration completed successfully!")
        logger.info(f"Added dm_challenge_notifications column to players table")
        logger.info(f"Set default value FALSE for {updated_count} existing players (opt-in)")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        if conn:
            conn.rollback()
        raise
    
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("Running notification preferences migration...")
    asyncio.run(run_migration())
    print("Migration completed!")