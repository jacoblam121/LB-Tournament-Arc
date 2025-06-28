# Phase 1.1 Database Architecture Manual Test Suite

## Overview
This test suite validates the Phase 1.1 implementation of per-event Elo tracking and meta-game foundation. These tests are designed to be run manually after the migration has been completed.

**Note**: The Phase 1.1 migration has already been executed successfully. These tests verify the current working state.

---

## Test Execution Instructions

Run each test by copying and pasting the Python code blocks into your terminal. Each test is self-contained and will show PASS/FAIL results.

---

## Test 1: Database Schema Verification
**Objective**: Verify all new tables and columns exist

```bash
python -c "
import asyncio
from bot.database.database import Database
from sqlalchemy import text

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        print('=== Database Schema Verification ===')
        
        # Check new tables exist
        tables = await session.execute(text(\"\"\"
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN (
                'player_event_stats', 'ticket_ledger', 'player_event_personal_bests',
                'weekly_scores', 'player_weekly_leaderboard_elo'
            )
        \"\"\"))
        
        table_names = [row[0] for row in tables.fetchall()]
        print(f'New tables found: {len(table_names)}/5')
        for table in table_names:
            print(f'  ✅ {table}')
        
        expected_tables = [
            'player_event_stats', 'ticket_ledger', 'player_event_personal_bests',
            'weekly_scores', 'player_weekly_leaderboard_elo'
        ]
        
        missing_tables = [t for t in expected_tables if t not in table_names]
        if missing_tables:
            print(f'❌ Missing tables: {missing_tables}')
            return False
            
        # Check Player model updates
        player_columns = await session.execute(text(\"PRAGMA table_info(players)\"))
        column_names = [row[1] for row in player_columns.fetchall()]
        
        expected_new_columns = ['active_leverage_token', 'current_streak', 'max_streak']
        print(f'\\nPlayer table new columns:')
        for col in expected_new_columns:
            if col in column_names:
                print(f'  ✅ {col}')
            else:
                print(f'  ❌ {col} - MISSING')
                return False
                
        # Check EloHistory model updates  
        elo_columns = await session.execute(text(\"PRAGMA table_info(elo_history)\"))
        elo_column_names = [row[1] for row in elo_columns.fetchall()]
        if 'event_id' in elo_column_names:
            print(f'  ✅ elo_history.event_id')
        else:
            print(f'  ❌ elo_history.event_id - MISSING')
            return False
            
        print('\\n✅ TEST 1: Database Schema Verification - PASS')
        return True

result = asyncio.run(test())
if not result:
    print('\\n❌ TEST 1: Database Schema Verification - FAIL')
"
```

---

## Test 2: Data Integrity Verification
**Objective**: Verify migration preserved and reset data correctly

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import Player, PlayerEventStats, TicketLedger, Event
        from sqlalchemy import select, func
        
        print('=== Data Integrity Verification ===')
        
        # Verify player data reset
        players_with_default_elo = await session.scalar(
            select(func.count(Player.id)).where(Player.elo_rating == 1000)
        )
        total_players = await session.scalar(select(func.count(Player.id)))
        
        print(f'Players with 1000 Elo: {players_with_default_elo}/{total_players}')
        if players_with_default_elo != total_players:
            print('❌ Not all players reset to 1000 Elo')
            return False
        else:
            print('✅ All players have default 1000 Elo')
        
        # Verify PlayerEventStats initialization
        stats_count = await session.scalar(select(func.count(PlayerEventStats.id)))
        event_count = await session.scalar(select(func.count(Event.id)))
        expected_stats = total_players * event_count
        
        print(f'\\nPlayerEventStats: {stats_count} (expected: {expected_stats})')
        if stats_count != expected_stats:
            print(f'❌ Expected {expected_stats} stats, got {stats_count}')
            return False
        else:
            print('✅ PlayerEventStats correctly initialized for all player/event combinations')
        
        # Verify TicketLedger initialization
        ledger_count = await session.scalar(select(func.count(TicketLedger.id)))
        print(f'\\nTicketLedger entries: {ledger_count}')
        if ledger_count != total_players:
            print(f'❌ Expected {total_players} ledger entries, got {ledger_count}')
            return False
        else:
            print('✅ TicketLedger correctly initialized for all players')
        
        print('\\n✅ TEST 2: Data Integrity Verification - PASS')
        return True

result = asyncio.run(test())
if not result:
    print('\\n❌ TEST 2: Data Integrity Verification - FAIL')
"
```

---

## Test 3: Dual-Track Elo System
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
        
        print('=== Dual-Track Elo System Test ===')
        
        # Test dual-track enforcement via SQLAlchemy event listener
        # Use high IDs to avoid migration data conflicts
        stats = PlayerEventStats(
            player_id=9999,  # Non-existent player to avoid unique constraint
            event_id=9999,   # Non-existent event to avoid unique constraint  
            raw_elo=750,     # Below 1000
            scoring_elo=750  # Will be auto-corrected
        )
        
        session.add(stats)
        await session.flush()
        
        # Check that scoring_elo was automatically corrected to 1000
        print(f'Raw Elo: {stats.raw_elo}')
        print(f'Scoring Elo: {stats.scoring_elo}')
        
        if stats.raw_elo != 750:
            print('❌ Raw Elo should remain 750')
            return False
        
        if stats.scoring_elo != 1000:
            print('❌ Scoring Elo should be floored at 1000')
            return False
            
        print('✅ Raw Elo preserved at 750')
        print('✅ Scoring Elo automatically floored to 1000')
        
        # Test with Elo above 1000 (should remain unchanged)
        stats2 = PlayerEventStats(
            player_id=9998,
            event_id=9998,
            raw_elo=1200,
            scoring_elo=1200
        )
        
        session.add(stats2)
        await session.flush()
        
        print(f'\\nHigh Elo Test:')
        print(f'Raw Elo: {stats2.raw_elo}')
        print(f'Scoring Elo: {stats2.scoring_elo}')
        
        if stats2.raw_elo != 1200 or stats2.scoring_elo != 1200:
            print('❌ High Elo values should remain unchanged')
            return False
            
        print('✅ High Elo values preserved correctly')
        
        print('\\n✅ TEST 3: Dual-Track Elo System - PASS')
        return True

result = asyncio.run(test())
if not result:
    print('\\n❌ TEST 3: Dual-Track Elo System - FAIL')
"
```

---

## Test 4: Model Relationships
**Objective**: Test model relationships work correctly

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import Player, Event
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        
        print('=== Model Relationships Test ===')
        
        # Test Player -> PlayerEventStats relationship
        player = await session.execute(
            select(Player).options(
                selectinload(Player.event_stats)
            ).limit(1)
        )
        player = player.scalar_one_or_none()
        
        if not player:
            print('❌ No players found to test relationships')
            return False
            
        event_stats_count = len(player.event_stats)
        print(f'Player {player.id} ({player.username}) has {event_stats_count} event stats')
        
        if event_stats_count == 0:
            print('❌ Player should have event stats')
            return False
        else:
            print('✅ Player has event stats records')
            
        # Test reverse relationship
        first_stat = player.event_stats[0]
        if first_stat.player.id != player.id:
            print('❌ Reverse relationship broken')
            return False
        else:
            print('✅ Reverse relationship (PlayerEventStats -> Player) working')
            
        # Test Event -> PlayerEventStats relationship
        event = await session.execute(
            select(Event).options(
                selectinload(Event.player_stats)
            ).limit(1)
        )
        event = event.scalar_one_or_none()
        
        if event:
            player_stats_count = len(event.player_stats)
            print(f'\\nEvent {event.id} ({event.name}) has {player_stats_count} player stats')
            
            if player_stats_count == 0:
                print('❌ Event should have player stats')
                return False
            else:
                print('✅ Event has player stats records')
        
        print('\\n✅ TEST 4: Model Relationships - PASS')
        return True

result = asyncio.run(test())
if not result:
    print('\\n❌ TEST 4: Model Relationships - FAIL')
"
```

---

## Test 5: Event Leaderboard Generation
**Objective**: Test per-event leaderboard functionality

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import PlayerEventStats, Player, Event
        from sqlalchemy import select, desc
        
        print('=== Event Leaderboard Test ===')
        
        # Get a sample event
        event = await session.execute(select(Event).limit(1))
        event = event.scalar_one_or_none()
        
        if not event:
            print('❌ No events found for leaderboard test')
            return False
            
        print(f'Testing leaderboard for Event {event.id}: {event.name}')
        
        # Get leaderboard for this event
        leaderboard_query = select(PlayerEventStats).join(Player).where(
            PlayerEventStats.event_id == event.id
        ).order_by(desc(PlayerEventStats.scoring_elo)).limit(5)
        
        leaderboard = await session.execute(leaderboard_query)
        leaderboard_entries = leaderboard.scalars().all()
        
        print(f'\\nTop 5 players for this event:')
        for i, stats in enumerate(leaderboard_entries[:5]):
            print(f'{i+1}. Player {stats.player_id}: {stats.scoring_elo} Elo (Raw: {stats.raw_elo})')
            
            # After migration, all should have 1000 Elo
            if stats.scoring_elo != 1000:
                print(f'❌ Expected 1000 Elo, got {stats.scoring_elo}')
                return False
        
        if len(leaderboard_entries) == 0:
            print('❌ No leaderboard entries found')
            return False
        else:
            print(f'✅ Leaderboard generated with {len(leaderboard_entries)} entries')
            print('✅ All players correctly show 1000 Elo post-migration')
        
        print('\\n✅ TEST 5: Event Leaderboard Generation - PASS')
        return True

result = asyncio.run(test())
if not result:
    print('\\n❌ TEST 5: Event Leaderboard Generation - FAIL')
"
```

---

## Test 6: Ticket Ledger Verification
**Objective**: Verify ticket ledger was properly initialized

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import TicketLedger, Player
        from sqlalchemy import select
        
        print('=== Ticket Ledger Verification ===')
        
        # Get a sample player and their ticket history
        player = await session.execute(select(Player).limit(1))
        player = player.scalar_one_or_none()
        
        if not player:
            print('❌ No players found for ticket test')
            return False
            
        print(f'Testing tickets for Player {player.id}: {player.username}')
        print(f'Player current ticket balance: {player.tickets}')
        
        # Get ticket ledger entries for this player
        ledger_query = select(TicketLedger).where(
            TicketLedger.player_id == player.id
        ).order_by(TicketLedger.timestamp)
        
        ledger_entries = await session.execute(ledger_query)
        entries = ledger_entries.scalars().all()
        
        print(f'\\nTicket ledger entries for this player: {len(entries)}')
        
        if len(entries) == 0:
            print('❌ Player should have at least one ledger entry (migration reset)')
            return False
            
        # Check migration reset entry
        reset_entry = entries[0]
        print(f'First entry: {reset_entry.change_amount} tickets, reason: {reset_entry.reason}')
        print(f'Balance after: {reset_entry.balance_after}')
        
        if reset_entry.reason != 'MIGRATION_RESET':
            print('❌ First entry should be MIGRATION_RESET')
            return False
            
        if reset_entry.change_amount != 0:
            print('❌ Migration reset should be 0 tickets')
            return False
            
        if reset_entry.balance_after != 0:
            print('❌ Post-migration balance should be 0')
            return False
            
        print('✅ Migration reset entry found with correct values')
        print('✅ Ticket ledger properly initialized')
        
        print('\\n✅ TEST 6: Ticket Ledger Verification - PASS')
        return True

result = asyncio.run(test())
if not result:
    print('\\n❌ TEST 6: Ticket Ledger Verification - FAIL')
"
```

---

## Test 7: Data Consistency Check
**Objective**: Verify overall data consistency across all Phase 1.1 components

```bash
python -c "
import asyncio
from bot.database.database import Database

async def test():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        from bot.database.models import Player, Event, PlayerEventStats, TicketLedger
        from sqlalchemy import select, func
        
        print('=== Data Consistency Check ===')
        
        # Get counts
        player_count = await session.scalar(select(func.count(Player.id)))
        event_count = await session.scalar(select(func.count(Event.id)))
        stats_count = await session.scalar(select(func.count(PlayerEventStats.id)))
        ledger_count = await session.scalar(select(func.count(TicketLedger.id)))
        
        print(f'Database Overview:')
        print(f'  Players: {player_count}')
        print(f'  Events: {event_count}')
        print(f'  PlayerEventStats: {stats_count}')
        print(f'  TicketLedger entries: {ledger_count}')
        
        # Verify mathematical consistency
        expected_stats = player_count * event_count
        print(f'\\nConsistency Checks:')
        print(f'  Expected PlayerEventStats: {expected_stats}')
        print(f'  Actual PlayerEventStats: {stats_count}')
        
        if stats_count != expected_stats:
            print('❌ PlayerEventStats count inconsistent')
            return False
        else:
            print('✅ PlayerEventStats count matches expectation')
            
        if ledger_count != player_count:
            print('❌ TicketLedger entries should equal player count')
            return False
        else:
            print('✅ TicketLedger entries match player count')
            
        # Check that all players have the same number of event stats
        stats_per_player = await session.execute(
            select(PlayerEventStats.player_id, func.count(PlayerEventStats.id)).
            group_by(PlayerEventStats.player_id)
        )
        
        stats_counts = [(row[0], row[1]) for row in stats_per_player.fetchall()]
        
        if not all(count == event_count for _, count in stats_counts):
            print('❌ Not all players have stats for all events')
            return False
        else:
            print(f'✅ All players have stats for all {event_count} events')
            
        print('\\n✅ TEST 7: Data Consistency Check - PASS')
        return True

result = asyncio.run(test())
if not result:
    print('\\n❌ TEST 7: Data Consistency Check - FAIL')
"
```

---

## Test Results Template

Copy and fill out this template with your test results:

```
## Phase 1.1 Manual Test Results

**Test Date**: [DATE]
**Environment**: Python 3.12, SQLite

### Test Results
- [ ] Test 1: Database Schema Verification - PASS/FAIL
- [ ] Test 2: Data Integrity Verification - PASS/FAIL  
- [ ] Test 3: Dual-Track Elo System - PASS/FAIL
- [ ] Test 4: Model Relationships - PASS/FAIL
- [ ] Test 5: Event Leaderboard Generation - PASS/FAIL
- [ ] Test 6: Ticket Ledger Verification - PASS/FAIL
- [ ] Test 7: Data Consistency Check - PASS/FAIL

### Issues Found:
1. 
2. 
3. 

### Overall Assessment:
READY FOR NEXT PHASE / NEEDS FIXES / CRITICAL ISSUES

### Notes:
[Any additional observations or comments]
```

---

## Expected Results

If Phase 1.1 is working correctly, you should see:

✅ **All 7 tests should PASS**
- 5 new tables created successfully
- 1,628 PlayerEventStats records (11 players × 148 events)
- 11 TicketLedger entries with migration reset
- Dual-track Elo system enforcing 1000 minimum for scoring_elo
- All model relationships working bidirectionally
- Data consistency across all components

The tests are designed to be comprehensive yet easy to run manually. Each test provides detailed output to help you understand what's being verified.