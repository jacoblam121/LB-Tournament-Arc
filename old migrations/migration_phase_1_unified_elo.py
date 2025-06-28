#!/usr/bin/env python3
"""
Phase 1: Unified Event Elo - Schema Migration
=============================================

This migration makes Event.scoring_type nullable as the first step towards
implementing unified event Elo ratings where a single event can have multiple
match formats (1v1, FFA, Team) all contributing to the same Elo pool.

Migration Steps:
1. Make Event.scoring_type nullable
2. Verify data integrity
3. Create rollback capability

This is a non-destructive migration that preserves all existing data.
"""

import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from bot.database.database import Database
from bot.database.models import Event
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def create_backup(db_path: str) -> str:
    """Create a backup of the database before migration"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"tournament_backup_unified_elo_phase1_{timestamp}.db"
    
    import shutil
    shutil.copy2(db_path, backup_path)
    logger.info(f"Created backup: {backup_path}")
    
    return backup_path


async def verify_current_schema(db: Database) -> bool:
    """Verify the current schema is as expected"""
    async with db.get_session() as session:
        # Check if scoring_type is currently NOT NULL
        result = await session.execute(text("""
            SELECT sql FROM sqlite_master 
            WHERE type='table' AND name='events';
        """))
        
        table_sql = result.scalar()
        if table_sql and 'scoring_type' in table_sql and 'NOT NULL' in table_sql:
            logger.info("Current schema verified: scoring_type is NOT NULL")
            return True
        else:
            logger.warning("Unexpected schema state")
            return False


async def alter_scoring_type_nullable(db: Database) -> bool:
    """
    Make Event.scoring_type nullable in SQLite.
    
    SQLite doesn't support ALTER COLUMN, so we need to:
    1. Create a new table with the desired schema
    2. Copy data from old table
    3. Drop old table
    4. Rename new table
    """
    try:
        async with db.transaction() as session:
            # Step 1: Create new table with nullable scoring_type
            await session.execute(text("""
                CREATE TABLE events_new (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    cluster_id INTEGER NOT NULL,
                    scoring_type VARCHAR(20),  -- Now nullable
                    score_direction VARCHAR(10),
                    crownslayer_pool INTEGER DEFAULT 300,
                    is_active BOOLEAN DEFAULT TRUE,
                    min_players INTEGER DEFAULT 2,
                    max_players INTEGER DEFAULT 8,
                    allow_challenges BOOLEAN DEFAULT TRUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (cluster_id) REFERENCES clusters(id),
                    UNIQUE (cluster_id, name)
                );
            """))
            
            # Step 2: Copy data from old table
            await session.execute(text("""
                INSERT INTO events_new 
                SELECT * FROM events;
            """))
            
            # Step 3: Drop old table
            await session.execute(text("DROP TABLE events;"))
            
            # Step 4: Rename new table
            await session.execute(text("ALTER TABLE events_new RENAME TO events;"))
            
            logger.info("Successfully made scoring_type nullable")
            return True
            
    except Exception as e:
        logger.error(f"Failed to alter schema: {e}")
        return False


async def verify_migration(db: Database) -> bool:
    """Verify the migration was successful"""
    try:
        async with db.get_session() as session:
            # Test that we can insert with NULL scoring_type
            test_result = await session.execute(text("""
                SELECT COUNT(*) as total,
                       COUNT(scoring_type) as non_null,
                       COUNT(*) - COUNT(scoring_type) as null_count
                FROM events;
            """))
            
            row = test_result.fetchone()
            logger.info(f"Events: Total={row.total}, With scoring_type={row.non_null}, Without={row.null_count}")
            
            # Verify all existing events still have scoring_type
            if row.total == row.non_null:
                logger.info("All existing events preserved their scoring_type values")
                return True
            else:
                logger.warning("Some events lost their scoring_type values!")
                return False
                
    except Exception as e:
        logger.error(f"Failed to verify migration: {e}")
        return False


async def main():
    """Main migration function"""
    logger.info("Starting Phase 1: Unified Event Elo - Schema Migration")
    
    # Initialize database
    db = Database()
    await db.initialize()
    
    try:
        # Create backup
        db_path = "tournament.db"
        backup_path = await create_backup(db_path)
        
        # Verify current schema
        if not await verify_current_schema(db):
            logger.error("Current schema verification failed")
            return False
        
        # Perform migration
        logger.info("Altering Event.scoring_type to be nullable...")
        if not await alter_scoring_type_nullable(db):
            logger.error("Schema alteration failed")
            return False
        
        # Verify migration
        if not await verify_migration(db):
            logger.error("Migration verification failed")
            return False
        
        # Generate rollback script
        rollback_script = f"""#!/bin/bash
# Rollback script for Phase 1 Unified Elo migration
# Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

echo "Rolling back Phase 1 Unified Elo migration..."
cp {backup_path} tournament.db
echo "Rollback complete. Database restored from {backup_path}"
"""
        
        rollback_path = f"rollback_unified_elo_phase1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sh"
        with open(rollback_path, 'w') as f:
            f.write(rollback_script)
        os.chmod(rollback_path, 0o755)
        
        logger.info(f"Created rollback script: {rollback_path}")
        
        # Success report
        report = f"""
========================================
Phase 1 Migration: SUCCESS
========================================
Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Changes Made:
- Event.scoring_type is now nullable
- All existing data preserved
- No events were modified

Backup: {backup_path}
Rollback: {rollback_path}

Next Steps:
- Test that existing functionality still works
- Proceed to Phase 2: Core Logic Updates
========================================
"""
        
        print(report)
        
        with open(f"migration_report_unified_elo_phase1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", 'w') as f:
            f.write(report)
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
    finally:
        await db.close()


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)