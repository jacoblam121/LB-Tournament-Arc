#!/usr/bin/env python3
"""
Phase 2.1.1: Add role field to challenge_participants table

This migration adds a role field to distinguish between challenge initiators
and recipients, enabling proper N-player challenge logic.
"""
import sqlite3
import logging
from datetime import datetime
import shutil
import os
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'migration_phase_2_1_1_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def check_sqlite_version(conn):
    """Check if SQLite version supports required operations"""
    cursor = conn.execute("SELECT sqlite_version();")
    version = cursor.fetchone()[0]
    logger.info(f"SQLite version: {version}")
    major, minor, patch = map(int, version.split('.'))
    
    if major < 3 or (major == 3 and minor < 35):
        raise RuntimeError(f"SQLite {version} is too old. Need 3.35.0+ for ALTER TABLE support.")
    
    return version

def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    cursor = conn.execute(f"PRAGMA table_info({table_name});")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def create_backup(db_path):
    """Create a backup of the database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path.stem}_backup_phase_2_1_1_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    logger.info(f"✅ Backup created: {backup_path}")
    return backup_path

def migrate_database(db_path, backup_path):
    """Execute the migration
    
    Args:
        db_path: Path to the database file
        backup_path: Path to the backup file created before migration
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    
    try:
        # Check SQLite version
        check_sqlite_version(conn)
        
        # Check if migration already applied
        if column_exists(conn, 'challenge_participants', 'role'):
            logger.info("ℹ️  Migration already applied - role column exists")
            return
        
        logger.info("🔧 Starting migration...")
        
        # Step 1: Add nullable role column
        logger.info("Step 1: Adding role column (nullable)...")
        conn.execute("""
            ALTER TABLE challenge_participants 
            ADD COLUMN role VARCHAR(10);
        """)
        logger.info("✅ Role column added")
        
        # Step 2: Backfill existing data
        logger.info("Step 2: Backfilling existing participants...")
        
        # Set all participants to 'challenged' initially
        conn.execute("""
            UPDATE challenge_participants 
            SET role = 'challenged' 
            WHERE role IS NULL;
        """)
        
        # Identify and update challenge initiators
        # Strategy: First participant (lowest ID) per challenge is the challenger
        # Note: This assumes chronological participant creation. For better accuracy,
        # consider using created_at timestamp if available in future iterations.
        conn.execute("""
            UPDATE challenge_participants
            SET role = 'challenger'
            WHERE id IN (
                SELECT MIN(id) 
                FROM challenge_participants 
                GROUP BY challenge_id
            );
        """)
        
        # Verify backfill
        cursor = conn.execute("""
            SELECT COUNT(*) FROM challenge_participants WHERE role IS NULL;
        """)
        null_count = cursor.fetchone()[0]
        
        if null_count > 0:
            raise RuntimeError(f"Backfill failed: {null_count} participants still have NULL role")
        
        logger.info("✅ All participants have role assigned")
        
        # Log statistics
        cursor = conn.execute("""
            SELECT role, COUNT(*) as count 
            FROM challenge_participants 
            GROUP BY role;
        """)
        for role, count in cursor:
            logger.info(f"  - {role}: {count} participants")
        
        # Step 3: Add NOT NULL constraint would require table recreation in SQLite
        # We'll handle this constraint at the application level instead
        logger.info("ℹ️  Note: NOT NULL constraint will be enforced at application level")
        logger.info("    Future migration can recreate table with proper constraints if needed")
        
        # Create rollback script
        rollback_script = f"""#!/bin/bash
# Rollback script for Phase 2.1.1 migration
# Generated: {datetime.now()}

DB_PATH="{db_path}"
BACKUP_PATH="{backup_path}"

echo "Rolling back Phase 2.1.1 migration..."
sqlite3 "$DB_PATH" <<EOF
PRAGMA foreign_keys = OFF;

-- Remove the role column
CREATE TABLE challenge_participants_new (
    id INTEGER PRIMARY KEY,
    challenge_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    responded_at DATETIME,
    team_id VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(challenge_id) REFERENCES challenges(id),
    FOREIGN KEY(player_id) REFERENCES players(id),
    UNIQUE(challenge_id, player_id)
);

INSERT INTO challenge_participants_new 
SELECT id, challenge_id, player_id, status, responded_at, team_id, created_at
FROM challenge_participants;

DROP TABLE challenge_participants;
ALTER TABLE challenge_participants_new RENAME TO challenge_participants;

-- Recreate indexes
CREATE INDEX idx_challenge_participants_challenge ON challenge_participants(challenge_id);
CREATE INDEX idx_challenge_participants_player ON challenge_participants(player_id);
CREATE INDEX idx_challenge_participants_status ON challenge_participants(status);

PRAGMA foreign_keys = ON;
EOF

echo "✅ Rollback complete"
"""
        
        rollback_path = f"rollback_phase_2_1_1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sh"
        with open(rollback_path, 'w') as f:
            f.write(rollback_script)
        os.chmod(rollback_path, 0o755)
        logger.info(f"✅ Rollback script created: {rollback_path}")
        
        conn.commit()
        logger.info("✅ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    db_path = Path("tournament.db")
    
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        exit(1)
    
    # Create backup
    backup_path = create_backup(db_path)
    
    try:
        # Run migration
        migrate_database(db_path, backup_path)
        
        print("\n" + "="*60)
        print("✅ PHASE 2.1.1 MIGRATION COMPLETE")
        print("="*60)
        print(f"Database: {db_path}")
        print(f"Backup: {backup_path}")
        print("\nNext steps:")
        print("1. Update models.py with role field (nullable=False, default=ChallengeRole.CHALLENGED)")
        print("2. Test bot startup and challenge operations")
        print("3. Implement ChallengeOperations service with role awareness")
        
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        print(f"Database backup available at: {backup_path}")
        exit(1)