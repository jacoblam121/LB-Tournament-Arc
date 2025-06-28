# Phase 1.1 Model Updates - Test Plan

## Overview
This test plan validates the Phase 1.1 model updates including:
- New meta-game economy fields in PlayerEventStats
- ChallengeParticipant model for N-player challenges
- Challenge model relationship updates
- Row-level locking for concurrent operations

## Prerequisites
- Ensure you have a backup of your database before testing
- Python virtual environment activated
- All dependencies installed (`pip install -r requirements.txt`)

## Test Environment Setup

```bash
# 1. Create a test database backup
cp tournament.db tournament_test_backup.db

# 2. Run the migration
python migration_phase_1.1_model_updates.py

# 3. Check migration report
cat migration_report_phase_1.1_model_updates_*.txt
```

## Test Suite

### Test 1: Verify Database Schema Changes

**Objective**: Confirm all new columns and tables were created correctly

**Steps**:
```bash
# Open SQLite console
sqlite3 tournament.db

# Check PlayerEventStats columns
.schema player_event_stats

# Expected: Should see final_score, shard_bonus, shop_bonus columns

# Check ChallengeParticipant table
.schema challenge_participants

# Expected: Should see the new table with all columns

# Exit SQLite
.quit
```

**Expected Results**:
- PlayerEventStats table has three new columns: final_score (INTEGER), shard_bonus (INTEGER DEFAULT 0), shop_bonus (INTEGER DEFAULT 0)
- challenge_participants table exists with proper structure
- Unique constraint on (challenge_id, player_id) is present

### Test 2: Verify Model Relationships

**Objective**: Ensure ORM relationships work correctly

**Test Script**: Create `test_phase_1.1_relationships.py`:
```python
import asyncio
from bot.database.database import Database
from bot.database.models import Challenge, ChallengeParticipant, PlayerEventStats

async def test_relationships():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        # Test 1: Challenge.participants relationship
        result = await session.execute(
            select(Challenge).options(selectinload(Challenge.participants)).limit(1)
        )
        challenge = result.scalar_one_or_none()
        
        if challenge:
            print(f"✓ Challenge {challenge.id} has {len(challenge.participants)} participants")
        else:
            print("✓ No challenges exist yet (expected for new database)")
        
        # Test 2: PlayerEventStats new fields
        result = await session.execute(select(PlayerEventStats).limit(1))
        stats = result.scalar_one_or_none()
        
        if stats:
            print(f"✓ PlayerEventStats has new fields: final_score={stats.final_score}, "
                  f"shard_bonus={stats.shard_bonus}, shop_bonus={stats.shop_bonus}")
        else:
            print("✓ No PlayerEventStats exist yet (expected)")

if __name__ == "__main__":
    asyncio.run(test_relationships())
```

**Run**: `python test_phase_1.1_relationships.py`

### Test 3: Test ChallengeParticipant Creation

**Objective**: Verify ChallengeParticipant model works correctly

**Test Script**: Create `test_phase_1.1_participants.py`:
```python
import asyncio
from datetime import datetime, timedelta
from bot.database.database import Database
from bot.database.models import (
    Player, Event, Cluster, Challenge, ChallengeParticipant, 
    ChallengeStatus, ConfirmationStatus
)

async def test_challenge_participants():
    db = Database()
    await db.initialize()
    
    async with db.transaction() as session:
        # Create test data
        cluster = Cluster(number=99, name="Test Cluster")
        session.add(cluster)
        await session.flush()
        
        event = Event(
            name="Test Event",
            cluster_id=cluster.id,
            scoring_type="FFA"
        )
        session.add(event)
        await session.flush()
        
        # Create test players
        players = []
        for i in range(4):
            player = Player(
                discord_id=900000 + i,
                username=f"TestPlayer{i}"
            )
            session.add(player)
            players.append(player)
        await session.flush()
        
        # Create FFA challenge
        challenge = Challenge(
            event_id=event.id,
            status=ChallengeStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        session.add(challenge)
        await session.flush()
        
        # Add participants
        for i, player in enumerate(players):
            participant = ChallengeParticipant(
                challenge_id=challenge.id,
                player_id=player.id,
                status=ConfirmationStatus.PENDING,
                team_id="A" if i < 2 else "B"  # Team assignment for testing
            )
            session.add(participant)
        
        await session.commit()
        
        # Verify
        result = await session.execute(
            select(Challenge)
            .options(selectinload(Challenge.participants))
            .where(Challenge.id == challenge.id)
        )
        loaded_challenge = result.scalar_one()
        
        print(f"✓ Created FFA challenge with {len(loaded_challenge.participants)} participants")
        for p in loaded_challenge.participants:
            print(f"  - Player {p.player_id}, Team {p.team_id}, Status: {p.status.value}")

if __name__ == "__main__":
    asyncio.run(test_challenge_participants())
```

**Run**: `python test_phase_1.1_participants.py`

### Test 4: Test Row-Level Locking

**Objective**: Verify concurrent updates are handled safely

**Test Script**: Create `test_phase_1.1_locking.py`:
```python
import asyncio
from bot.database.database import Database
from bot.database.models import Player, Event, Cluster, PlayerEventStats

async def concurrent_update(db, player_id, event_id, task_id):
    """Simulate concurrent Elo updates"""
    async with db.transaction() as session:
        stats = await db.get_or_create_player_event_stats(player_id, event_id, session)
        
        # Simulate some processing time
        await asyncio.sleep(0.1)
        
        # Update Elo
        old_elo = stats.raw_elo
        stats.raw_elo += 10
        stats.scoring_elo = max(stats.raw_elo, 1000)
        
        print(f"Task {task_id}: Updated Elo from {old_elo} to {stats.raw_elo}")

async def test_concurrent_updates():
    db = Database()
    await db.initialize()
    
    # Setup test data
    async with db.transaction() as session:
        cluster = Cluster(number=98, name="Locking Test")
        session.add(cluster)
        await session.flush()
        
        event = Event(name="Locking Event", cluster_id=cluster.id)
        session.add(event)
        await session.flush()
        
        player = Player(discord_id=800000, username="LockTestPlayer")
        session.add(player)
        await session.flush()
        
        player_id = player.id
        event_id = event.id
    
    # Run concurrent updates
    print("Running 5 concurrent updates...")
    tasks = [
        concurrent_update(db, player_id, event_id, i) 
        for i in range(5)
    ]
    await asyncio.gather(*tasks)
    
    # Verify final result
    async with db.get_session() as session:
        stats = await db.get_or_create_player_event_stats(player_id, event_id, session)
        print(f"✓ Final Elo: {stats.raw_elo} (expected: 1050)")
        assert stats.raw_elo == 1050, f"Expected 1050, got {stats.raw_elo}"

if __name__ == "__main__":
    asyncio.run(test_concurrent_updates())
```

**Run**: `python test_phase_1.1_locking.py`

### Test 5: Migration Data Integrity

**Objective**: Verify existing challenges were migrated correctly

**Steps**:
```bash
sqlite3 tournament.db << EOF
-- Check migrated challenge participants
SELECT c.id, cp.player_id, cp.status, c.status as challenge_status
FROM challenges c
LEFT JOIN challenge_participants cp ON c.id = cp.challenge_id
WHERE c.challenger_id IS NOT NULL
LIMIT 5;

-- Count total migrated participants
SELECT COUNT(*) as participant_count
FROM challenge_participants;

-- Verify unique constraint works
-- This should fail if constraint is working
INSERT INTO challenge_participants (challenge_id, player_id, status)
SELECT challenge_id, player_id, status 
FROM challenge_participants 
LIMIT 1;
EOF
```

**Expected Results**:
- Each 1v1 challenge should have exactly 2 ChallengeParticipant records
- Participant status should match challenge status appropriately
- Duplicate insert should fail with unique constraint error

### Test 6: Meta-Game Fields Functionality

**Objective**: Test new PlayerEventStats fields work correctly

**Test Script**: Create `test_phase_1.1_metagame.py`:
```python
import asyncio
from bot.database.database import Database
from bot.database.models import Player, Event, Cluster, PlayerEventStats

async def test_metagame_fields():
    db = Database()
    await db.initialize()
    
    async with db.transaction() as session:
        # Get or create test data
        player = await db.get_or_create_player(700000, "MetaGamePlayer", session)
        
        cluster = Cluster(number=97, name="Meta Test")
        session.add(cluster)
        await session.flush()
        
        event = Event(name="Meta Event", cluster_id=cluster.id)
        session.add(event)
        await session.flush()
        
        # Test meta-game fields
        stats = await db.get_or_create_player_event_stats(player.id, event.id, session)
        
        # Update meta-game fields
        stats.final_score = 1500
        stats.shard_bonus = 100
        stats.shop_bonus = 50
        
        await session.commit()
        
        # Verify
        loaded_stats = await db.get_or_create_player_event_stats(player.id, event.id, session)
        print(f"✓ Meta-game fields saved correctly:")
        print(f"  - Final Score: {loaded_stats.final_score}")
        print(f"  - Shard Bonus: {loaded_stats.shard_bonus}")
        print(f"  - Shop Bonus: {loaded_stats.shop_bonus}")
        
        assert loaded_stats.final_score == 1500
        assert loaded_stats.shard_bonus == 100
        assert loaded_stats.shop_bonus == 50

if __name__ == "__main__":
    asyncio.run(test_metagame_fields())
```

**Run**: `python test_phase_1.1_metagame.py`

## Rollback Procedure

If any tests fail:

1. Check for the rollback script created by the migration:
   ```bash
   ls rollback_phase_1.1_model_updates_*.sh
   ```

2. Run the rollback script:
   ```bash
   ./rollback_phase_1.1_model_updates_[timestamp].sh
   ```

3. Verify rollback:
   ```bash
   sqlite3 tournament.db ".schema player_event_stats" | grep -E "final_score|shard_bonus|shop_bonus"
   # Should return nothing if rollback successful
   ```

## Success Criteria

All tests pass when:
1. ✅ Database schema updated correctly
2. ✅ ORM relationships function properly
3. ✅ ChallengeParticipant model creates records successfully
4. ✅ Row-level locking prevents race conditions
5. ✅ Existing challenges migrated with data integrity
6. ✅ Meta-game fields store and retrieve data correctly

## Notes

- The migration is designed to be idempotent - running it multiple times is safe
- All changes are additive, preserving existing data
- The Challenge model still supports legacy 1v1 fields for backward compatibility
- Future phases will complete the transition to fully use ChallengeParticipant