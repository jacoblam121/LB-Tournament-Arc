#!/usr/bin/env python3
"""
Phase 2A2 Schema Migration: Add Match and MatchParticipant Tables

This migration script adds the new Match and MatchParticipant tables to support
N-player matches while preserving all existing Challenge functionality.

Migration Type: Additive (Zero Risk)
- Adds new tables: matches, match_participants  
- Updates EloHistory with nullable match_id column
- Preserves all existing data and functionality

Usage:
    python migration_phase_2a2_schema.py
"""

import asyncio
import os
import sys
import traceback
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.database.database import Database
from bot.database.models import Base
from bot.config import Config
from sqlalchemy import text  # Required for SQLAlchemy 2.0+ raw SQL

class Phase2A2SchemaMigration:
    """Migration handler for Phase 2A2 schema changes"""
    
    def __init__(self):
        self.db = Database()
    
    def print_header(self, message: str):
        """Print a formatted header"""
        print(f"\n{'='*60}")
        print(f" {message}")
        print(f"{'='*60}")
    
    def print_success(self, message: str):
        """Print a success message"""
        print(f"✅ {message}")
    
    def print_error(self, message: str):
        """Print an error message"""
        print(f"❌ {message}")
    
    def print_info(self, message: str):
        """Print an info message"""
        print(f"ℹ️  {message}")
    
    def print_warning(self, message: str):
        """Print a warning message"""
        print(f"⚠️  {message}")
    
    async def run_migration(self):
        """Execute the Phase 2A2 schema migration"""
        self.print_header("Phase 2A2 Schema Migration: Match Models Addition")
        
        try:
            # Step 1: Backup verification
            await self.verify_backup()
            
            # Step 2: Initialize database with new schema
            await self.apply_schema_changes()
            
            # Step 3: Verify migration success
            await self.verify_migration()
            
            self.print_success("🎉 Phase 2A2 Schema Migration Completed Successfully!")
            print("\n✅ New tables added: matches, match_participants")
            print("✅ EloHistory updated with match_id support")
            print("✅ All existing data preserved")
            print("✅ Backward compatibility maintained")
            print("\n🚀 Ready for Phase 2A2 Subphase 2: Match Operations")
            
            return True
            
        except Exception as e:
            self.print_error(f"Migration failed: {e}")
            traceback.print_exc()
            return False
            
        finally:
            await self.cleanup()
    
    async def verify_backup(self):
        """Verify that a backup exists before proceeding"""
        backup_file = "tournament_backup_phase_2a2.db"
        
        if not os.path.exists(backup_file):
            self.print_warning(f"Backup file {backup_file} not found")
            self.print_info("Creating backup now...")
            
            # Create backup if it doesn't exist
            if os.path.exists("tournament.db"):
                import shutil
                shutil.copy2("tournament.db", backup_file)
                self.print_success(f"Backup created: {backup_file}")
            else:
                self.print_info("No existing tournament.db found - fresh installation")
        else:
            self.print_success(f"Backup verified: {backup_file}")
    
    async def apply_schema_changes(self):
        """Apply the new schema changes"""
        self.print_info("Applying Phase 2A2 schema changes...")
        
        # Initialize database - this will create new tables
        await self.db.initialize()
        
        # Manually handle ALTER TABLE for existing databases
        async with self.db.get_session() as session:
            await self._add_match_id_to_elo_history(session)
        
        self.print_success("Schema changes applied successfully")
        self.print_info("New tables created:")
        print("  - matches (Match model)")
        print("  - match_participants (MatchParticipant model)")
        print("  - EloHistory updated with match_id column")
    
    async def _add_match_id_to_elo_history(self, session):
        """Manually add the match_id column to elo_history if it doesn't exist."""
        self.print_info("Checking if 'elo_history' table needs migration...")
        
        try:
            # Check if match_id column already exists
            result = await session.execute(text("PRAGMA table_info(elo_history)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'match_id' not in columns:
                self.print_warning("'match_id' column not found in 'elo_history'. Applying ALTER TABLE.")
                try:
                    await session.execute(text("ALTER TABLE elo_history ADD COLUMN match_id INTEGER REFERENCES matches(id)"))
                    await session.commit()
                    self.print_success("Successfully added 'match_id' column to 'elo_history' table.")
                except Exception as e:
                    self.print_error(f"Failed to add 'match_id' column: {e}")
                    raise
            else:
                self.print_success("'match_id' column already exists in 'elo_history'. No migration needed.")
                
        except Exception as e:
            # If we can't check the schema, the table might not exist yet (fresh install)
            if "no such table" in str(e).lower():
                self.print_info("'elo_history' table not found - fresh installation, will be created by initialize()")
            else:
                raise
    
    async def verify_migration(self):
        """Verify that the migration completed successfully"""
        self.print_info("Verifying migration success...")
        
        async with self.db.get_session() as session:
            # Test 1: Verify new tables exist and are accessible
            try:
                from bot.database.models import Match, MatchParticipant, MatchStatus, MatchFormat
                
                # Try to query new tables (should not fail)
                result = await session.execute(text("SELECT COUNT(*) FROM matches"))
                matches_count = result.scalar()
                self.print_success(f"matches table accessible (current count: {matches_count})")
                
                result = await session.execute(text("SELECT COUNT(*) FROM match_participants"))
                participants_count = result.scalar()
                self.print_success(f"match_participants table accessible (current count: {participants_count})")
                
            except Exception as e:
                raise Exception(f"New tables verification failed: {e}")
            
            # Test 2: Verify existing tables still work
            try:
                result = await session.execute(text("SELECT COUNT(*) FROM challenges"))
                challenges_count = result.scalar()
                self.print_success(f"Existing challenges table preserved (count: {challenges_count})")
                
                result = await session.execute(text("SELECT COUNT(*) FROM players"))
                players_count = result.scalar()
                self.print_success(f"Existing players table preserved (count: {players_count})")
                
                result = await session.execute(text("SELECT COUNT(*) FROM elo_history"))
                elo_count = result.scalar()
                self.print_success(f"Existing elo_history table preserved (count: {elo_count})")
                
            except Exception as e:
                raise Exception(f"Existing tables verification failed: {e}")
            
            # Test 3: Verify EloHistory schema update
            try:
                # Check if match_id column exists
                result = await session.execute(text("PRAGMA table_info(elo_history)"))
                columns = result.fetchall()
                column_names = [col[1] for col in columns]
                
                if 'match_id' not in column_names:
                    raise Exception("match_id column not found in elo_history table")
                    
                self.print_success("EloHistory schema update verified (match_id column present)")
                
            except Exception as e:
                raise Exception(f"EloHistory schema verification failed: {e}")
        
        self.print_success("All migration verifications passed")
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            await self.db.close()
        except Exception as e:
            self.print_warning(f"Cleanup warning: {e}")

async def main():
    """Main migration execution"""
    print("🔄 Phase 2A2 Schema Migration")
    print("=" * 60)
    print("This migration adds Match and MatchParticipant models")
    print("for N-player tournament support while preserving")
    print("all existing Challenge functionality.")
    print("=" * 60)
    
    migration = Phase2A2SchemaMigration()
    success = await migration.run_migration()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        print("\nNext steps:")
        print("1. Run validation tests: python test_phase_2a2_subphase_1_schema.py")
        print("2. Proceed to Subphase 2: Match Operations Implementation")
    else:
        print("\n❌ Migration failed!")
        print("\nRestore from backup if needed:")
        print("1. cp tournament_backup_phase_2a2.db tournament.db")
        print("2. Check error messages above for details")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)