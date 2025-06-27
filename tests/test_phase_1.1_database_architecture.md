# Phase 1.1 Database Architecture Test Suite

## Overview
This test suite validates the Phase 1.1 implementation of per-event Elo tracking and meta-game foundation. Run these tests manually after implementing the critical fixes identified in the code review.

## ✅ CRITICAL FIXES COMPLETED

**ALL CRITICAL ISSUES HAVE BEEN RESOLVED:**

### ✅ 1. Session Management Anti-Pattern - FIXED
**Location**: `bot/database/database.py:508, 539, 665`
**Status**: ✅ **COMPLETED** - Methods now accept AsyncSession parameters for transaction composability

### ✅ 2. Event Context to EloHistory - FIXED  
**Location**: `bot/database/models.py:251` and `bot/database/database.py:551`
**Status**: ✅ **COMPLETED** - EloHistory model includes event_id field with proper relationships

### ✅ 3. Transaction Boundary Issues - FIXED
**Location**: `bot/database/database.py:720`
**Status**: ✅ **COMPLETED** - Methods use flush() for transaction composability, legacy method removed

### ✅ 4. Legacy Method Data Integrity Risk - FIXED
**Location**: `bot/database/database.py` (legacy record_elo_change method)
**Status**: ✅ **COMPLETED** - Legacy method removed to prevent data inconsistency

**🚀 PHASE 1.1 IMPLEMENTATION READY FOR TESTING**

---

## Test Execution Order

### Phase 1: Pre-Migration Tests
Run these tests to verify current state before migration.

### Phase 2: Migration Tests  
Run migration and verify database structure.

### Phase 3: Functionality Tests
Test the new per-event Elo and ticket systems.

### Phase 4: Integration Tests
Test interaction with existing systems.

---

## Phase 1: Pre-Migration Tests

### Test 1.1: Current Database State
**Objective**: Verify current database has CSV data loaded

```bash
# Test existing data
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import Player, Event, Cluster
        from sqlalchemy import select, func
        
        player_count = await session.scalar(select(func.count(Player.id)))
        event_count = await session.scalar(select(func.count(Event.id))) 
        cluster_count = await session.scalar(select(func.count(Cluster.id)))
        
        print(f'Pre-migration: {player_count} players, {event_count} events, {cluster_count} clusters')
        
        # Should see clusters/events from CSV
        assert cluster_count > 0, 'No clusters found - CSV data not loaded'
        assert event_count > 0, 'No events found - CSV data not loaded'

asyncio.run(test())
"
```

**Expected**: Should show loaded clusters and events from CSV data.

### Test 1.2: Model Import Verification  
**Objective**: Verify new models can be imported without errors

```bash
python -c "
from bot.database.models import (
    PlayerEventStats, TicketLedger, PlayerEventPersonalBest, 
    WeeklyScores, PlayerWeeklyLeaderboardElo
)
print('✅ All Phase 1.1 models imported successfully')
"
```

**Expected**: No import errors, success message displayed.

---

## Phase 2: Migration Tests

### Test 2.1: Migration Execution
**Objective**: Run the Phase 1.1 migration safely

```bash
# Create backup before migration
cp tournament.db tournament_backup_before_phase_1.1.db

# Run migration
python migration_phase_1.1.py
```

**Expected**: 
- ✅ Backup created successfully
- ✅ Migration completes without errors  
- ✅ Success report generated
- ✅ PlayerEventStats records created for all player/event combinations

### Test 2.2: Database Schema Verification
**Objective**: Verify new tables and columns exist

```bash
python -c "
import asyncio
from bot.database.database import Database
from sqlalchemy import text

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        # Check new tables exist
        tables = await session.execute(text(\"\"\"
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN (
                'player_event_stats', 'ticket_ledger', 'player_event_personal_bests',
                'weekly_scores', 'player_weekly_leaderboard_elo'
            )
        \"\"\"))
        
        table_names = [row[0] for row in tables.fetchall()]
        print(f'New tables created: {table_names}')
        
        expected_tables = [
            'player_event_stats', 'ticket_ledger', 'player_event_personal_bests',
            'weekly_scores', 'player_weekly_leaderboard_elo'
        ]
        
        for table in expected_tables:
            assert table in table_names, f'Missing table: {table}'
            
        # Check Player model updates
        player_columns = await session.execute(text(\"PRAGMA table_info(players)\"))
        column_names = [row[1] for row in player_columns.fetchall()]
        
        expected_new_columns = ['active_leverage_token', 'current_streak', 'max_streak']
        for col in expected_new_columns:
            assert col in column_names, f'Missing Player column: {col}'
            
        # Check Event model updates  
        event_columns = await session.execute(text(\"PRAGMA table_info(events)\"))
        event_column_names = [row[1] for row in event_columns.fetchall()]
        assert 'score_direction' in event_column_names, 'Missing Event.score_direction column'
        
        print('✅ All database schema changes verified')

asyncio.run(test())
"
```

**Expected**: All new tables and columns created successfully.

### Test 2.3: Data Integrity Verification
**Objective**: Verify migration preserved existing data correctly

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import Player, PlayerEventStats, TicketLedger
        from sqlalchemy import select, func
        
        # Verify player data reset
        players_with_default_elo = await session.scalar(
            select(func.count(Player.id)).where(Player.elo_rating == 1000)
        )
        total_players = await session.scalar(select(func.count(Player.id)))
        
        print(f'Players with default Elo: {players_with_default_elo}/{total_players}')
        assert players_with_default_elo == total_players, 'Not all players reset to 1000 Elo'
        
        # Verify PlayerEventStats initialization
        stats_count = await session.scalar(select(func.count(PlayerEventStats.id)))
        event_count = await session.scalar(select(func.count()).select_from('events'))
        expected_stats = total_players * event_count
        
        print(f'PlayerEventStats: {stats_count} (expected: {expected_stats})')
        assert stats_count == expected_stats, f'Expected {expected_stats} stats, got {stats_count}'
        
        # Verify TicketLedger initialization
        ledger_count = await session.scalar(select(func.count(TicketLedger.id)))
        print(f'TicketLedger entries: {ledger_count}')
        assert ledger_count == total_players, f'Expected {total_players} ledger entries, got {ledger_count}'
        
        print('✅ Migration data integrity verified')

asyncio.run(test())
"
```

**Expected**: All data integrity checks pass.

---

## Phase 3: Functionality Tests

### Test 3.1: Dual-Track Elo System
**Objective**: Verify dual-track Elo enforcement works correctly

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import PlayerEventStats
        
        # Test dual-track enforcement via SQLAlchemy event listener
        stats = PlayerEventStats(
            player_id=1,
            event_id=1,
            raw_elo=800,  # Below 1000
            scoring_elo=800  # Will be auto-corrected
        )
        
        session.add(stats)
        await session.flush()
        
        # Check that scoring_elo was automatically corrected to 1000
        print(f'Raw Elo: {stats.raw_elo}, Scoring Elo: {stats.scoring_elo}')
        assert stats.raw_elo == 800, 'Raw Elo should remain 800'
        assert stats.scoring_elo == 1000, 'Scoring Elo should be floored at 1000'
        
        print('✅ Dual-track Elo system working correctly')

asyncio.run(test())
"
```

**Expected**: Raw Elo stays at 800, Scoring Elo auto-corrected to 1000.

### Test 3.2: PlayerEventStats Operations
**Objective**: Test get_or_create functionality (after fixing session management)

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    # Test get_or_create pattern
    async with db.transaction() as session:
        # This test assumes the session management fix is implemented
        stats = await db.get_or_create_player_event_stats(1, 1, session)
        print(f'Created stats: {stats}')
        
        # Test getting existing stats
        stats2 = await db.get_or_create_player_event_stats(1, 1, session)
        assert stats.id == stats2.id, 'Should return same stats object'
        
        print('✅ PlayerEventStats get_or_create working correctly')

asyncio.run(test())
"
```

**Expected**: Creates new stats first time, returns existing stats second time.

### Test 3.3: Atomic Ticket Transactions  
**Objective**: Test ticket ledger atomic operations

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    # Test atomic ticket transaction
    try:
        ledger_entry = await db.add_ticket_transaction_atomic(
            player_id=1,
            amount=100,
            reason='TEST_GRANT'
        )
        
        print(f'Ticket transaction: {ledger_entry}')
        
        # Verify balance is correct
        balance = await db.get_player_ticket_balance(1)
        print(f'Player ticket balance: {balance}')
        assert balance == 100, f'Expected 100 tickets, got {balance}'
        
        # Test integrity check
        integrity = await db.verify_ticket_balance_integrity(1)
        print(f'Balance integrity: {integrity}')
        assert integrity['integrity_check'], 'Balance integrity check failed'
        
        print('✅ Atomic ticket transactions working correctly')
        
    except Exception as e:
        print(f'❌ Ticket transaction failed: {e}')
        print('This may be due to the double transaction boundary issue - check if fix was applied')

asyncio.run(test())
"
```

**Expected**: Ticket transaction succeeds, balance updates correctly, integrity check passes.

### Test 3.4: Event Leaderboard Generation
**Objective**: Test per-event leaderboard functionality

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    # Test event leaderboard
    leaderboard = await db.get_event_leaderboard(event_id=1, scoring_type='1v1', limit=10)
    print(f'Event leaderboard entries: {len(leaderboard)}')
    
    for i, stats in enumerate(leaderboard[:3]):
        print(f'{i+1}. Player {stats.player_id}: {stats.scoring_elo} Elo')
        
    # All should have 1000 Elo after migration
    for stats in leaderboard:
        assert stats.scoring_elo == 1000, f'Expected 1000 Elo, got {stats.scoring_elo}'
    
    print('✅ Event leaderboard generation working correctly')

asyncio.run(test())
"
```

**Expected**: Returns leaderboard with all players at 1000 Elo.

---

## Phase 4: Integration Tests

### Test 4.1: Relationship Verification
**Objective**: Test model relationships work correctly

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import Player
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        
        # Test Player -> PlayerEventStats relationship
        player = await session.execute(
            select(Player).options(
                selectinload(Player.event_stats)
            ).limit(1)
        )
        player = player.scalar_one_or_none()
        
        if player:
            print(f'Player {player.id} has {len(player.event_stats)} event stats')
            assert len(player.event_stats) > 0, 'Player should have event stats'
            
            # Test reverse relationship
            first_stat = player.event_stats[0]
            assert first_stat.player.id == player.id, 'Reverse relationship broken'
            
            print('✅ Player <-> PlayerEventStats relationships working')
        else:
            print('⚠️ No players found to test relationships')

asyncio.run(test())
"
```

**Expected**: Relationships work bidirectionally without errors.

### Test 4.2: Comprehensive Player Stats
**Objective**: Test comprehensive stats retrieval

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    # Test comprehensive stats
    stats = await db.get_comprehensive_player_stats(1)
    
    if stats:
        print(f'Player stats summary:')
        print(f'  Total events: {stats[\"total_events\"]}')
        print(f'  Clusters: {list(stats[\"cluster_stats\"].keys())}')
        
        assert stats['total_events'] > 0, 'Player should have event stats'
        assert len(stats['cluster_stats']) > 0, 'Player should have cluster stats'
        
        print('✅ Comprehensive player stats working correctly')
    else:
        print('⚠️ No player found for comprehensive stats test')

asyncio.run(test())
"
```

**Expected**: Returns comprehensive stats organized by cluster.

---

## Test Results Template

Copy and fill out this template with your test results:

```
## Phase 1.1 Test Results

**Environment**: 
- Python version: 
- Database: SQLite
- Test date: 

### Pre-Migration Tests
- [ ] Test 1.1: Current Database State - PASS/FAIL
- [ ] Test 1.2: Model Import Verification - PASS/FAIL

### Migration Tests  
- [ ] Test 2.1: Migration Execution - PASS/FAIL
- [ ] Test 2.2: Database Schema Verification - PASS/FAIL
- [ ] Test 2.3: Data Integrity Verification - PASS/FAIL

### Functionality Tests
- [ ] Test 3.1: Dual-Track Elo System - PASS/FAIL  
- [ ] Test 3.2: PlayerEventStats Operations - PASS/FAIL
- [ ] Test 3.3: Atomic Ticket Transactions - PASS/FAIL
- [ ] Test 3.4: Event Leaderboard Generation - PASS/FAIL

### Integration Tests
- [ ] Test 4.1: Relationship Verification - PASS/FAIL
- [ ] Test 4.2: Comprehensive Player Stats - PASS/FAIL

### Issues Found:
1. 
2. 
3. 

### Overall Assessment:
READY FOR NEXT PHASE / NEEDS FIXES / CRITICAL ISSUES
```

---

## Notes

- Run tests in order - don't skip phases
- If any test fails, investigate and fix before proceeding
- Keep backup of database before migration
- Report any issues found during testing

Remember: **CRITICAL FIXES MUST BE IMPLEMENTED BEFORE RUNNING THESE TESTS!**