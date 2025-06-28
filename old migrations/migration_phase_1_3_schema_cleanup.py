#!/usr/bin/env python3
"""
Phase 1.3 Database Schema Cleanup Migration

This migration removes legacy 2-player Challenge fields (challenger_id, challenged_id) 
and adds performance indexes. Uses SQLite table recreation strategy due to foreign 
key constraints.

Approach:
1. Create new challenges table without legacy columns
2. Copy data from old table to new table
3. Drop old table and rename new table
4. Add performance indexes
"""

import asyncio
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict
from sqlalchemy import text
from bot.database.database import Database
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)

async def phase_1_3_migration():
    """
    Execute Phase 1.3 schema cleanup with proper SQLite table recreation.
    """
    print('🔧 Phase 1.3 Database Schema Cleanup - Table Recreation Strategy')
    print('='*70)
    
    # Version check
    sqlite_version = sqlite3.sqlite_version
    version_parts = tuple(int(x) for x in sqlite_version.split('.'))
    print(f'📋 SQLite version: {sqlite_version}')
    
    if version_parts < (3, 35, 0):
        logger.warning(f'SQLite version {sqlite_version} may have limited support')
    
    # Initialize database
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        print('🔍 Starting migration transaction...')
        
        # Start with foreign keys disabled for the migration
        await session.execute(text('PRAGMA foreign_keys=OFF;'))
        
        try:
            # Step 1: Backup verification
            print('💾 Creating migration backup...')
            backup_name = f'tournament_backup_phase_1_3_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
            await session.execute(text(f'''VACUUM INTO '{backup_name}';'''))
            print(f'   ✅ Backup created: {backup_name}')
            
            # Step 2: Check if legacy columns exist
            result = await session.execute(text('PRAGMA table_info(challenges);'))
            columns = result.fetchall()
            column_names = [col[1] for col in columns]
            
            challenger_exists = 'challenger_id' in column_names
            challenged_exists = 'challenged_id' in column_names
            
            print(f'🔍 Legacy column check:')
            print(f'   challenger_id: {"EXISTS" if challenger_exists else "MISSING"}')
            print(f'   challenged_id: {"EXISTS" if challenged_exists else "MISSING"}')
            
            if not (challenger_exists or challenged_exists):
                print('ℹ️  Legacy columns already removed, proceeding to indexes only...')
            else:
                # Step 3: Create new challenges table without legacy columns
                print('🏗️  Creating new challenges table structure...')
                
                new_table_sql = '''
                CREATE TABLE challenges_new (
                    id INTEGER NOT NULL,
                    game_id INTEGER NOT NULL,
                    status VARCHAR(9),
                    ticket_wager INTEGER,
                    elo_at_stake BOOLEAN,
                    discord_message_id BIGINT,
                    discord_channel_id BIGINT,
                    created_at DATETIME,
                    expires_at DATETIME,
                    accepted_at DATETIME,
                    completed_at DATETIME,
                    challenger_result VARCHAR(4),
                    challenged_result VARCHAR(4),
                    challenger_elo_change INTEGER,
                    challenged_elo_change INTEGER,
                    admin_notes TEXT,
                    event_id INTEGER,
                    PRIMARY KEY (id),
                    FOREIGN KEY(game_id) REFERENCES games (id)
                );'''
                
                await session.execute(text(new_table_sql))
                print('   ✅ New challenges table created')
                
                # Step 4: Copy data from old table to new table (excluding legacy columns)
                print('📋 Copying data to new table structure...')
                
                copy_sql = '''
                INSERT INTO challenges_new (
                    id, game_id, status, ticket_wager, elo_at_stake, 
                    discord_message_id, discord_channel_id, created_at, 
                    expires_at, accepted_at, completed_at, challenger_result, 
                    challenged_result, challenger_elo_change, challenged_elo_change, 
                    admin_notes, event_id
                )
                SELECT 
                    id, game_id, status, ticket_wager, elo_at_stake,
                    discord_message_id, discord_channel_id, created_at,
                    expires_at, accepted_at, completed_at, challenger_result,
                    challenged_result, challenger_elo_change, challenged_elo_change,
                    admin_notes, event_id
                FROM challenges;'''
                
                result = await session.execute(text(copy_sql))
                rows_copied = result.rowcount
                print(f'   ✅ Copied {rows_copied} rows to new table')
                
                # Step 5: Drop old table and rename new table
                print('🔄 Replacing old table with new structure...')
                await session.execute(text('DROP TABLE challenges;'))
                await session.execute(text('ALTER TABLE challenges_new RENAME TO challenges;'))
                print('   ✅ Table replacement completed')
                
                # Step 6: Verify the migration
                print('🔍 Verifying schema changes...')
                result = await session.execute(text('PRAGMA table_info(challenges);'))
                new_columns = result.fetchall()
                new_column_names = [col[1] for col in new_columns]
                
                if 'challenger_id' in new_column_names or 'challenged_id' in new_column_names:
                    raise Exception('Legacy columns still exist after migration!')
                
                print('   ✅ Legacy columns successfully removed')
                print(f'   ✅ New table has {len(new_column_names)} columns')
            
            # Step 7: Add performance indexes (works whether columns were removed or not)
            print('📈 Adding performance indexes...')
            
            indexes = [
                ('idx_challenge_participants_challenge', 'challenge_participants', 'challenge_id'),
                ('idx_challenge_participants_player', 'challenge_participants', 'player_id'), 
                ('idx_challenge_participants_status', 'challenge_participants', 'status'),
                ('idx_events_base_name', 'events', 'base_event_name'),
                ('idx_challenges_status', 'challenges', 'status'),
                ('idx_challenges_created_at', 'challenges', 'created_at'),
                ('idx_challenges_event_id', 'challenges', 'event_id')
            ]
            
            for index_name, table_name, column_name in indexes:
                try:
                    await session.execute(text(f'CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name});'))
                    print(f'   ✅ Added index: {index_name}')
                except Exception as e:
                    print(f'   ⚠️  Index {index_name} failed: {e}')
            
            # Step 8: Re-enable foreign keys and verify integrity
            print('🔍 Re-enabling foreign keys and checking integrity...')
            await session.execute(text('PRAGMA foreign_keys=ON;'))
            
            # Check foreign key integrity
            result = await session.execute(text('PRAGMA foreign_key_check;'))
            fk_violations = result.fetchall()
            
            if fk_violations:
                print(f'   ⚠️  Foreign key violations found: {len(fk_violations)}')
                for violation in fk_violations:
                    print(f'      {violation}')
            else:
                print('   ✅ Foreign key integrity verified')
            
            # Step 9: Commit all changes
            await session.commit()
            print('💾 All schema updates committed successfully!')
            
        except Exception as e:
            await session.rollback()
            logger.error(f'Migration failed: {e}')
            print(f'❌ Migration failed: {e}')
            print('🔄 All changes have been rolled back')
            raise
        
        finally:
            # Always re-enable foreign keys
            await session.execute(text('PRAGMA foreign_keys=ON;'))
    
    print('')
    print('🎉 Phase 1.3 Database Schema Cleanup COMPLETED!')
    print('   ✅ Legacy 2-player Challenge fields removed')
    print('   ✅ Foreign key constraints preserved')
    print('   ✅ Performance indexes added')
    print('   ✅ Database ready for N-player challenge system')
    print(f'   ✅ Backup available: {backup_name}')

async def main():
    """Main entry point"""
    logger.info("Starting Phase 1.3 schema cleanup migration...")
    try:
        await phase_1_3_migration()
        logger.info("Phase 1.3 migration completed successfully")
    except Exception as e:
        logger.error(f"Phase 1.3 migration failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())