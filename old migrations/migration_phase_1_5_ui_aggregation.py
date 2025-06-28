#!/usr/bin/env python3
"""
Phase 1.5 Migration: UI Aggregation Layer

This migration adds base_event_name field and populates it for all existing events.
This enables UI aggregation while preserving the current data structure.

Usage:
    python migration_phase_1_5_ui_aggregation.py
"""

import sqlite3
import shutil
import os
import sys
from datetime import datetime
from typing import List, Tuple

# Add bot directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))
from bot.utils.event_name_parser import extract_base_event_name


def create_backup(db_path: str) -> str:
    """Create a backup of the database before migration"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"tournament_backup_ui_aggregation_phase1_5_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path


def add_base_event_name_column(conn: sqlite3.Connection) -> None:
    """Add the base_event_name column to events table"""
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(events)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'base_event_name' in columns:
        print("⚠️  base_event_name column already exists")
        return
    
    # Add the column
    cursor.execute("""
        ALTER TABLE events 
        ADD COLUMN base_event_name VARCHAR(200)
    """)
    
    # Create index for better query performance
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_base_event_name 
        ON events(base_event_name)
    """)
    
    print("✅ Added base_event_name column and index")


def populate_base_event_names(conn: sqlite3.Connection) -> Tuple[int, List[str]]:
    """Populate base_event_name for all existing events"""
    cursor = conn.cursor()
    
    # Get all events
    cursor.execute("SELECT id, name FROM events")
    events = cursor.fetchall()
    
    updated_count = 0
    unparseable_events = []
    
    for event_id, event_name in events:
        base_name = extract_base_event_name(event_name)
        
        # Update the event
        cursor.execute("""
            UPDATE events 
            SET base_event_name = ? 
            WHERE id = ?
        """, (base_name, event_id))
        
        updated_count += 1
        
        # Track if the name wasn't changed (might indicate unparseable format)
        if base_name == event_name and any(char in event_name for char in ['(', ')']):
            unparseable_events.append(event_name)
    
    conn.commit()
    return updated_count, unparseable_events


def verify_migration(conn: sqlite3.Connection) -> None:
    """Verify the migration was successful"""
    cursor = conn.cursor()
    
    # Check total events
    cursor.execute("SELECT COUNT(*) FROM events")
    total_events = cursor.fetchone()[0]
    
    # Check events with base_event_name
    cursor.execute("SELECT COUNT(*) FROM events WHERE base_event_name IS NOT NULL")
    events_with_base = cursor.fetchone()[0]
    
    # Check aggregation example
    cursor.execute("""
        SELECT base_event_name, COUNT(*) as count 
        FROM events 
        WHERE base_event_name IS NOT NULL
        GROUP BY base_event_name 
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT 5
    """)
    aggregated_examples = cursor.fetchall()
    
    print(f"\n📊 Migration Verification:")
    print(f"   Total events: {total_events}")
    print(f"   Events with base_event_name: {events_with_base}")
    print(f"   Coverage: {events_with_base/total_events*100:.1f}%")
    
    if aggregated_examples:
        print(f"\n   Top aggregated events:")
        for base_name, count in aggregated_examples:
            print(f"   - {base_name}: {count} variations")


def create_rollback_script(backup_path: str) -> str:
    """Create a rollback script in case we need to revert"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback_script = f"rollback_ui_aggregation_phase1_5_{timestamp}.sh"
    
    with open(rollback_script, 'w') as f:
        f.write(f"""#!/bin/bash
# Rollback script for Phase 1.5 UI Aggregation migration
# Generated at: {datetime.now()}

echo "🔄 Rolling back Phase 1.5 migration..."

# Restore from backup
cp "{backup_path}" tournament.db

echo "✅ Rollback complete! Database restored from backup."
echo "Note: The base_event_name column has been removed."
""")
    
    os.chmod(rollback_script, 0o755)
    print(f"✅ Rollback script created: {rollback_script}")
    return rollback_script


def main():
    """Main migration function"""
    db_path = "tournament.db"
    
    print("🚀 Phase 1.5 Migration: UI Aggregation Layer")
    print("=" * 50)
    
    # Create backup
    backup_path = create_backup(db_path)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    try:
        # Add the new column
        add_base_event_name_column(conn)
        
        # Populate base event names
        print("\n📝 Populating base_event_name values...")
        updated_count, unparseable = populate_base_event_names(conn)
        
        print(f"✅ Updated {updated_count} events")
        
        if unparseable:
            print(f"\n⚠️  Found {len(unparseable)} events with parentheses that weren't parsed:")
            for event in unparseable[:5]:  # Show first 5
                print(f"   - {event}")
            if len(unparseable) > 5:
                print(f"   ... and {len(unparseable) - 5} more")
        
        # Verify migration
        verify_migration(conn)
        
        # Create rollback script
        rollback_script = create_rollback_script(backup_path)
        
        # Create migration report
        report_path = f"migration_report_ui_aggregation_phase1_5_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_path, 'w') as f:
            f.write(f"""
========================================
Phase 1.5 Migration: SUCCESS
========================================
Timestamp: {datetime.now()}
Changes Made:
- Added base_event_name column to events table
- Created index on base_event_name
- Populated base names for {updated_count} events
- {len(unparseable)} events may need manual review

Backup: {backup_path}
Rollback: {rollback_script}

Next Steps:
- Test UI aggregation in /list-events command
- Update CSV import to populate base_event_name
- Monitor for any parsing issues
========================================
""")
        
        print(f"\n✅ Migration report: {report_path}")
        print("\n🎉 Phase 1.5 migration completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        print(f"💾 Database backup available at: {backup_path}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()