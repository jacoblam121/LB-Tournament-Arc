#!/usr/bin/env python3
"""
Apply Phase 2.4.3 database migrations for challenge management commands.

This script applies the necessary indexes to optimize challenge queries.
Run this after implementing the Phase 2.4.3 code changes.
"""

import sqlite3
import os
from pathlib import Path

def apply_migration():
    """Apply Phase 2.4.3 database indexes to SQLite database"""
    
    # Get database path
    db_path = Path("tournament.db")
    if not db_path.exists():
        print("❌ Error: tournament.db not found!")
        print("Make sure you're in the project root directory.")
        return False
    
    print("📦 Applying Phase 2.4.3 migrations to tournament.db...")
    
    try:
        # Connect to database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='challenges'")
        if not cursor.fetchone():
            print("❌ Error: challenges table not found!")
            print("Make sure the bot has been run at least once to create tables.")
            return False
        
        # Read and execute migration SQL
        migration_file = Path("migrations/phase_2_4_3_indexes_sqlite.sql")
        if not migration_file.exists():
            print("❌ Error: Migration file not found!")
            return False
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        # Begin transaction
        conn.execute("BEGIN TRANSACTION")
        
        # Execute each statement separately (SQLite requirement)
        statements = migration_sql.split(';')
        executed_statements = 0
        skipped_statements = 0
        total_statements = 0
        
        try:
            for statement in statements:
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    total_statements += 1
                    try:
                        print(f"  Executing: {statement[:120]}...")
                        cursor.execute(statement)
                        executed_statements += 1
                        print(f"    ✓ Success - newly created")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" in str(e):
                            print(f"    ⚠️  Column already exists, skipping...")
                            skipped_statements += 1
                        elif "already exists" in str(e):
                            print(f"    ⚠️  Index already exists, skipping...")
                            skipped_statements += 1
                        else:
                            print(f"    ❌ Error: {e}")
                            raise
                    except Exception as e:
                        print(f"    ❌ Unexpected error: {e}")
                        raise
            
            # Commit changes if all successful
            conn.commit()
            print(f"\n✅ Transaction committed successfully!")
        except Exception:
            # Rollback on any error
            conn.rollback()
            print(f"\n❌ Transaction rolled back due to errors.")
            raise
        
        # Verify indexes were created
        print(f"\n📊 Migration Summary:")
        print(f"  Total statements: {total_statements}")
        print(f"  Newly executed: {executed_statements}")
        print(f"  Already existed: {skipped_statements}")
        
        if executed_statements > 0:
            print(f"\n✅ Migration complete! Created {executed_statements} new indexes/columns.")
        elif skipped_statements == total_statements:
            print(f"\n✅ Migration already complete! All {total_statements} items already exist.")
        else:
            print(f"\n✅ Migration complete!")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error applying migration: {e}")
        return False

def verify_migration():
    """Verify the migration was applied correctly"""
    
    db_path = Path("tournament.db")
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        print("\n🔍 Verifying migration...")
        
        # Check for indexes
        required_indexes = [
            'idx_challenge_participant_lookup',
            'idx_challenge_status',
            'idx_cp_pending_challenger',
            'idx_cp_pending_challenged'
        ]
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        existing_indexes = [row[0] for row in cursor.fetchall()]
        
        missing = []
        for idx in required_indexes:
            if idx in existing_indexes:
                print(f"  ✅ {idx}")
            else:
                print(f"  ❌ {idx} - MISSING")
                missing.append(idx)
        
        # Check for updated_at column
        cursor.execute("PRAGMA table_info(challenges)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'updated_at' in columns:
            print(f"  ✅ updated_at column exists")
        else:
            print(f"  ❌ updated_at column - MISSING")
            missing.append('updated_at column')
        
        if missing:
            print(f"\n⚠️  Missing {len(missing)} items. Please check the migration.")
            return False
        else:
            print("\n✅ All migrations verified successfully!")
            return True
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("=== Phase 2.4.3 Migration Tool ===\n")
    
    if apply_migration():
        verify_migration()
        print("\n🎉 Phase 2.4.3 database is ready for testing!")
    else:
        print("\n❌ Migration failed. Please check the errors above.")