#!/usr/bin/env python3
"""
Game→Event Migration Script
Migrates legacy Game model data to Event model and updates Challenge model references

CRITICAL: This migration must be run BEFORE updating the Challenge model
to ensure data integrity and no loss of existing challenge data.
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from bot.config import Config
from bot.database.database import Database
from bot.database.models import Game, Event, Challenge, Cluster
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

class GameToEventMigrator:
    def __init__(self):
        self.db = None
        self.migration_log = []
        self.backup_created = False
        
    def log(self, message: str, level: str = "INFO"):
        """Log migration progress"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {level}: {message}"
        print(log_entry)
        self.migration_log.append(log_entry)
    
    async def initialize_database(self):
        """Initialize database connection"""
        self.log("Initializing database connection...")
        self.db = Database()
        await self.db.initialize()
        self.log("Database connection established")
    
    async def create_backup(self):
        """Create backup of current database"""
        self.log("Creating database backup...")
        
        # Get current database path
        db_url = Config.DATABASE_URL
        if 'sqlite' in db_url:
            # Extract database file path
            db_path = db_url.replace('sqlite:///', '').replace('sqlite+aiosqlite:///', '')
            backup_path = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{db_path}"
            
            import shutil
            shutil.copy2(db_path, backup_path)
            self.log(f"Database backup created: {backup_path}")
            self.backup_created = True
        else:
            self.log("Non-SQLite database detected - manual backup recommended", "WARNING")
    
    async def analyze_current_state(self) -> Dict:
        """Analyze current Games and Events"""
        self.log("Analyzing current database state...")
        
        async with self.db.get_session() as session:
            # Get all Games
            games_result = await session.execute(select(Game))
            games = games_result.scalars().all()
            
            # Get all Events  
            events_result = await session.execute(
                select(Event).options(selectinload(Event.cluster))
            )
            events = events_result.scalars().all()
            
            # Get all Challenges with Game references
            challenges_result = await session.execute(
                select(Challenge).options(
                    selectinload(Challenge.game),
                    selectinload(Challenge.challenger),
                    selectinload(Challenge.challenged)
                )
            )
            challenges = challenges_result.scalars().all()
            
            # Get all Clusters
            clusters_result = await session.execute(select(Cluster))
            clusters = clusters_result.scalars().all()
        
        analysis = {
            'games': games,
            'events': events, 
            'challenges': challenges,
            'clusters': clusters,
            'games_count': len(games),
            'events_count': len(events),
            'challenges_count': len(challenges),
            'clusters_count': len(clusters)
        }
        
        self.log(f"Found {analysis['games_count']} Games, {analysis['events_count']} Events")
        self.log(f"Found {analysis['challenges_count']} Challenges, {analysis['clusters_count']} Clusters")
        
        return analysis
    
    async def create_game_to_event_mapping(self, analysis: Dict) -> Dict[int, int]:
        """Create mapping from Game IDs to Event IDs"""
        self.log("Creating Game→Event mapping...")
        
        mapping = {}
        games_without_events = []
        
        # Try to match Games to existing Events by name
        for game in analysis['games']:
            matched_event = None
            
            # Look for exact name match first
            for event in analysis['events']:
                if event.name.lower() == game.name.lower():
                    matched_event = event
                    break
            
            # If no exact match, look for partial match
            if not matched_event:
                for event in analysis['events']:
                    if game.name.lower() in event.name.lower() or event.name.lower() in game.name.lower():
                        matched_event = event
                        break
            
            if matched_event:
                mapping[game.id] = matched_event.id
                self.log(f"Mapped Game '{game.name}' → Event '{matched_event.name}'")
            else:
                games_without_events.append(game)
                self.log(f"No matching Event found for Game '{game.name}'", "WARNING")
        
        # For Games without matching Events, we need to create new Events
        if games_without_events:
            await self._create_events_for_unmapped_games(games_without_events, mapping, analysis)
        
        self.log(f"Game→Event mapping complete: {len(mapping)} mappings created")
        return mapping
    
    async def _create_events_for_unmapped_games(self, games: List[Game], mapping: Dict[int, int], analysis: Dict):
        """Create Events for Games that don't have matching Events"""
        self.log(f"Creating Events for {len(games)} unmapped Games...")
        
        # Find the "Legacy Games" cluster or create it
        legacy_cluster = None
        for cluster in analysis['clusters']:
            if 'legacy' in cluster.name.lower() or 'games' in cluster.name.lower():
                legacy_cluster = cluster
                break
        
        if not legacy_cluster:
            # Create Legacy Games cluster
            async with self.db.get_session() as session:
                # Find next cluster number
                max_cluster_num = max([c.number for c in analysis['clusters']], default=0)
                
                legacy_cluster = Cluster(
                    number=max_cluster_num + 1,
                    name="Legacy Games",
                    is_active=True
                )
                session.add(legacy_cluster)
                await session.commit()
                await session.refresh(legacy_cluster)
                
                self.log(f"Created Legacy Games cluster (#{legacy_cluster.number})")
        
        # Create Events for unmapped Games
        async with self.db.get_session() as session:
            for game in games:
                # Default to 1v1 scoring for legacy games
                new_event = Event(
                    name=game.name,
                    cluster_id=legacy_cluster.id,
                    scoring_type="1v1",  # Most legacy games are 1v1
                    crownslayer_pool=300,
                    is_active=game.is_active,
                    min_players=game.min_players,
                    max_players=game.max_players,
                    allow_challenges=game.allow_challenges
                )
                
                session.add(new_event)
                await session.flush()  # Get the ID
                
                mapping[game.id] = new_event.id
                self.log(f"Created Event '{new_event.name}' for Game '{game.name}'")
            
            await session.commit()
    
    async def migrate_challenge_references(self, mapping: Dict[int, int], analysis: Dict):
        """Update Challenge model to use event_id instead of game_id"""
        self.log("Migrating Challenge references from game_id to event_id...")
        
        challenges_updated = 0
        challenges_skipped = 0
        
        async with self.db.get_session() as session:
            for challenge in analysis['challenges']:
                if challenge.game_id in mapping:
                    new_event_id = mapping[challenge.game_id]
                    
                    # We can't directly update the challenge model yet since it still has game_id
                    # This will be handled in the model update phase
                    self.log(f"Challenge {challenge.id}: Game {challenge.game_id} → Event {new_event_id}")
                    challenges_updated += 1
                else:
                    self.log(f"Challenge {challenge.id}: No mapping for Game {challenge.game_id}", "ERROR")
                    challenges_skipped += 1
        
        self.log(f"Challenge migration analysis: {challenges_updated} to update, {challenges_skipped} skipped")
        return challenges_updated, challenges_skipped
    
    async def validate_migration(self, mapping: Dict[int, int]):
        """Validate the migration was successful"""
        self.log("Validating migration...")
        
        async with self.db.get_session() as session:
            # Check that all mapped Events exist
            for game_id, event_id in mapping.items():
                event_result = await session.execute(
                    select(Event).where(Event.id == event_id)
                )
                event = event_result.scalar_one_or_none()
                
                if not event:
                    self.log(f"ERROR: Event {event_id} not found for Game {game_id}", "ERROR")
                    return False
                else:
                    self.log(f"✓ Event {event_id} exists for Game {game_id}")
        
        self.log("Migration validation successful")
        return True
    
    async def generate_migration_report(self, mapping: Dict[int, int], analysis: Dict):
        """Generate detailed migration report"""
        self.log("Generating migration report...")
        
        report_lines = [
            "=" * 60,
            "GAME→EVENT MIGRATION REPORT",
            "=" * 60,
            f"Migration Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Backup Created: {self.backup_created}",
            "",
            "SUMMARY:",
            f"  • Games processed: {analysis['games_count']}",
            f"  • Events existing: {analysis['events_count']}",
            f"  • Challenges affected: {analysis['challenges_count']}",
            f"  • Mappings created: {len(mapping)}",
            "",
            "MAPPINGS:",
        ]
        
        for game_id, event_id in mapping.items():
            # Find game and event names
            game_name = "Unknown"
            event_name = "Unknown"
            
            for game in analysis['games']:
                if game.id == game_id:
                    game_name = game.name
                    break
            
            for event in analysis['events']:
                if event.id == event_id:
                    event_name = f"{event.name} (Cluster {event.cluster.number if event.cluster else 'Unknown'})"
                    break
            
            report_lines.append(f"  • Game {game_id} '{game_name}' → Event {event_id} '{event_name}'")
        
        report_lines.extend([
            "",
            "NEXT STEPS:",
            "1. Update Challenge model to use event_id instead of game_id",
            "2. Update database operations to use Events instead of Games",
            "3. Run test suite to verify functionality",
            "4. Deprecate Game model after successful validation",
            "",
            "MIGRATION LOG:",
        ])
        
        report_lines.extend(self.migration_log)
        
        # Write report to file
        report_path = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_path, 'w') as f:
            f.write('\n'.join(report_lines))
        
        self.log(f"Migration report saved to: {report_path}")
        
        # Also print key info
        print("\n" + "\n".join(report_lines[:20]))  # Print first 20 lines
        print(f"\nFull report saved to: {report_path}")
    
    async def run_migration(self):
        """Run the complete migration process"""
        try:
            await self.initialize_database()
            await self.create_backup()
            
            analysis = await self.analyze_current_state()
            mapping = await self.create_game_to_event_mapping(analysis)
            
            updated, skipped = await self.migrate_challenge_references(mapping, analysis)
            
            if await self.validate_migration(mapping):
                await self.generate_migration_report(mapping, analysis)
                
                self.log("=" * 50)
                self.log("MIGRATION COMPLETED SUCCESSFULLY", "SUCCESS")
                self.log("=" * 50)
                self.log("Next steps:")
                self.log("1. Update Challenge model (models.py)")
                self.log("2. Update database operations (database.py)")
                self.log("3. Run test suite")
                
                return True
            else:
                self.log("MIGRATION VALIDATION FAILED", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"MIGRATION FAILED: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            if self.db:
                await self.db.close()

async def main():
    """Run the migration"""
    print("🔄 Game→Event Migration Script")
    print("=" * 50)
    print("This script will migrate legacy Game model data to Event model")
    print("and prepare for Challenge model updates.")
    print()
    
    response = input("Continue with migration? (y/N): ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        return 1
    
    migrator = GameToEventMigrator()
    success = await migrator.run_migration()
    
    return 0 if success else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)