#!/usr/bin/env python3
"""
Phase 1.1 Database Migration: Per-Event Elo Tracking and Meta-Game Foundation

This migration implements the complete data reset strategy as specified in planA.md:
1. Creates new models for per-event Elo tracking and ticket economy
2. Preserves Discord registrations (Player records)
3. Resets all Elo to 1000 and tickets to 0
4. Initializes PlayerEventStats for all player/event combinations
5. Creates TicketLedger entries for clean slate

Migration Strategy: Complete data reset approach to establish new per-event architecture.
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import List

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, delete, func, text
from sqlalchemy.exc import IntegrityError

from bot.config import Config
from bot.database.models import (
    Base, Player, Event, Cluster,
    PlayerEventStats, TicketLedger, EloHistory, Ticket, Challenge
)
from bot.utils.logger import setup_logger

# Migration configuration
DEFAULT_ELO = 1000
DEFAULT_TICKETS = 0
BACKUP_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

logger = setup_logger(__name__)

async def get_session():
    """Create async database session"""
    database_url = Config.DATABASE_URL
    if database_url.startswith('sqlite:///'):
        database_url = database_url.replace('sqlite:///', 'sqlite+aiosqlite:///')
    
    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
    
    await engine.dispose()

async def create_database_backup():
    """Create a backup of the current database"""
    try:
        import shutil
        backup_path = f"tournament_backup_phase_1.1_{BACKUP_TIMESTAMP}.db"
        shutil.copy2("tournament.db", backup_path)
        logger.info(f"Database backup created: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        raise

async def verify_existing_data():
    """Verify current database state before migration"""
    async for session in get_session():
        try:
            # Count existing records
            player_count = await session.scalar(select(func.count(Player.id)))
            event_count = await session.scalar(select(func.count(Event.id)))
            cluster_count = await session.scalar(select(func.count(Cluster.id)))
            
            logger.info(f"Pre-migration data: {player_count} players, {event_count} events, {cluster_count} clusters")
            
            # Verify we have the CSV data loaded
            if cluster_count == 0 or event_count == 0:
                logger.warning("No clusters or events found - CSV data may not be loaded")
            
            return {
                'players': player_count,
                'events': event_count,
                'clusters': cluster_count
            }
            
        except Exception as e:
            logger.error(f"Error verifying existing data: {e}")
            raise

async def reset_player_data():
    """Reset player stats while preserving Discord registrations"""
    async for session in get_session():
        try:
            logger.info("Resetting player data to clean slate...")
            
            # Reset player stats to defaults while preserving Discord registration
            await session.execute(
                update(Player).values(
                    elo_rating=DEFAULT_ELO,
                    tickets=DEFAULT_TICKETS,
                    matches_played=0,
                    wins=0,
                    losses=0,
                    draws=0,
                    active_leverage_token=None,
                    current_streak=0,
                    max_streak=0
                )
            )
            
            # Clear historical data as per reset strategy
            await session.execute(delete(EloHistory))
            await session.execute(delete(Ticket))
            await session.execute(delete(Challenge))
            
            await session.commit()
            logger.info("Player data reset completed")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error resetting player data: {e}")
            raise

async def initialize_player_event_stats():
    """Initialize PlayerEventStats for all player/event combinations"""
    async for session in get_session():
        try:
            logger.info("Initializing PlayerEventStats for all player/event combinations...")
            
            # Use SQL-based approach for scalability (as recommended by expert analysis)
            insert_query = text("""
                INSERT OR IGNORE INTO player_event_stats (
                    player_id, 
                    event_id, 
                    raw_elo, 
                    scoring_elo,
                    matches_played,
                    wins,
                    losses,
                    draws
                )
                SELECT
                    p.id AS player_id,
                    e.id AS event_id,
                    :default_elo AS raw_elo,
                    :default_elo AS scoring_elo,
                    0 AS matches_played,
                    0 AS wins,
                    0 AS losses,
                    0 AS draws
                FROM
                    players p
                CROSS JOIN
                    events e
            """)
            
            result = await session.execute(insert_query, {"default_elo": DEFAULT_ELO})
            await session.commit()
            
            logger.info(f"PlayerEventStats initialization complete. {result.rowcount} records created.")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error initializing PlayerEventStats: {e}")
            raise

async def initialize_ticket_ledger():
    """Initialize TicketLedger with starting balance entries for all players"""
    async for session in get_session():
        try:
            logger.info("Initializing TicketLedger with starting balances...")
            
            # Get all players
            players = await session.execute(select(Player.id))
            player_ids = [row[0] for row in players.fetchall()]
            
            # Create initial ledger entries for each player
            ledger_entries = []
            for player_id in player_ids:
                ledger_entries.append(TicketLedger(
                    player_id=player_id,
                    change_amount=DEFAULT_TICKETS,
                    reason="MIGRATION_RESET",
                    balance_after=DEFAULT_TICKETS
                ))
            
            if ledger_entries:
                session.add_all(ledger_entries)
                await session.commit()
                logger.info(f"TicketLedger initialized with {len(ledger_entries)} starting balance entries")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Error initializing TicketLedger: {e}")
            raise

async def verify_migration_results():
    """Verify the migration completed successfully"""
    async for session in get_session():
        try:
            logger.info("Verifying migration results...")
            
            # Count new records
            player_event_stats_count = await session.scalar(select(func.count(PlayerEventStats.id)))
            ticket_ledger_count = await session.scalar(select(func.count(TicketLedger.id)))
            
            # Verify player data reset
            result = await session.execute(
                select(func.count(Player.id)).where(Player.elo_rating != DEFAULT_ELO)
            )
            non_default_elo_count = result.scalar()
            
            logger.info(f"Migration verification:")
            logger.info(f"  - PlayerEventStats records: {player_event_stats_count}")
            logger.info(f"  - TicketLedger records: {ticket_ledger_count}")
            logger.info(f"  - Players with non-default Elo: {non_default_elo_count}")
            
            # Verify relationships work
            sample_player = await session.execute(
                select(Player).options(selectinload(Player.event_stats)).limit(1)
            )
            player = sample_player.scalar_one_or_none()
            
            if player and player.event_stats:
                logger.info(f"  - Sample player has {len(player.event_stats)} event stats records")
            
            return {
                'player_event_stats': player_event_stats_count,
                'ticket_ledger': ticket_ledger_count,
                'players_with_default_elo': non_default_elo_count == 0
            }
            
        except Exception as e:
            logger.error(f"Error verifying migration: {e}")
            raise

async def main():
    """Execute Phase 1.1 migration"""
    logger.info("=" * 60)
    logger.info("Starting Phase 1.1 Database Migration")
    logger.info("Per-Event Elo Tracking and Meta-Game Foundation")
    logger.info("=" * 60)
    
    try:
        # Step 1: Create backup
        backup_path = await create_database_backup()
        
        # Step 2: Verify existing data
        pre_migration_data = await verify_existing_data()
        
        # Step 3: Create new tables and add missing columns
        async for session in get_session():
            async with session.begin():
                # Create all new tables
                from sqlalchemy.ext.asyncio import create_async_engine
                database_url = Config.DATABASE_URL
                if database_url.startswith('sqlite:///'):
                    database_url = database_url.replace('sqlite:///', 'sqlite+aiosqlite:///')
                
                engine = create_async_engine(database_url, echo=False)
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                    
                    # Add missing columns to existing tables
                    try:
                        await conn.execute(text("ALTER TABLE players ADD COLUMN active_leverage_token VARCHAR(50)"))
                        logger.info("Added active_leverage_token column to players table")
                    except Exception as e:
                        if "duplicate column name" in str(e).lower():
                            logger.info("active_leverage_token column already exists")
                        else:
                            raise
                    
                    try:
                        await conn.execute(text("ALTER TABLE players ADD COLUMN current_streak INTEGER DEFAULT 0"))
                        logger.info("Added current_streak column to players table")
                    except Exception as e:
                        if "duplicate column name" in str(e).lower():
                            logger.info("current_streak column already exists")
                        else:
                            raise
                    
                    try:
                        await conn.execute(text("ALTER TABLE players ADD COLUMN max_streak INTEGER DEFAULT 0"))
                        logger.info("Added max_streak column to players table")
                    except Exception as e:
                        if "duplicate column name" in str(e).lower():
                            logger.info("max_streak column already exists")
                        else:
                            raise
                    
                    # Add event_id column to elo_history if missing
                    try:
                        await conn.execute(text("ALTER TABLE elo_history ADD COLUMN event_id INTEGER"))
                        logger.info("Added event_id column to elo_history table")
                    except Exception as e:
                        if "duplicate column name" in str(e).lower():
                            logger.info("event_id column already exists")
                        else:
                            raise
                            
                await engine.dispose()
                
                logger.info("Database schema update completed successfully")
        
        # Step 4: Reset player data (preserving Discord registrations)
        await reset_player_data()
        
        # Step 5: Initialize PlayerEventStats
        await initialize_player_event_stats()
        
        # Step 6: Initialize TicketLedger
        await initialize_ticket_ledger()
        
        # Step 7: Verify results
        verification_results = await verify_migration_results()
        
        # Create success report
        report_path = f"migration_success_report_phase_1.1_{BACKUP_TIMESTAMP}.txt"
        with open(report_path, 'w') as f:
            f.write(f"Phase 1.1 Migration Success Report\n")
            f.write(f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"Backup Created: {backup_path}\n\n")
            f.write(f"Pre-migration Data:\n")
            for key, value in pre_migration_data.items():
                f.write(f"  {key}: {value}\n")
            f.write(f"\nPost-migration Data:\n")
            for key, value in verification_results.items():
                f.write(f"  {key}: {value}\n")
            f.write(f"\nMigration completed successfully!\n")
        
        logger.info("=" * 60)
        logger.info("Phase 1.1 Migration COMPLETED SUCCESSFULLY")
        logger.info(f"Success report: {report_path}")
        logger.info(f"Database backup: {backup_path}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error("MIGRATION FAILED")
        logger.error(f"Error: {e}")
        logger.error("=" * 60)
        
        # Create emergency rollback script
        rollback_script = f"emergency_rollback_phase_1.1_{BACKUP_TIMESTAMP}.sh"
        with open(rollback_script, 'w') as f:
            f.write("#!/bin/bash\n")
            f.write(f"# Emergency rollback for Phase 1.1 migration\n")
            f.write(f"cp {backup_path} tournament.db\n")
            f.write(f"echo 'Database rolled back to pre-migration state'\n")
        
        os.chmod(rollback_script, 0o755)
        logger.error(f"Emergency rollback script created: {rollback_script}")
        
        raise

if __name__ == "__main__":
    asyncio.run(main())