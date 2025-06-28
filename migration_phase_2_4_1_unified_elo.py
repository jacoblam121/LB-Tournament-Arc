#!/usr/bin/env python3
"""
Phase 2.4.1: Unified Elo Architecture Fix

Consolidates separate events per scoring type into unified events per base game.
Moves scoring_type from Event level to Match level.

CRITICAL: Fixes architectural violation where separate events per scoring type
(e.g., "Diep (1v1)", "Diep (Team)", "Diep (FFA)") create fragmented Elo ratings
instead of unified Elo per base game.
"""

import sqlite3
import logging
import json
from datetime import datetime
import shutil
import os
from pathlib import Path
from typing import Dict, List, Set
from collections import defaultdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'migration_phase_2_4_1_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
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
    backup_path = f"{db_path.stem}_backup_phase_2_4_1_{timestamp}{db_path.suffix}"
    shutil.copy2(db_path, backup_path)
    logger.info(f"✅ Backup created: {backup_path}")
    return backup_path

def analyze_current_state(conn):
    """Analyze current fragmented events and PlayerEventStats"""
    logger.info("🔍 Analyzing current database state...")
    
    # Count fragmented events
    cursor = conn.execute("""
        SELECT base_event_name, COUNT(*) as event_count 
        FROM events 
        WHERE base_event_name IS NOT NULL 
        GROUP BY base_event_name 
        ORDER BY event_count DESC
    """)
    fragmented_events = cursor.fetchall()
    
    total_events = sum(count for _, count in fragmented_events)
    unique_base_games = len(fragmented_events)
    
    logger.info(f"Current state: {total_events} events, {unique_base_games} unique base games")
    
    # Count PlayerEventStats
    cursor = conn.execute("SELECT COUNT(*) FROM player_event_stats")
    total_stats = cursor.fetchone()[0]
    
    cursor = conn.execute("SELECT COUNT(DISTINCT player_id) FROM player_event_stats")
    unique_players = cursor.fetchone()[0]
    
    logger.info(f"PlayerEventStats: {total_stats} records for {unique_players} players")
    
    return {
        'fragmented_events': fragmented_events,
        'total_events': total_events,
        'unique_base_games': unique_base_games,
        'total_stats': total_stats,
        'unique_players': unique_players
    }

def create_event_consolidation_map(conn):
    """Create mapping from old fragmented events to new unified events"""
    logger.info("📋 Creating event consolidation mapping...")
    
    # Get all events grouped by base_event_name
    cursor = conn.execute("""
        SELECT id, name, base_event_name, scoring_type, cluster_id, 
               score_direction, crownslayer_pool, is_active, allow_challenges,
               min_players, max_players, created_at
        FROM events 
        WHERE base_event_name IS NOT NULL
        ORDER BY base_event_name, scoring_type
    """)
    
    events_data = cursor.fetchall()
    consolidation_map = {}
    event_groups = defaultdict(list)
    
    # Group events by base name
    for event_data in events_data:
        event_id, name, base_name, scoring_type = event_data[:4]
        event_groups[base_name].append(event_data)
    
    # Create consolidation mapping
    for base_name, events in event_groups.items():
        if len(events) > 1:
            # Multiple events for this base game - need consolidation
            # Use the first event as the primary unified event
            primary_event = events[0]
            primary_id = primary_event[0]
            
            consolidation_map[base_name] = {
                'primary_event_id': primary_id,
                'primary_event_data': primary_event,
                'redundant_events': events[1:],
                'supported_scoring_types': [e[3] for e in events]  # scoring_type
            }
        else:
            # Single event - no consolidation needed but include in map
            event = events[0]
            consolidation_map[base_name] = {
                'primary_event_id': event[0],
                'primary_event_data': event,
                'redundant_events': [],
                'supported_scoring_types': [event[3]]
            }
    
    logger.info(f"Created consolidation map for {len(consolidation_map)} base games")
    return consolidation_map

def add_required_columns(conn):
    """Add required columns to tables"""
    logger.info("🔧 Adding required columns...")
    
    # Add scoring_type to matches table
    if not column_exists(conn, 'matches', 'scoring_type'):
        conn.execute("""
            ALTER TABLE matches 
            ADD COLUMN scoring_type VARCHAR(20) DEFAULT '1v1';
        """)
        logger.info("✅ Added scoring_type column to matches table")
    else:
        logger.info("ℹ️  scoring_type column already exists in matches table")
    
    # Add supported_scoring_types to events table
    if not column_exists(conn, 'events', 'supported_scoring_types'):
        conn.execute("""
            ALTER TABLE events 
            ADD COLUMN supported_scoring_types VARCHAR(100);
        """)
        logger.info("✅ Added supported_scoring_types column to events table")
    else:
        logger.info("ℹ️  supported_scoring_types column already exists in events table")

def consolidate_events(conn, consolidation_map):
    """Consolidate fragmented events into unified events"""
    logger.info("🔄 Consolidating fragmented events...")
    
    events_to_deactivate = []
    events_consolidated = 0
    
    for base_name, mapping in consolidation_map.items():
        redundant_events = mapping['redundant_events']
        
        if redundant_events:
            primary_id = mapping['primary_event_id']
            supported_types = mapping['supported_scoring_types']
            
            # Update primary event name to remove suffix
            conn.execute("""
                UPDATE events 
                SET name = ?, 
                    supported_scoring_types = ?
                WHERE id = ?
            """, (base_name, ','.join(supported_types), primary_id))
            
            # Mark redundant events for deactivation
            for redundant_event in redundant_events:
                redundant_id = redundant_event[0]
                events_to_deactivate.append(redundant_id)
                events_consolidated += 1
    
    logger.info(f"Updated {len(consolidation_map)} primary events with unified names")
    logger.info(f"Marked {events_consolidated} redundant events for deactivation")
    
    return events_to_deactivate

def consolidate_player_event_stats(conn, consolidation_map):
    """Consolidate PlayerEventStats records for unified events"""
    logger.info("📊 Consolidating PlayerEventStats records...")
    
    stats_consolidated = 0
    stats_deleted = 0
    
    for base_name, mapping in consolidation_map.items():
        redundant_events = mapping['redundant_events']
        
        if redundant_events:
            primary_event_id = mapping['primary_event_id']
            redundant_event_ids = [event[0] for event in redundant_events]
            
            # Get all affected players for this base game
            placeholders = ','.join(['?'] * (len(redundant_event_ids) + 1))
            cursor = conn.execute(f"""
                SELECT DISTINCT player_id 
                FROM player_event_stats 
                WHERE event_id IN ({placeholders})
            """, [primary_event_id] + redundant_event_ids)
            
            affected_players = [row[0] for row in cursor.fetchall()]
            
            # Consolidate stats for each affected player
            for player_id in affected_players:
                # Get all stats for this player and base game
                cursor = conn.execute(f"""
                    SELECT event_id, raw_elo, scoring_elo, matches_played, wins, losses, draws
                    FROM player_event_stats 
                    WHERE player_id = ? AND event_id IN ({placeholders})
                    ORDER BY event_id
                """, [player_id] + [primary_event_id] + redundant_event_ids)
                
                player_stats = cursor.fetchall()
                
                if len(player_stats) > 1:
                    # Multiple stats records to consolidate
                    total_matches = sum(stat[3] for stat in player_stats)  # matches_played
                    total_wins = sum(stat[4] for stat in player_stats)     # wins
                    total_losses = sum(stat[5] for stat in player_stats)   # losses
                    total_draws = sum(stat[6] for stat in player_stats)    # draws
                    
                    if total_matches > 0:
                        # Calculate weighted average Elo
                        weighted_raw_elo = sum(stat[1] * stat[3] for stat in player_stats) / total_matches
                        weighted_scoring_elo = sum(stat[2] * stat[3] for stat in player_stats) / total_matches
                    else:
                        # No matches played - use default or first record's Elo
                        weighted_raw_elo = player_stats[0][1]
                        weighted_scoring_elo = player_stats[0][2]
                    
                    # Update primary record with consolidated stats
                    conn.execute("""
                        UPDATE player_event_stats 
                        SET raw_elo = ?, scoring_elo = ?, matches_played = ?, 
                            wins = ?, losses = ?, draws = ?
                        WHERE player_id = ? AND event_id = ?
                    """, (
                        int(weighted_raw_elo), int(weighted_scoring_elo), total_matches,
                        total_wins, total_losses, total_draws, player_id, primary_event_id
                    ))
                    
                    # Delete redundant stats records
                    for redundant_id in redundant_event_ids:
                        conn.execute("""
                            DELETE FROM player_event_stats 
                            WHERE player_id = ? AND event_id = ?
                        """, (player_id, redundant_id))
                        stats_deleted += 1
                    
                    stats_consolidated += 1
    
    logger.info(f"✅ Consolidated stats for {stats_consolidated} players")
    logger.info(f"✅ Deleted {stats_deleted} redundant PlayerEventStats records")

def deactivate_redundant_events(conn, events_to_deactivate):
    """Deactivate redundant events instead of deleting them"""
    logger.info("🔒 Deactivating redundant events...")
    
    if not events_to_deactivate:
        logger.info("ℹ️  No redundant events to deactivate")
        return
    
    placeholders = ','.join(['?'] * len(events_to_deactivate))
    conn.execute(f"""
        UPDATE events 
        SET is_active = 0, 
            allow_challenges = 0,
            name = name || ' [DEPRECATED-CONSOLIDATED]'
        WHERE id IN ({placeholders})
    """, events_to_deactivate)
    
    logger.info(f"✅ Deactivated {len(events_to_deactivate)} redundant events")

def create_legacy_backup_tables(conn):
    """Create backup tables for rollback capability"""
    logger.info("💾 Creating legacy backup tables...")
    
    # Drop existing legacy tables if they exist
    conn.execute("DROP TABLE IF EXISTS events_legacy_2_4_1")
    conn.execute("DROP TABLE IF EXISTS player_event_stats_legacy_2_4_1")
    
    # Backup events table
    conn.execute("""
        CREATE TABLE events_legacy_2_4_1 AS 
        SELECT * FROM events
    """)
    
    # Backup player_event_stats table
    conn.execute("""
        CREATE TABLE player_event_stats_legacy_2_4_1 AS 
        SELECT * FROM player_event_stats
    """)
    
    logger.info("✅ Created legacy backup tables")

def verify_consolidation(conn):
    """Verify the consolidation was successful"""
    logger.info("🔍 Verifying consolidation results...")
    
    # Count remaining active events per base game
    cursor = conn.execute("""
        SELECT base_event_name, COUNT(*) as active_count
        FROM events 
        WHERE is_active = 1 AND base_event_name IS NOT NULL
        GROUP BY base_event_name
        HAVING COUNT(*) > 1
    """)
    
    duplicates = cursor.fetchall()
    if duplicates:
        logger.warning(f"⚠️  Found {len(duplicates)} base games with multiple active events:")
        for base_name, count in duplicates:
            logger.warning(f"  - {base_name}: {count} events")
    else:
        logger.info("✅ No duplicate active events found")
    
    # Count total consolidated events
    cursor = conn.execute("""
        SELECT COUNT(*) FROM events WHERE is_active = 1
    """)
    active_events = cursor.fetchone()[0]
    
    cursor = conn.execute("""
        SELECT COUNT(*) FROM events WHERE is_active = 0 AND name LIKE '%[DEPRECATED-CONSOLIDATED]'
    """)
    deprecated_events = cursor.fetchone()[0]
    
    # Count consolidated PlayerEventStats
    cursor = conn.execute("SELECT COUNT(*) FROM player_event_stats")
    total_stats = cursor.fetchone()[0]
    
    logger.info(f"Final state: {active_events} active events, {deprecated_events} deprecated events")
    logger.info(f"Final PlayerEventStats: {total_stats} records")

def create_rollback_script(backup_path, consolidation_map):
    """Create a rollback script for emergency recovery"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    rollback_script = f"""#!/bin/bash
# Rollback script for Phase 2.4.1 migration
# Generated: {datetime.now()}
# Backup: {backup_path}

DB_PATH="tournament.db"
BACKUP_PATH="{backup_path}"

echo "🔄 Rolling back Phase 2.4.1 unified Elo migration..."

# Safety check
if [ ! -f "$BACKUP_PATH" ]; then
    echo "❌ Backup file not found: $BACKUP_PATH"
    exit 1
fi

sqlite3 "$DB_PATH" <<EOF
PRAGMA foreign_keys = OFF;

-- Restore events table from backup
DROP TABLE IF EXISTS events;
CREATE TABLE events AS SELECT * FROM events_legacy_2_4_1;

-- Restore player_event_stats table from backup  
DROP TABLE IF EXISTS player_event_stats;
CREATE TABLE player_event_stats AS SELECT * FROM player_event_stats_legacy_2_4_1;

-- Remove scoring_type column from matches (if it exists)
-- Note: This requires table recreation in SQLite
CREATE TABLE matches_new AS 
SELECT id, event_id, match_format, status, created_by, started_at, completed_at,
       admin_notes, created_at, updated_at
FROM matches;

DROP TABLE matches;
ALTER TABLE matches_new RENAME TO matches;

-- Recreate indexes (add your specific indexes here)
CREATE INDEX IF NOT EXISTS idx_events_cluster ON events(cluster_id);
CREATE INDEX IF NOT EXISTS idx_events_base_name ON events(base_event_name);
CREATE INDEX IF NOT EXISTS idx_player_event_stats_player ON player_event_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_event_stats_event ON player_event_stats(event_id);

-- Clean up legacy tables
DROP TABLE IF EXISTS events_legacy_2_4_1;
DROP TABLE IF EXISTS player_event_stats_legacy_2_4_1;

PRAGMA foreign_keys = ON;
EOF

echo "✅ Rollback complete"
echo "⚠️  Note: You may need to repopulate from CSV to get clean event structure"
"""
    
    rollback_path = f"rollback_phase_2_4_1_{timestamp}.sh"
    with open(rollback_path, 'w') as f:
        f.write(rollback_script)
    os.chmod(rollback_path, 0o755)
    
    logger.info(f"✅ Rollback script created: {rollback_path}")
    return rollback_path

def migrate_database(db_path, backup_path):
    """Execute the unified Elo migration"""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    
    try:
        # Check SQLite version
        check_sqlite_version(conn)
        
        # Analyze current state
        current_state = analyze_current_state(conn)
        
        logger.info("🔧 Starting unified Elo migration...")
        
        # Step 1: Create legacy backup tables
        create_legacy_backup_tables(conn)
        
        # Step 2: Add required columns
        add_required_columns(conn)
        
        # Step 3: Create event consolidation mapping
        consolidation_map = create_event_consolidation_map(conn)
        
        # Step 4: Consolidate events
        events_to_deactivate = consolidate_events(conn, consolidation_map)
        
        # Step 5: Consolidate PlayerEventStats
        consolidate_player_event_stats(conn, consolidation_map)
        
        # Step 6: Deactivate redundant events
        deactivate_redundant_events(conn, events_to_deactivate)
        
        # Step 7: Verify consolidation
        verify_consolidation(conn)
        
        # Step 8: Create rollback script
        rollback_path = create_rollback_script(backup_path, consolidation_map)
        
        conn.commit()
        logger.info("✅ Migration completed successfully!")
        
        # Final summary
        final_state = analyze_current_state(conn)
        events_reduced = current_state['total_events'] - final_state['total_events']
        stats_reduced = current_state['total_stats'] - final_state['total_stats']
        
        logger.info(f"📊 Migration summary:")
        logger.info(f"  - Events: {current_state['total_events']} → {final_state['total_events']} (-{events_reduced})")
        logger.info(f"  - PlayerEventStats: {current_state['total_stats']} → {final_state['total_stats']} (-{stats_reduced})")
        logger.info(f"  - Backup: {backup_path}")
        logger.info(f"  - Rollback: {rollback_path}")
        
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
        print("✅ PHASE 2.4.1 UNIFIED ELO MIGRATION COMPLETE")
        print("="*60)
        print(f"Database: {db_path}")
        print(f"Backup: {backup_path}")
        print("\nNext steps:")
        print("1. Update populate_from_csv.py to create unified events")
        print("2. Update challenge command to use unified event lookup")
        print("3. Test challenge creation with unified Elo system")
        print("4. Run comprehensive test suite")
        
    except Exception as e:
        print(f"\n❌ MIGRATION FAILED: {e}")
        print(f"Database backup available at: {backup_path}")
        exit(1)