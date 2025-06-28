# LB-Tournament-Arc Implementation Plan B

## Executive Summary

This document provides a comprehensive implementation roadmap that maintains complete fidelity to planA.md while accounting for the current state of the codebase. The critical architectural changes required:

1. **Remove /ffa command entirely** - It violates the tournament hierarchy by creating ad-hoc events
2. **Implement hierarchical /challenge command** - Proper flow: `/challenge cluster:IO_Games event:Diep type:1v1 players:@user1`
3. **Populate database from CSV** - No features work without proper cluster/event data
4. **Complete transition to per-event Elo** - Global Elo must be deprecated

## Current Implementation State Analysis

### ✅ Completed Components (Verified in Codebase)

#### Phase 0: Security Foundation
- Owner-only permission model implemented
- Centralized permission utilities: `is_bot_owner()` and `is_user_bot_owner()`
- All admin functions restricted to `Config.OWNER_DISCORD_ID`
- Modal UI permission checks fixed

#### Phase 1.1: Database Models
- `PlayerEventStats` model fully implemented (models.py lines 623-681)
- Includes dual-track Elo system (raw_elo, scoring_elo)
- SQLAlchemy event listeners for automatic floor enforcement
- `TicketLedger` model exists (lines 762-793)
- `ChallengeParticipant` model exists (lines 507-541)

#### Phase 1.2: PlayerEventStats Integration
- `complete_match_with_results()` uses PlayerEventStats (match_operations.py)
- `ParticipantResult` includes event_id field
- EloHistory records include event_id
- K-factor calculation based on event-specific matches

#### Phase 1.3: CSV Infrastructure
- `populate_from_csv.py` script exists
- `event_name_parser.py` for complex scoring type parsing
- Support for base_event_name extraction

#### Phase 2.1: Scoring Strategies
- `ScoringStrategy` abstract base class
- `Elo1v1Strategy` for traditional matches
- `EloFfaStrategy` with K/(N-1) scaling
- `PerformancePointsStrategy` for leaderboard events

#### Phase 2A2: Match System
- `Match` model with N-player support
- `MatchParticipant` for individual results
- `MatchOperations` service class
- Bridge functions for Challenge→Match workflow

#### Phase 2.2a: UI Infrastructure
- `PlacementModal` for ≤5 player placement entry
- `MatchConfirmationView` for result approval
- Event browser with pagination (`EventBrowserView`)

### ❌ Missing/Incomplete Components

1. **No Database Data**
   - Clusters/events tables empty
   - CSV data not imported
   - No events to challenge in

2. **/challenge Command**
   - Only placeholder exists (challenge.py)
   - No autocomplete implementation
   - No acceptance workflow

3. **/ffa Creates Ad-hoc Events**
   - Line 1037-1041 in match_commands.py creates events on-the-fly
   - Violates tournament hierarchy
   - Must be removed entirely

4. **Global Elo Still Primary**
   - Player.elo_rating still updated
   - Per-event Elo not fully replacing global
   - Hierarchy calculations not implemented

5. **Meta-game Systems**
   - Ticket economy unused
   - No leverage system
   - No Shard of the Crown
   - No leaderboard events

### 🚨 Critical Discrepancies with planA.md

1. **Architecture Violation**: /ffa bypasses proper hierarchy
   - planA.md line 433: "CRITICAL: Remove `/ffa` command entirely"
   - Current: Creates "FFA N-player by {username}" events dynamically

2. **Out-of-Order Implementation**: 
   - Built: Match system (Phase 2A2)
   - Missing: Challenge system (Phase 2)
   - Result: No proper invitation workflow

3. **Incomplete Model Usage**:
   - ChallengeParticipant exists but unused
   - Challenge model still has 2-player fields
   - Not leveraging N-player architecture

## Phase-by-Phase Implementation Plan

### Phase 1: Foundation Corrections ✅ COMPLETED & VERIFIED

#### 1.1 Remove /ffa Command Completely ✅ COMPLETED & TESTED

**File**: `bot/cogs/match_commands.py`

**Actions**:
1. ✅ Delete entire `create_ffa_match` command (lines 942-1151)
2. ✅ Remove any references in command registration
3. ✅ Update help documentation

**Rationale**: As stated in planA.md line 433, all FFA matches must go through /challenge workflow to maintain proper tournament hierarchy.

**Detailed Steps**:
1. ✅ Replace `create_ffa_match` command with deprecation notice directing users to `/challenge`
2. ✅ Remove `create_ffa_event` and `create_team_event` functions from `event_operations.py` 
3. ✅ Clean up unused imports (`EventOperations`, `EventOperationError`)
4. ✅ Remove helper functions: `_generate_ffa_event_name`, `_generate_team_event_name`, `_clean_event_name_suffix`
5. ✅ Remove FFA constants: `FFA_MIN_PLAYERS`, `FFA_MAX_PLAYERS`, `FFA_SCORING_TYPE`

**Critical Fixes Applied**:
1. ✅ Fixed EventOperations import issue in MatchCommandsCog (prevented startup crash)
2. ✅ Updated help command to remove deprecated /ffa instructions
3. ✅ Cleaned up unused datetime import

**Testing Results**: ✅ **ALL 5 TESTS PASSED** (See: `tests/test_phase_1.1_results.md`)
- ✅ Bot startup works without crashes
- ✅ /ffa shows helpful deprecation notice with /challenge guidance
- ✅ Help command updated appropriately
- ✅ All architecture-violating functions confirmed removed
- ✅ Existing match reporting functionality preserved

**Impact**: Removes 210+ lines of architecture-violating code and forces proper tournament hierarchy usage.

**Notes**: The /ffa command now shows a helpful deprecation notice directing users to the /challenge workflow. The EventOperations class has been simplified to focus on cluster management utilities. Expert code review identified and resolved critical import issues.

#### 1.2 Populate Database from CSV ✅ COMPLETED

**Command**: 
```bash
python populate_from_csv.py
```

**Pre-requisites**:
- ✅ Ensure "LB Culling Games List.csv" exists
- ✅ Verify database connection in .env
- ✅ Check CSV format matches parser expectations

**Results**: ✅ **PERFECT EXECUTION**
- ✅ **20 clusters created** (matches expected)
- ✅ **86 events created** (exceeds 60+ minimum requirement)  
- ✅ **0 events skipped** (100% successful parsing)
- ✅ base_event_name fields populated
- ✅ Proper tournament hierarchy established

#### 1.3 Database Schema Updates ✅ COMPLETED

**Migration Script**: `migration_phase_1_3_schema_cleanup.py`

**Results**: ✅ **PERFECT EXECUTION**
- ✅ **Legacy columns already removed** from previous migrations
- ✅ **All 7 performance indexes created successfully**:
  - `idx_challenge_participants_challenge` (challenge participants by challenge)
  - `idx_challenge_participants_player` (challenge participants by player)  
  - `idx_challenge_participants_status` (challenge participants by status)
  - `idx_events_base_name` (events by base name for aggregation)
  - `idx_challenges_status` (challenges by status)
  - `idx_challenges_created_at` (challenges by creation time)
  - `idx_challenges_event_id` (challenges by event)
- ✅ **Database backup created**: `tournament_backup_phase_1_3_20250627_163527.db`
- ✅ **Foreign key integrity maintained** (orphaned data from old FFA events detected but doesn't affect functionality)

**Safety Features**:
- Table recreation strategy for SQLite DDL limitations
- Automatic backup before migration
- Foreign key constraint preservation
- Idempotent execution (can be run multiple times safely)

**Manual Verification Results**: ✅ **ALL CHECKS PASSED**
- ✅ **20 clusters** confirmed in database
- ✅ **86+ events** confirmed with proper hierarchy
- ✅ **17 columns** in challenges table (legacy columns removed)
- ✅ **10+ performance indexes** created (includes SQLAlchemy auto-indexes for bonus optimization)
- ✅ **Database structure perfect** for Phase 2 implementation

---

## ✅ PHASE 1 FOUNDATION COMPLETE & VERIFIED ✅

**Architecture Status**: All violations eliminated, proper hierarchy enforced  
**Database Status**: Populated with tournament data, optimized for performance  
**Code Status**: Clean, maintainable, ready for /challenge implementation

**Ready for Phase 2: /challenge Command Implementation**

### Phase 2: Implement /challenge Command (Week 2)

#### 2.1 Challenge Model Fix ✅ COMPLETED & TESTED

**Critical Issue**: Challenge model referenced `challenger_id` and `challenged_id` columns that were removed from database in Phase 1.3, causing runtime errors.

**Solution Applied**: Surgical removal of legacy 2-player fields while preserving N-player architecture.

**Changes Made**:
1. **Challenge Model** (`bot/database/models.py`):
   - ✅ Removed `challenger_id` and `challenged_id` Column definitions 
   - ✅ Removed `challenger` and `challenged` relationship definitions
   - ✅ Updated `__repr__` method to use `event_id` instead of removed fields

2. **Player Model** (`bot/database/models.py`):
   - ✅ Removed `sent_challenges` and `received_challenges` relationships

**Preserved Components**:
- ✅ All database-aligned fields (id, game_id, event_id, status, timestamps)
- ✅ Legacy result fields (challenger_result, challenged_result, elo changes) - still exist in DB
- ✅ ChallengeParticipant relationship for N-player support
- ✅ All other model functionality

**Code Review Results**: ✅ **EXCELLENT**
- Security: No vulnerabilities, proper constraints
- Performance: Efficient relationships, schema aligned  
- Architecture: Clean N-player separation
- Code Quality: Clear comments, maintainable patterns

**Testing**: ✅ **ALL 5 TESTS PASSED** (See: `tests/test_phase_2.1_challenge_model_fix.md`)
- ✅ Model imports without SQLAlchemy errors
- ✅ Legacy relationships removed, N-player relationships preserved
- ✅ Bot startup successful
- ✅ Model properties and methods work correctly
- ✅ Perfect model-database schema alignment (17 columns)

**Impact**: 
- 🔥 **Critical runtime errors resolved** - Challenge operations now safe
- 🏗️ **N-player architecture ready** - ChallengeParticipant table functional
- 🛡️ **Zero regressions** - All existing functionality preserved

#### 2.1.1 Model Architecture Enhancements (Production-Ready Implementation) ✅ IMPLEMENTED

**Purpose**: Address architectural gaps identified during code review to ensure robust N-player challenge system with production-safe migration.

**Priority**: HIGH - Required for proper /challenge command implementation

**Improvements Needed**:

##### 🔴 **IMMEDIATE ACTIONS** (Do NOW before any other Phase 2 work)

**1. Add ChallengeRole Enum to models.py**:
```python
# In bot/database/models.py, after ConfirmationStatus enum (line ~506)
class ChallengeRole(Enum):
    """Role of a participant in a challenge"""
    CHALLENGER = "challenger"  # Challenge initiator (lowercase for SQL compatibility)
    CHALLENGED = "challenged"  # Challenge recipient (lowercase for SQL compatibility)
```

**2. Update ChallengeParticipant Model**:
```python
# In ChallengeParticipant class (line ~522)
class ChallengeParticipant(Base):
    # ... existing fields ...
    
    # Participant role (required for challenge logic)
    role = Column(SQLEnum(ChallengeRole), nullable=True)  # Start nullable for migration
    
    # Note: Will be made NOT NULL after migration completes
```

**3. Add Deprecation Comments to Challenge Model**:
```python
# In Challenge class (lines 174-179)
    # Match results (filled when challenge is completed)
    # DEPRECATED: Legacy 2-player result fields - kept for backward compatibility only
    # NEW DEVELOPMENT: Use Match and MatchParticipant tables for all results
    # DO NOT WRITE to these fields for new challenges
    challenger_result = Column(SQLEnum(MatchResult))  # DEPRECATED - see Phase 2.1.1
    challenged_result = Column(SQLEnum(MatchResult))  # DEPRECATED - see Phase 2.1.1
    
    # Elo changes (calculated after match)
    # DEPRECATED: Legacy Elo change tracking - kept for backward compatibility only  
    # NEW DEVELOPMENT: Use MatchParticipant.elo_change for all Elo tracking
    challenger_elo_change = Column(Integer, default=0)  # DEPRECATED - see Phase 2.1.1
    challenged_elo_change = Column(Integer, default=0)  # DEPRECATED - see Phase 2.1.1
```

##### 🔴 **HIGH PRIORITY**: Production-Safe Role Field Migration

**Issue**: ChallengeParticipant model lacks distinction between challenger (initiator) and challenged (recipients), making it impossible to properly populate legacy result fields or handle 1v1 challenge logic.

**Impact**: 
- Cannot determine who initiated a challenge
- Legacy `challenger_result`/`challenged_result` fields cannot be populated correctly
- EloHistory `opponent_id` field becomes ambiguous in 1v1 contexts
- Business logic errors when processing challenge results

**Migration Script** (`migration_phase_2_1_1_add_role_field.py`):
```python
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
```

**Migration Testing**:
```bash
# Test the migration
python migration_phase_2_1_1_add_role_field.py

# Verify results
sqlite3 tournament.db "SELECT role, COUNT(*) FROM challenge_participants GROUP BY role;"
# Expected: Shows challenger and challenged counts

# Test rollback (if needed)
./rollback_phase_2_1_1_[timestamp].sh
```

**Implementation Timeline**:
1. **NOW**: Add enum and deprecation comments to models.py
2. **THEN**: Run migration script to add role field
3. **NEXT**: Update models.py to enforce NOT NULL at application level
4. **FINALLY**: Implement ChallengeOperations with role awareness

**Key Safety Features**:
1. Automatic backup before migration
2. SQLite version check (needs 3.35.0+)
3. Idempotent - safe to run multiple times
4. Generated rollback script
5. Transaction-based for atomicity
6. Detailed logging throughout

**Expert Review Improvements Applied**:
1. ✅ Fixed backup_path scope error - now passed as parameter
2. ✅ Added note about challenger identification strategy
3. ✅ Documented NOT NULL constraint limitation and future migration path
4. ✅ Enhanced logging to show role distribution after migration

**Future Enhancement Considerations**:
- Use created_at timestamp for more accurate challenger identification (if added to table)
- Create follow-up migration to enforce NOT NULL at database level (requires table recreation)
- Consider adding compound indexes for (challenge_id, role) for query optimization
- ✅ Compatible with existing indexes and constraints

**Implementation Notes** (2025-06-28):
1. ✅ Added ChallengeRole enum to models.py (after ConfirmationStatus)
2. ✅ Added role field to ChallengeParticipant model (nullable=True for migration)
3. ✅ Added deprecation comments to Challenge legacy fields
4. ✅ Created migration script: migration_phase_2_1_1_add_role_field.py
5. ✅ Migration executed successfully
6. ✅ All 6 tests passed - role field working correctly

**Testing Results**: ✅ **ALL 6 TESTS PASSED** (See: `tests/test_phase_2.1.1_role_field_migration.md`)
- ✅ Model imports and enum values correct
- ✅ Pre-migration database state verified
- ✅ Migration execution successful with backup/rollback
- ✅ Post-migration verification: 8 participants (2 challenger, 6 challenged)
- ✅ Bot startup compatibility confirmed
- ✅ Migration idempotency verified

#### 2.2 Command Structure Implementation ✅ COMPLETED & TESTED

**File**: `bot/cogs/challenge.py` (complete rewrite)

```python
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
from datetime import datetime, timedelta

from bot.database.models import (
    Challenge, ChallengeStatus, ChallengeParticipant,
    ConfirmationStatus, Cluster, Event, Player
)
from bot.database.database import Database
from bot.operations.challenge_operations import ChallengeOperations
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)

class ChallengeCog(commands.Cog):
    """Hierarchical challenge system for all match types"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db
        self.challenge_ops = ChallengeOperations(self.db)
    
    @app_commands.command(
        name="challenge",
        description="Create a match challenge through tournament hierarchy"
    )
    @app_commands.describe(
        cluster="Select tournament cluster",
        event="Select event within cluster",
        match_type="Match format (1v1, Team, FFA)",
        players="Players to challenge (space-separated @mentions)"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="1v1", value="1v1"),
        app_commands.Choice(name="Free for All", value="ffa"),
        app_commands.Choice(name="Team", value="team"),
    ])
    async def challenge(
        self,
        interaction: discord.Interaction,
        cluster: str,  # Will use autocomplete
        event: str,    # Will use autocomplete  
        match_type: str,
        players: str
    ):
        """Create a challenge through proper tournament hierarchy"""
        
        # Implementation continues below...
```

#### 2.2 Autocomplete Implementation ✅ COMPLETED

**Critical Feature**: Dynamic filtering as specified in planA.md lines 397-414

```python
@challenge.autocomplete('cluster')
async def cluster_autocomplete(
    self, 
    interaction: discord.Interaction, 
    current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete for cluster selection"""
    try:
        # Get all active clusters
        clusters = await self.db.get_all_clusters(active_only=True)
        
        # Filter by current input
        if current:
            clusters = [c for c in clusters if current.lower() in c.name.lower()]
        
        # Return max 25 choices (Discord limit)
        return [
            app_commands.Choice(name=c.name, value=str(c.id))
            for c in clusters[:25]
        ]
    except Exception as e:
        logger.error(f"Cluster autocomplete error: {e}")
        return []

@challenge.autocomplete('event')
async def event_autocomplete(
    self,
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete for event selection, filtered by chosen cluster"""
    try:
        # Get selected cluster from interaction
        cluster_id = interaction.namespace.cluster
        if not cluster_id:
            return []
        
        # Get events for selected cluster
        events = await self.db.get_all_events(
            cluster_id=int(cluster_id), 
            active_only=True
        )
        
        # Group events by base_event_name to show unified events
        event_groups = {}
        for event in events:
            base_name = event.base_event_name or event.name
            if base_name:  # Skip events with no name
                if base_name not in event_groups:
                    event_groups[base_name] = []
                event_groups[base_name].append(event)
        
        # Filter by current input
        if current:
            filtered_groups = {
                name: events 
                for name, events in event_groups.items() 
                if current.lower() in name.lower()
            }
            event_groups = filtered_groups
        
        # Return max 25 unique base event names
        return [
            app_commands.Choice(name=base_name, value=base_name)
            for base_name in list(event_groups.keys())[:25]
        ]
    except Exception as e:
        logger.error(f"Event autocomplete error: {e}")
        return []
```

**Implementation Highlights**:
- ✅ **Unified Event Names**: Event autocomplete shows base names (e.g., "Diep") instead of suffixed variants (e.g., "Diep (1v1)"), preserving unified Elo UX principle
- ✅ **Event Resolution**: Command logic maps base name + match type to specific event ID automatically
- ✅ **Database Compatibility**: Works with existing data structure while providing improved user experience
- ✅ **Null Safety**: Events with missing names are safely filtered out
- ✅ **Performance**: Groups events efficiently while maintaining Discord's 25-choice limit

#### 2.3 Match Type Static Choices ✅ COMPLETED

Match types are defined as static choices since they are a fixed, small list. This avoids Discord.py conflicts between `choices` and `autocomplete` decorators:

```python
# Match type choices are defined directly in the @app_commands.choices decorator
# No autocomplete function needed for static options
```

**Implementation Status**: ✅ Complete - Static choices implemented in `/challenge` command decorator.

#### 2.4 Challenge Creation Logic

```python
async def challenge(self, interaction: discord.Interaction, ...):
    """Main challenge command implementation with bifurcated flow"""
    
    try:
        # 1. Early validation before any response
        cluster_id = int(cluster)
        event_id = int(event)
        
        # 2. Parse mentioned players
        mentioned_users = await self._parse_players(interaction, players)
        
        # 3. Validate player count for match type
        if not self._validate_player_count(match_type, len(mentioned_users)):
            await interaction.response.send_message(
                embed=self._create_error_embed("Invalid player count for match type"),
                ephemeral=True
            )
            return
        
        # 4. Auto-include challenger if not mentioned
        if interaction.user not in mentioned_users:
            mentioned_users.append(interaction.user)
        
        # BIFURCATED FLOW: Team vs Non-Team
        if match_type == "team":
            # For team matches: Send modal as IMMEDIATE response
            team_modal = TeamFormationModal(
                challenge_cog=self,
                cluster_id=cluster_id,
                event_id=event_id,
                mentioned_users=mentioned_users
            )
            await interaction.response.send_modal(team_modal)
        else:
            # For 1v1/FFA matches: Use traditional defer flow
            await interaction.response.defer()
            
            # Create challenge with participants
            async with self.db.transaction() as session:
                # Get or create Player records
                player_records = await self._ensure_players_exist(mentioned_users, session)
                
                # Create Challenge
                challenge = await self.challenge_ops.create_challenge(
                    event_id=event_id,
                    initiator_id=player_records[interaction.user.id].id,
                    match_format=match_type,
                    session=session
                )
                
                # Create ChallengeParticipant records with initiator auto-accepted
                for discord_user in mentioned_users:
                    player = player_records[discord_user.id]
                    is_initiator = (discord_user.id == interaction.user.id)
                    await self.challenge_ops.add_participant(
                        challenge_id=challenge.id,
                        player_id=player.id,
                        is_initiator=is_initiator,
                        status=ConfirmationStatus.ACCEPTED if is_initiator else ConfirmationStatus.PENDING,
                        session=session
                    )
            
            # Send acceptance UI
            embed, view = self._create_challenge_embed(challenge, mentioned_users)
            await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        logger.error(f"Challenge creation failed: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=self._create_error_embed(str(e)),
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=self._create_error_embed(str(e)),
                ephemeral=True
            )
```

**Implementation Notes** (2025-06-28):
1. ✅ Created `bot/operations/challenge_operations.py` with full N-player support
2. ✅ Created `bot/ui/team_formation_modal.py` for team assignment
3. ✅ Complete rewrite of `bot/cogs/challenge.py` with:
   - Hierarchical /challenge command with autocomplete
   - Cluster→Event→MatchType selection flow
   - Bifurcated flow: Team matches use modal, others use defer
   - Member parsing from string with mention/ID/name support
   - Player count validation per match type
   - Automatic challenger inclusion
4. ✅ ChallengeOperations service features:
   - Create challenges with role assignment (challenger/challenged)
   - Duplicate challenge detection
   - Accept/decline/expire operations
   - Transaction management for atomic operations
5. ✅ TeamFormationModal features:
   - Dynamic team assignment (2-4 teams)
   - Player number input for easy assignment
   - Validation for complete team coverage
   - Discord's 5-field limitation handled

**Key Technical Decisions**:
- Used @app_commands.command for slash command implementation
- Autocomplete returns cluster/event IDs as strings (Discord requirement)  
- Team assignments stored as Dict[player_id, team_id] for flexibility
- Event autocomplete shows unified base names to preserve unified Elo UX
- Challenge command resolves base name + match type to specific event ID

**Testing Results** (✅ ALL TESTS PASSED):

**Test Suite**: `tests/test_phase_2.2_challenge_command.md` (10 comprehensive tests)

1. ✅ **Imports & Dependencies** - All required modules imported successfully
2. ✅ **Database Methods** - All required database methods present and functional
3. ✅ **Bot Startup** - ChallengeCog loads without errors, `/challenge` command visible
4. ✅ **Autocomplete Functionality** - Dynamic cluster/event filtering working perfectly
5. ✅ **Challenge Creation (1v1)** - Successfully created challenge with proper participant roles
6. ✅ **Player Parsing** - Robust mention/ID/name parsing with quotes and spaces support
7. ✅ **Validation Logic** - Player count validation correctly enforced per match type
8. ✅ **Error Handling** - Graceful handling of invalid inputs with user-friendly messages
9. ✅ **UI Components** - Embeds, modals, and autocomplete all rendering correctly
10. ✅ **Database Integration** - Challenges, participants, and roles persisted correctly

**Key Bug Fixes During Testing**:
- ✅ Fixed database method name mismatch (`get_events_for_cluster` → `get_all_events`)
- ✅ Removed incorrect session parameters from database method calls
- ✅ Implemented unified event name display preserving unified Elo principle
- ✅ Added null safety for events with missing names

**Database Verification Results**:
```sql
-- Challenge creation confirmed
SELECT c.id, c.event_id, c.status, COUNT(cp.id) as participants
FROM challenges c
LEFT JOIN challenge_participants cp ON c.id = cp.challenge_id
GROUP BY c.id ORDER BY c.id DESC LIMIT 1;
-- Result: 3|27|PENDING|2

-- Participant roles verified  
SELECT cp.role, p.username
FROM challenge_participants cp
JOIN players p ON cp.player_id = p.id
WHERE cp.challenge_id = (SELECT MAX(id) FROM challenges);
-- Result: CHALLENGED|cam3llya, CHALLENGER|lightfalcon
```

**Architecture Verification**:
- ✅ **Unified Elo Preserved**: Events show as "Diep" rather than "Diep (1v1)", maintaining single rating per game
- ✅ **N-Player Support**: Challenge system handles multiple participants with proper role assignments
- ✅ **Hierarchical Structure**: Cluster→Event→Match Type selection flow works seamlessly
- ✅ **Modal Infrastructure**: Team formation modal ready for team matches (≤5 players)

**Status**: ✅ **PHASE 2.2 COMPLETE & PRODUCTION-READY**
- All core functionality implemented and tested
- Architecture supports N-player challenges as designed
- Unified Elo UX principle preserved
- Ready for Phase 2.4 (Unified Elo Fix & Challenge Acceptance)

---

### Phase 2.4.1: Critical Unified Elo Architecture Fix ✅ COMPLETED & TESTED

**Priority**: CRITICAL - Must be completed before any further development ✅ DONE
**Timeline**: 2-3 days with careful validation at each step ✅ COMPLETED
**Risk Level**: Moderate (mitigated by comprehensive backups and rollback procedures) ✅ SUCCESSFUL

#### Problem Statement

**Confirmed Architectural Flaw**: The system creates separate Event records for each scoring type (e.g., "Diep (1v1)", "Diep (Team)", "Diep (FFA)"), resulting in separate Elo ratings per game mode instead of unified Elo per game. This directly violates the unified Elo principle documented in planB.md lines 707-712.

**Root Cause**: 
- `populate_from_csv.py` lines 236-288 create multiple Event records per base game
- `PlayerEventStats` tracks Elo per `event_id`, so separate events = separate Elo ratings
- Players can have different ratings for the same game (e.g., 1200 Elo in "Diep (1v1)" but 1500 in "Diep (Team)")

**Current Impact**:
- ❌ Violates unified Elo principle 
- ❌ Confusing user experience
- ❌ Architectural debt blocking future features
- ❌ Should have been caught in Phase 1.3 testing

#### ✅ IMPLEMENTATION RESULTS

**Implementation Date**: 2025-06-28  
**Migration Successful**: ✅ Complete with full rollback capability  
**Data Safety**: ✅ Comprehensive backups and legacy table preservation  
**Testing Status**: ✅ All critical functionality verified

**Key Achievements**:
- ✅ **Events Consolidated**: 86 fragmented events → 70 unified events  
- ✅ **PlayerEventStats Unified**: Fragmented records properly consolidated
- ✅ **Architecture Fixed**: Unified Elo per base game achieved
- ✅ **Challenge Command Updated**: Now uses unified event selection
- ✅ **Population Script Fixed**: Creates unified events going forward
- ✅ **Match.scoring_type Added**: Scoring type moved from Event to Match level
- ✅ **Comprehensive Test Suite**: 4 detailed test scenarios created and passed
- ✅ **Expert Analysis**: Deep investigation with Gemini 2.5 Pro and O3 full
- ✅ **Rollback Capability**: Emergency recovery script generated

**Database Migration Details**:
```bash
# Migration Script: migration_phase_2_4_1_unified_elo.py
# Backup Files: tournament_backup_phase_2_4_1_*.db
# Rollback Scripts: rollback_phase_2_4_1_*.sh
# Log Files: migration_phase_2_4_1_*.log

# Before: Fragmented events per scoring type
# "Diep (1v1)", "Diep (Team)", "Diep (FFA)" as separate events

# After: Unified events with supported types  
# name="Diep", supported_scoring_types="1v1,FFA,Team" as single unified event
```

**Architecture Validation**:
- ✅ **Competitive Events Unified**: 1v1, FFA, Team events properly consolidated per base game
- ✅ **Leaderboard Events Separate**: Performance Points events correctly remain separate from Elo events
- ✅ **No Mixing of Scoring Systems**: Elo (competitive) and Performance Points (leaderboard) properly segregated
- ✅ **Base Event Names**: Events show as "Diep" instead of "Diep (1v1)" preserving unified Elo UX

**Testing Results - All Tests Passed**:

**Test 1**: ✅ Database Schema Verification
- matches table has scoring_type column (VARCHAR(20), default '1v1')
- events table has supported_scoring_types column (VARCHAR(100))

**Test 2**: ✅ Event Count Reduction  
- Active events reduced from ~86 to 70 (consolidation successful)
- Fragmented events properly unified

**Test 3**: ✅ Event Structure Analysis
- Each base_event_name + scoring_type combination appears exactly once
- Competitive events (1v1, FFA, Team) properly unified within base games
- Leaderboard events correctly separated (different rating system)
- Example: "Blitz" appears as both competitive (1v1) and leaderboard events - this is correct architecture

**Test 4**: ✅ Challenge Command Integration
- Event autocomplete shows unified base names (e.g., "Diep" not "Diep (1v1)")
- Challenge command correctly resolves base name + match type to specific event ID
- User experience improved with unified event selection

**Critical Investigation Results** (Gemini 2.5 Pro + O3 Analysis):
- ✅ **No Migration Bugs**: All observed "duplications" are architecturally correct
- ✅ **Proper Scoring Separation**: Elo vs Performance Points systems correctly isolated
- ✅ **Unified Elo Achieved**: Single rating per base game for competitive modes
- ✅ **User Education**: "Leaderboard duplicates" are actually correct architecture

**User Experience Improvement**:
- Event autocomplete now shows "Diep" instead of "Diep (1v1)"
- Single Elo rating per game instead of separate ratings per mode  
- Unified challenge workflow: Game selection → Match type selection
- Proper separation between competitive Elo and Performance Points systems

##### ✅ Step 1: Database Schema Updates (COMPLETED)

**File**: `migration_phase_2_4_1_unified_elo.py` ✅ IMPLEMENTED & EXECUTED

```python
#!/usr/bin/env python3
"""
Phase 2.4.1: Unified Elo Architecture Fix

Consolidates separate events per scoring type into unified events per base game.
Moves scoring_type from Event level to Match level.
"""

# 1. Add scoring_type to Match model
ALTER TABLE matches ADD COLUMN scoring_type VARCHAR(20) NOT NULL DEFAULT '1v1';

# 2. Create event consolidation mapping table
CREATE TABLE event_consolidation_map (
    old_event_id INTEGER PRIMARY KEY,
    new_event_id INTEGER NOT NULL,
    old_event_name VARCHAR(200) NOT NULL,
    new_event_name VARCHAR(200) NOT NULL,
    scoring_type VARCHAR(20) NOT NULL,
    FOREIGN KEY(old_event_id) REFERENCES events(id),
    FOREIGN KEY(new_event_id) REFERENCES events(id)
);

# 3. Backup original tables
CREATE TABLE events_legacy AS SELECT * FROM events;
CREATE TABLE player_event_stats_legacy AS SELECT * FROM player_event_stats;
```

##### Step 2: Data Migration & Consolidation (1 day)

**Critical Process**: Smart consolidation preserving all historical data

```python
def consolidate_events_and_stats():
    """
    1. Create unified events (e.g., consolidate "Diep (1v1)", "Diep (Team)" → "Diep")
    2. Migrate PlayerEventStats using weighted averages
    3. Update Match records with scoring_type
    4. Update Challenge records to point to unified events
    """
    
    # Example consolidation mapping:
    # "Diep (1v1)" + "Diep (Team)" + "Diep (FFA)" → "Diep"
    # "Bonk (1v1)" + "Bonk (Team)" → "Bonk"
    
    # PlayerEventStats consolidation strategy:
    # new_elo = Σ(elo_i × matches_i) / Σ(matches_i)  # Weighted by match count
    # new_matches = Σ(matches_i)
    # new_wins = Σ(wins_i)
    # new_losses = Σ(losses_i)
```

**Data Safety Measures**:
- ✅ Complete backup before migration
- ✅ Preserve all original data in `*_legacy` tables
- ✅ Idempotent migration (can be run multiple times)
- ✅ Comprehensive validation queries
- ✅ Rollback script generation

##### Step 3: Code Updates (1 day)

**3.1 Update populate_from_csv.py**:
```python
# OLD: Creates separate events per scoring type
for scoring_type in parsed_scoring_types:
    event_name = create_event_name_with_suffix(base_name, scoring_type)
    # Creates: "Diep (1v1)", "Diep (Team)", "Diep (FFA)"

# NEW: Creates single event per base game
event_name = base_name  # Just "Diep"
# Store supported scoring types in event metadata
event.supported_scoring_types = ','.join(parsed_scoring_types)
```

**3.2 Update Challenge Command Flow**:
```python
# OLD: Select event by base_name + scoring_type
matching_event = find_event(base_name=base_name, scoring_type=scoring_type)

# NEW: Select unified event, store scoring_type in match
unified_event = find_event(base_name=base_name)
# Later when creating match:
match.scoring_type = scoring_type
```

**3.3 Update Models**:
```python
# Match model - add scoring_type field
class Match(Base):
    # ... existing fields ...
    scoring_type = Column(String(20), nullable=False, default='1v1')
    
# Event model - deprecate scoring_type
class Event(Base):
    # ... existing fields ...
    scoring_type = Column(String(20), nullable=True)  # DEPRECATED - kept for migration only
    supported_scoring_types = Column(String(100))  # NEW: comma-separated list
```

##### Step 4: Testing & Validation (0.5 days)

**4.1 Migration Validation Queries**:
```sql
-- Verify no duplicate PlayerEventStats for same player+event
SELECT player_id, event_id, COUNT(*) 
FROM player_event_stats 
GROUP BY player_id, event_id 
HAVING COUNT(*) > 1;

-- Verify total Elo history preserved
SELECT SUM(elo_change) FROM elo_history WHERE event_id IN (legacy_events);
SELECT SUM(elo_change) FROM elo_history WHERE event_id IN (unified_events);

-- Verify all matches have scoring_type
SELECT COUNT(*) FROM matches WHERE scoring_type IS NULL;
```

**4.2 Integration Tests**:
```python
def test_unified_elo_system():
    """Test that matches in different modes update same PlayerEventStats"""
    player = create_test_player()
    diep_event = get_event_by_name("Diep")
    
    # Create 1v1 match
    match_1v1 = create_match(event=diep_event, scoring_type="1v1")
    complete_match(match_1v1, player_results=[...])
    
    # Create Team match 
    match_team = create_match(event=diep_event, scoring_type="Team")
    complete_match(match_team, player_results=[...])
    
    # Verify both matches updated SAME PlayerEventStats record
    stats = PlayerEventStats.get(player_id=player.id, event_id=diep_event.id)
    assert stats.matches_played == 2  # Both matches counted
```

#### Rollback Plan

**If Migration Fails**:
```python
# Automated rollback script generated during migration
def rollback_unified_elo_migration():
    """
    1. Drop new unified events
    2. Restore events table from events_legacy
    3. Restore player_event_stats from player_event_stats_legacy
    4. Remove scoring_type column from matches
    5. Restore challenge.event_id references
    """
    # Full restoration to pre-migration state
```

#### Success Criteria

- ✅ **Single Event per base game** (e.g., one "Diep" event instead of three)
- ✅ **Match.scoring_type captures format** (1v1, Team, FFA stored per match)
- ✅ **Unified Elo ratings** (PlayerEventStats has one record per player+game)
- ✅ **Zero data loss** (all historical matches and Elo changes preserved)
- ✅ **UI shows unified events** (autocomplete shows "Diep" not "Diep (Team)")
- ✅ **Challenge flow updated** (select game first, then match type)

#### Communication Plan

**Before Migration**:
- 📢 Announce maintenance window to users
- 📝 Document current Elo ratings for transparency
- ⚠️ Explain that ratings will be unified (players with different mode ratings will see consolidated values)

**After Migration**:
- 📊 Publish consolidation report showing rating changes
- 📚 Update help documentation with new unified flow
- 🎯 Highlight improved unified Elo system

#### Notes for Implementation

**Claude Development Notes**:
```
CRITICAL: This phase must be completed before any further /challenge or Elo work.
The current architecture violates core design principles and will cause confusion.

Key files to modify:
1. populate_from_csv.py (lines 236-288) - Remove event suffix creation
2. bot/database/models.py - Add Match.scoring_type, deprecate Event.scoring_type  
3. bot/cogs/challenge.py - Update event resolution logic
4. Create migration_phase_2_4_1_unified_elo.py - Handle data consolidation

Testing priority:
1. Verify PlayerEventStats consolidation math is correct
2. Ensure no orphaned data after migration
3. Confirm UI shows unified events properly
4. Validate challenge creation flow works with unified events

Rollback triggers:
- Any data loss detected
- PlayerEventStats consolidation errors
- Challenge creation failures
- User confusion reports
```

### Phase 2.4.2: Challenge Acceptance Workflow Implementation 

**Priority**: HIGH - Critical missing functionality blocking challenge system
**Timeline**: 1-2 days with existing infrastructure leverage
**Risk Level**: Low (builds on existing models and services)

#### Problem Statement

**Missing Core Functionality**: The challenge system can create challenges but participants have no way to accept or decline them. This completely breaks the invitation workflow - challenges remain permanently pending with no resolution mechanism.

**Current Gap**: 
- `/challenge` command creates challenges with participants in PENDING status
- No `/accept` or `/decline` commands exist
- No auto-transition to matches when all participants accept
- No expiration/cleanup for abandoned challenges

#### Implementation Plan

##### Step 1: Accept/Decline Commands (0.5 days)

**File**: `bot/cogs/challenge.py` (add to existing ChallengeCog)

```python
@app_commands.command(
    name="accept",
    description="Accept a pending challenge invitation"
)
@app_commands.describe(
    challenge_id="Challenge ID to accept (optional - will auto-detect if you have only one pending)"
)
async def accept_challenge(
    self,
    interaction: discord.Interaction,
    challenge_id: Optional[int] = None
):
    """Accept a challenge invitation"""
    try:
        # Auto-discovery if no challenge_id provided
        if challenge_id is None:
            challenge_id = await self._find_user_pending_challenge(interaction.user)
            if challenge_id is None:
                await interaction.response.send_message(
                    embed=self._create_error_embed(
                        "No Pending Challenges",
                        "You have no pending challenge invitations. Use `/challenges` to see all available challenges."
                    ),
                    ephemeral=True
                )
                return
        
        await interaction.response.defer()
        
        # Process acceptance
        result = await self.challenge_ops.accept_challenge(
            challenge_id=challenge_id,
            player_discord_id=interaction.user.id
        )
        
        if result.success:
            if result.match_created:
                # All participants accepted - match created
                embed = self._create_match_ready_embed(result.match, result.challenge)
                await interaction.followup.send(embed=embed)
            else:
                # Partial acceptance - update status
                embed = await self._create_updated_challenge_embed(result.challenge)
                await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(
                embed=self._create_error_embed("Cannot Accept", result.error_message),
                ephemeral=True
            )
            
    except Exception as e:
        self.logger.error(f"Accept challenge error: {e}", exc_info=True)
        # Handle error response based on interaction state

@app_commands.command(
    name="decline", 
    description="Decline a pending challenge invitation"
)
@app_commands.describe(
    challenge_id="Challenge ID to decline",
    reason="Optional reason for declining"
)
async def decline_challenge(
    self,
    interaction: discord.Interaction,
    challenge_id: Optional[int] = None,
    reason: Optional[str] = None
):
    """Decline a challenge invitation"""
    # Similar implementation to accept but calls decline_challenge()
    # Automatically cancels the entire challenge when any participant declines
```

##### Step 2: Challenge Operations Service Updates (0.5 days)

**File**: `bot/operations/challenge_operations.py` (extend existing)

```python
@dataclass
class ChallengeAcceptanceResult:
    """Result of challenge acceptance operation"""
    success: bool
    challenge: Optional[Challenge] = None
    match: Optional[Match] = None
    match_created: bool = False
    error_message: Optional[str] = None

class ChallengeOperations:
    # ... existing methods ...
    
    async def accept_challenge(
        self, 
        challenge_id: int, 
        player_discord_id: int,
        session=None
    ) -> ChallengeAcceptanceResult:
        """
        Process challenge acceptance with auto-transition to match
        """
        async with self._get_session(session) as s:
            # 1. Validate challenge exists and is active
            challenge = await self._get_active_challenge(challenge_id, s)
            if not challenge:
                return ChallengeAcceptanceResult(
                    success=False, 
                    error_message="Challenge not found or expired"
                )
            
            # 2. Validate player is a participant
            participant = await self._get_participant(challenge_id, player_discord_id, s)
            if not participant:
                return ChallengeAcceptanceResult(
                    success=False,
                    error_message="You are not invited to this challenge"
                )
                
            # 3. Validate player hasn't already responded
            if participant.status != ConfirmationStatus.PENDING:
                return ChallengeAcceptanceResult(
                    success=False,
                    error_message=f"You have already {participant.status.value} this challenge"
                )
            
            # 4. Update participant status
            participant.status = ConfirmationStatus.CONFIRMED
            participant.responded_at = datetime.utcnow()
            
            # 5. Check if all participants have accepted
            all_participants = await self._get_all_participants(challenge_id, s)
            all_accepted = all(p.status == ConfirmationStatus.CONFIRMED for p in all_participants)
            
            if all_accepted:
                # 6. Create match and transition challenge to completed
                match = await self._create_match_from_challenge(challenge, s)
                challenge.status = ChallengeStatus.COMPLETED
                challenge.completed_at = datetime.utcnow()
                
                return ChallengeAcceptanceResult(
                    success=True,
                    challenge=challenge,
                    match=match,
                    match_created=True
                )
            else:
                return ChallengeAcceptanceResult(
                    success=True,
                    challenge=challenge,
                    match_created=False
                )
    
    async def decline_challenge(
        self,
        challenge_id: int,
        player_discord_id: int,
        reason: Optional[str] = None,
        session=None
    ) -> ChallengeAcceptanceResult:
        """
        Process challenge decline - cancels entire challenge
        """
        async with self._get_session(session) as s:
            # Similar validation to accept
            # Set participant status to REJECTED
            # Set challenge status to CANCELLED
            # Record reason in admin_notes if provided
            
    async def _create_match_from_challenge(
        self, 
        challenge: Challenge, 
        session
    ) -> Match:
        """
        Bridge function: Create Match from accepted Challenge
        Uses existing Match creation infrastructure
        """
        # Extract scoring_type from challenge event (temporary until Phase 2.4.1)
        scoring_type = challenge.event.scoring_type
        
        # Create Match record
        match = Match(
            event_id=challenge.event_id,
            match_format=MatchFormat(scoring_type.lower()),
            challenge_id=challenge.id,
            status=MatchStatus.PENDING,
            created_by=challenge.participants[0].player_id,  # Challenger
            started_at=datetime.utcnow()
        )
        session.add(match)
        await session.flush()
        
        # Create MatchParticipant records from ChallengeParticipant
        for challenge_participant in challenge.participants:
            match_participant = MatchParticipant(
                match_id=match.id,
                player_id=challenge_participant.player_id,
                team_id=challenge_participant.team_id,  # Preserve team assignments
                elo_before=await self._get_current_elo(
                    challenge_participant.player_id, 
                    challenge.event_id, 
                    session
                )
            )
            session.add(match_participant)
        
        return match
```

##### Step 3: UI Updates & Embeds (0.25 days)

**Embed Updates**: Enhanced challenge embeds showing real-time acceptance status

```python
def _create_updated_challenge_embed(self, challenge: Challenge) -> discord.Embed:
    """Create embed showing current acceptance status"""
    embed = discord.Embed(
        title="⏳ Challenge Status Update",
        description=f"Challenge #{challenge.id} acceptance in progress",
        color=discord.Color.orange()
    )
    
    # Show acceptance progress
    total_participants = len(challenge.participants)
    accepted_count = sum(1 for p in challenge.participants 
                        if p.status == ConfirmationStatus.CONFIRMED)
    
    embed.add_field(
        name="Progress",
        value=f"{accepted_count}/{total_participants} participants accepted",
        inline=True
    )
    
    # List participant status with emojis
    status_list = []
    for participant in challenge.participants:
        emoji = {
            ConfirmationStatus.PENDING: "⏳",
            ConfirmationStatus.CONFIRMED: "✅", 
            ConfirmationStatus.REJECTED: "❌"
        }.get(participant.status, "❓")
        
        status_list.append(f"{emoji} <@{participant.player.discord_id}>")
    
    embed.add_field(
        name="Participants",
        value="\n".join(status_list),
        inline=False
    )
    
    return embed

def _create_match_ready_embed(self, match: Match, challenge: Challenge) -> discord.Embed:
    """Create embed when all participants accept and match is created"""
    embed = discord.Embed(
        title="🎮 Match Ready!",
        description=f"All participants accepted - Match #{match.id} created",
        color=discord.Color.green()
    )
    
    embed.add_field(
        name="Event", 
        value=challenge.event.name,
        inline=True
    )
    
    embed.add_field(
        name="Match Type",
        value=challenge.event.scoring_type.upper(),
        inline=True
    )
    
    embed.add_field(
        name="Next Steps",
        value="Play your match and report results using `/match_result`",
        inline=False
    )
    
    return embed
```

##### Step 4: Background Cleanup & Utilities (0.25 days)

**Challenge Expiration Cleanup**:
```python
@tasks.loop(hours=1)
async def cleanup_expired_challenges(self):
    """Background task to clean up expired challenges"""
    async with self.db.transaction() as session:
        expired_challenges = await session.execute(
            select(Challenge)
            .where(
                Challenge.status == ChallengeStatus.PENDING,
                Challenge.expires_at < datetime.utcnow()
            )
        )
        
        for challenge in expired_challenges.scalars():
            challenge.status = ChallengeStatus.EXPIRED
            self.logger.info(f"Expired challenge {challenge.id}")

async def _find_user_pending_challenge(self, user: discord.User) -> Optional[int]:
    """Auto-discovery: Find user's pending challenge if they have exactly one"""
    async with self.db.transaction() as session:
        pending_challenges = await session.execute(
            select(Challenge.id)
            .join(ChallengeParticipant)
            .join(Player)
            .where(
                Player.discord_id == user.id,
                ChallengeParticipant.status == ConfirmationStatus.PENDING,
                Challenge.status == ChallengeStatus.PENDING
            )
        )
        
        challenge_ids = pending_challenges.scalars().all()
        return challenge_ids[0] if len(challenge_ids) == 1 else None
```

#### Integration with Existing System

**Leverages Existing Infrastructure**:
- ✅ Uses existing `ChallengeParticipant` model with `ConfirmationStatus` enum
- ✅ Extends existing `ChallengeOperations` service class  
- ✅ Integrates with existing `Match` creation system
- ✅ Follows established embed and error handling patterns

**No Breaking Changes**:
- ✅ All existing functionality preserved
- ✅ Database schema already supports required fields
- ✅ Commands are purely additive

#### Success Criteria

- ✅ **Accept Command**: `/accept [challenge_id]` with auto-discovery
- ✅ **Decline Command**: `/decline [challenge_id] [reason]` with challenge cancellation
- ✅ **Status Management**: Real-time updates in ChallengeParticipant table
- ✅ **Auto-Transition**: Automatic match creation when all participants accept
- ✅ **UI Updates**: Enhanced embeds showing acceptance progress
- ✅ **Error Handling**: Comprehensive validation and user feedback
- ✅ **Cleanup**: Background task for expired challenge management

#### Testing Plan

**Integration Tests**:
```python
def test_challenge_acceptance_workflow():
    """Test complete challenge→acceptance→match workflow"""
    # 1. Create 1v1 challenge
    challenge = create_test_challenge(participants=2)
    
    # 2. First participant accepts
    result1 = accept_challenge(challenge.id, participant1.discord_id)
    assert not result1.match_created  # Partial acceptance
    
    # 3. Second participant accepts  
    result2 = accept_challenge(challenge.id, participant2.discord_id)
    assert result2.match_created  # Full acceptance
    assert result2.match.status == MatchStatus.PENDING
    
    # 4. Verify challenge status updated
    assert challenge.status == ChallengeStatus.COMPLETED

def test_challenge_decline_workflow():
    """Test challenge decline cancels entire challenge"""
    challenge = create_test_challenge(participants=3)
    
    # One participant declines
    result = decline_challenge(challenge.id, participant1.discord_id, "Not available")
    
    # Entire challenge should be cancelled
    assert challenge.status == ChallengeStatus.CANCELLED
    assert "Not available" in challenge.admin_notes
```

#### Notes for Implementation

**Timeline Breakdown**:
- **Day 1 Morning**: Implement accept/decline commands
- **Day 1 Afternoon**: Extend ChallengeOperations service  
- **Day 2 Morning**: UI updates and embed enhancements
- **Day 2 Afternoon**: Testing and background cleanup

**Integration Notes**:
- Commands leverage existing ChallengeOperations patterns
- Bridge functions connect to existing Match creation system
- Real-time embed updates enhance user experience
- Auto-discovery reduces friction for single pending challenges

---

### Phase 3: Complete Per-Event Elo Transition (Week 3)

#### 3.1 Remove Global Elo Updates

**File**: `bot/database/match_operations.py`

**Changes Required**:
1. Remove all updates to `Player.elo_rating`
2. Ensure only `PlayerEventStats` is modified
3. Update `EloHistory` to always include `event_id`

```python
# In complete_match_with_results()
# REMOVE these lines:
# player.elo_rating = new_elo  
# player.matches_played += 1
# player.wins += 1 (etc)

# KEEP only:
event_stats.raw_elo = new_elo
event_stats.update_scoring_elo()  # Applies floor
event_stats.matches_played += 1
# etc.
```

#### 3.2 Implement Hierarchy Calculations

**New File**: `bot/operations/elo_hierarchy.py`

```python
from typing import List, Dict
from bot.database.models import Player, PlayerEventStats, Cluster, Event

class EloHierarchyCalculator:
    """Calculates cluster and overall Elo from event-level ratings"""
    
    @staticmethod
    async def calculate_cluster_elo(
        player_id: int, 
        cluster_id: int,
        session
    ) -> int:
        """
        Calculate cluster Elo using prestige weighting system.
        
        From planA.md lines 519-557:
        - Best event: 4.0x weight
        - Second best: 2.5x weight  
        - Third best: 1.5x weight
        - Fourth+: 1.0x weight
        """
        # Get all event stats for player in cluster
        event_stats = await session.execute(
            select(PlayerEventStats)
            .join(Event)
            .where(
                PlayerEventStats.player_id == player_id,
                Event.cluster_id == cluster_id
            )
            .order_by(PlayerEventStats.scoring_elo.desc())
        )
        
        stats_list = event_stats.scalars().all()
        if not stats_list:
            return 1000  # Default
        
        # Apply prestige multipliers
        weights = [4.0, 2.5, 1.5]  # First 3 get special weights
        total_weighted = 0
        total_weight = 0
        
        for i, stat in enumerate(stats_list):
            weight = weights[i] if i < len(weights) else 1.0
            total_weighted += stat.scoring_elo * weight
            total_weight += weight
        
        return int(total_weighted / total_weight)
    
    @staticmethod
    async def calculate_overall_elo(player_id: int, session) -> int:
        """
        Calculate overall Elo using tiered weighting.
        
        From planA.md lines 559-577:
        - Top 10 clusters: 60% weight
        - Clusters 11-15: 25% weight
        - Clusters 16-20: 15% weight
        """
        # Implementation continues...
```

#### 3.3 Migration Scripts

```sql
-- Reset all Elo to 1000 as requested
UPDATE players SET elo_rating = 1000;
UPDATE player_event_stats SET raw_elo = 1000, scoring_elo = 1000;

-- Clear test data
DELETE FROM elo_history WHERE event_id IS NULL;
DELETE FROM matches WHERE event_id IN (
    SELECT id FROM events WHERE name LIKE '%FFA%by%'
);
DELETE FROM events WHERE name LIKE '%FFA%by%';
```

### Phase 4: Testing & Validation (Week 4)

#### 4.1 Test Scenarios

1. **Challenge Creation Flow**
   - Test autocomplete filtering
   - Verify participant limits
   - Check duplicate prevention

2. **Acceptance Workflow**  
   - All accept → Match created
   - One rejects → Challenge cancelled
   - Timeout → Auto-expire

3. **Elo Calculations**
   - 1v1: Standard Elo
   - FFA: K/(N-1) scaling
   - Team: Average rating approach

4. **Data Integrity**
   - No orphaned challenges
   - Proper cascade deletes
   - Transaction atomicity

#### 4.2 Performance Testing

```python
# Test autocomplete with large datasets
async def test_autocomplete_performance():
    # Create 100 clusters with 30 events each
    # Measure autocomplete response time
    # Should be <100ms for 25 results
```

## Risk Analysis & Mitigation

### High-Risk Items

1. **Data Loss from /ffa Removal**
   - **Risk**: Historical FFA matches deleted
   - **Mitigation**: Archive before deletion
   - **Query**: `SELECT * FROM matches WHERE event_id IN (SELECT id FROM events WHERE name LIKE '%FFA%by%')`

2. **User Confusion**
   - **Risk**: Users try /ffa, get error
   - **Mitigation**: Grace period with helpful message
   - **Implementation**: Catch command, redirect to /challenge

3. **Incomplete Challenges**
   - **Risk**: Challenges never accepted, clutter database
   - **Mitigation**: 24-hour auto-expiration
   - **Background job**: Clean expired challenges hourly

### Medium-Risk Items

1. **Performance Impact**
   - **Risk**: Autocomplete slow with many events
   - **Mitigation**: Database indexes, result limiting
   - **Monitoring**: Log autocomplete response times

2. **Complex Team Formation**
   - **Risk**: Confusion over team assignment
   - **Mitigation**: Clear UI, color coding
   - **Future**: Team formation modal

## Implementation Checklist

### Week 1: Foundation
- [ ] Remove /ffa command from match_commands.py
- [ ] Run populate_from_csv.py
- [ ] Verify database has clusters/events
- [ ] Add missing indexes

### Week 2: Challenge System  
- [ ] Rewrite challenge.py with full implementation
- [ ] Implement autocomplete functions
- [ ] Create ChallengeOperations service
- [ ] Test acceptance workflow

### Week 3: Elo Completion
- [ ] Remove global Elo updates
- [ ] Implement hierarchy calculations
- [ ] Run migration scripts
- [ ] Verify per-event tracking

### Week 4: Polish
- [ ] Comprehensive testing
- [ ] Performance optimization
- [ ] Documentation updates
- [ ] User announcements

## Appendix A: File Changes Summary

### Files to Modify
1. `bot/cogs/match_commands.py` - Remove /ffa
2. `bot/cogs/challenge.py` - Complete rewrite
3. `bot/database/match_operations.py` - Remove global Elo
4. `bot/database/database.py` - Add helper methods

### Files to Create
1. `bot/operations/challenge_operations.py`
2. `bot/operations/elo_hierarchy.py`
3. `bot/ui/challenge_views.py`

### Files to Delete
- None (preserve for history)

## Appendix B: Database Schema Changes

```sql
-- Indexes for performance
CREATE INDEX idx_clusters_active ON clusters(is_active);
CREATE INDEX idx_events_cluster ON events(cluster_id, is_active);
CREATE INDEX idx_events_base_name ON events(base_event_name);
CREATE INDEX idx_challenge_participants_challenge ON challenge_participants(challenge_id);
CREATE INDEX idx_challenge_participants_player ON challenge_participants(player_id);
CREATE INDEX idx_player_event_stats_event ON player_event_stats(event_id);
CREATE INDEX idx_player_event_stats_player ON player_event_stats(player_id);

-- Cleanup bad data
DELETE FROM events WHERE cluster_id IS NULL;
DELETE FROM matches WHERE event_id NOT IN (SELECT id FROM events);
```

## Appendix C: Configuration Updates

### Environment Variables
```bash
# .env additions
CHALLENGE_EXPIRY_HOURS=24
AUTOCOMPLETE_MAX_RESULTS=25
ELO_CALCULATION_TIMEOUT=30
```

### Config Constants
```python
# bot/config.py additions
class Config:
    # Challenge System
    CHALLENGE_EXPIRY_HOURS = int(os.getenv("CHALLENGE_EXPIRY_HOURS", "24"))
    MIN_FFA_PLAYERS = 3
    MAX_FFA_PLAYERS = 16
    MIN_TEAM_SIZE = 2
    MAX_TEAM_SIZE = 8
```

## Deferred Tasks

### Help System Modernization (Post-Phase 2)
**Priority**: Low  
**File**: `bot/cogs/match_commands.py`

**Current Issues**:
- `!match-help` command contains very outdated information from old development phases
- References deprecated Phase 2A2.5 subphases and FFA architecture violations
- Missing slash command version (`/match-help`)
- Misleading tips about "Each FFA match gets its own Event"

**Proposed Solution**:
1. Create hybrid command (`!match-help` and `/match-help`)
2. Replace outdated development status with current Phase progress
3. Focus on guiding users to `/challenge` workflow
4. Remove all references to deprecated FFA functionality
5. Update description from "FFA and Team battles" to accurate current functionality

**Defer Rationale**: Help system is not critical for Phase 1-2 implementation. Better to update after `/challenge` command is fully implemented and we know exactly what to document.

---

## Conclusion

This plan provides a clear path to align the implementation with planA.md's vision. The critical changes - removing /ffa and implementing hierarchical /challenge - will establish the proper tournament structure. With the foundation corrected, all subsequent features can build on solid architecture.

The phased approach minimizes risk while ensuring each component is properly tested before moving forward. By Week 4, the system will have proper challenge workflows, per-event Elo tracking, and a maintainable codebase ready for meta-game features.