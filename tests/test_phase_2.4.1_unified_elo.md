# Phase 2.4.1 Unified Elo System Test Suite

## Overview

This test suite validates the Phase 2.4.1 unified Elo architecture implementation. The migration consolidates fragmented events per scoring type into unified events per base game, moving scoring_type from Event level to Match level.

## Test Environment Setup

```bash
# Ensure virtual environment is active
source venv/bin/activate

# Confirm the bot starts without errors
python -m bot.main

# Stop the bot after confirming startup (Ctrl+C)
```

## Test 1: Database Schema Validation

**Objective**: Verify migration successfully updated database schema.

**Steps**:
1. Check matches table has scoring_type column:
   ```bash
   sqlite3 tournament.db "PRAGMA table_info(matches);"
   ```
   
2. Check events table has supported_scoring_types column:
   ```bash
   sqlite3 tournament.db "PRAGMA table_info(events);"
   ```

**Expected Results**:
- ✅ matches table should have `scoring_type VARCHAR(20) DEFAULT '1v1'` column
- ✅ events table should have `supported_scoring_types VARCHAR(100)` column

## Test 2: Event Consolidation Verification

**Objective**: Verify events are properly consolidated (one per base game).

**Steps**:
1. Count active events per base game:
   ```bash
   sqlite3 tournament.db "
   SELECT base_event_name, COUNT(*) as active_count
   FROM events 
   WHERE is_active = 1 AND base_event_name IS NOT NULL
   GROUP BY base_event_name
   ORDER BY active_count DESC, base_event_name;
   "
   ```

2. Check for any duplicate active events:
   ```bash
   sqlite3 tournament.db "
   SELECT base_event_name, COUNT(*) as count
   FROM events 
   WHERE is_active = 1 AND base_event_name IS NOT NULL
   GROUP BY base_event_name
   HAVING COUNT(*) > 1;
   "
   ```

3. Verify deprecated events are marked correctly:
   ```bash
   sqlite3 tournament.db "
   SELECT COUNT(*) as deprecated_events
   FROM events 
   WHERE name LIKE '%[DEPRECATED-CONSOLIDATED]';
   "
   ```

**Expected Results**:
- ✅ Each base_event_name should have exactly 1 active event
- ✅ No duplicate active events should exist
- ✅ Should have 17 deprecated events with [DEPRECATED-CONSOLIDATED] suffix

## Test 3: Unified Event Names and Supported Types

**Objective**: Verify unified events have proper names and supported scoring types.

**Steps**:
1. Check Diep and Bonk events specifically:
   ```bash
   sqlite3 tournament.db "
   SELECT name, base_event_name, supported_scoring_types, is_active
   FROM events 
   WHERE base_event_name IN ('Diep', 'Bonk')
   ORDER BY name;
   "
   ```

2. Verify all active events have supported_scoring_types populated:
   ```bash
   sqlite3 tournament.db "
   SELECT COUNT(*) as missing_supported_types
   FROM events 
   WHERE is_active = 1 AND (supported_scoring_types IS NULL OR supported_scoring_types = '');
   "
   ```

**Expected Results**:
- ✅ "Diep" event should be active with supported_scoring_types = "1v1,FFA,Team"
- ✅ "Bonk" event should be active with supported_scoring_types = "1v1,FFA,Team"
- ✅ No active events should have missing supported_scoring_types

## Test 4: PlayerEventStats Consolidation

**Objective**: Verify PlayerEventStats are properly consolidated.

**Steps**:
1. Count total PlayerEventStats records:
   ```bash
   sqlite3 tournament.db "SELECT COUNT(*) as total_stats FROM player_event_stats;"
   ```

2. Check specific player stats for unified events:
   ```bash
   sqlite3 tournament.db "
   SELECT p.username, e.name, pes.scoring_elo, pes.matches_played
   FROM player_event_stats pes
   JOIN players p ON pes.player_id = p.id
   JOIN events e ON pes.event_id = e.id
   WHERE e.name IN ('Diep', 'Bonk')
   ORDER BY p.username, e.name;
   "
   ```

3. Verify no player has multiple stats for same unified event:
   ```bash
   sqlite3 tournament.db "
   SELECT player_id, event_id, COUNT(*) as duplicate_count
   FROM player_event_stats pes
   JOIN events e ON pes.event_id = e.id
   WHERE e.is_active = 1
   GROUP BY player_id, event_id
   HAVING COUNT(*) > 1;
   "
   ```

**Expected Results**:
- ✅ Should have ~1449 total PlayerEventStats records (reduced from 1636)
- ✅ Each player should have exactly one stats record per unified event
- ✅ No duplicate stats should exist for same player + event combination

## Test 5: Challenge Command with Unified Events

**Objective**: Test challenge command works with unified event selection.

**Steps**:
1. Start the bot:
   ```bash
   python -m bot.main
   ```

2. In Discord, test autocomplete:
   - Type `/challenge cluster:IO` (should autocomplete IO Games)
   - Select IO Games cluster
   - Type `/challenge cluster:1 event:Diep` (should show "Diep" not "Diep (1v1)")

3. Test event selection validation:
   - Try: `/challenge cluster:1 event:Diep match_type:1v1 players:@cam3llya`
   - Try: `/challenge cluster:1 event:Diep match_type:ffa players:@cam3llya @joey123tribbiani @gayfucking`

4. Check database for created challenges:
   ```bash
   sqlite3 tournament.db "
   SELECT c.id, e.name, e.supported_scoring_types
   FROM challenges c
   JOIN events e ON c.event_id = e.id
   ORDER BY c.id DESC LIMIT 2;
   "
   ```

**Expected Results**:
- ✅ Event autocomplete should show "Diep" (not "Diep (1v1)")
- ✅ Challenge creation should succeed for unified events
- ✅ Challenges should reference unified event IDs

## Test 6: Population Script Creates Unified Events

**Objective**: Test updated populate_from_csv.py creates unified events.

**Steps**:
1. Create a backup of current database:
   ```bash
   cp tournament.db tournament_test_backup.db
   ```

2. Clear current events and run population:
   ```bash
   sqlite3 tournament.db "
   DELETE FROM player_event_stats;
   DELETE FROM events;
   DELETE FROM clusters;
   "
   ```

3. Run population script:
   ```bash
   python populate_from_csv.py
   ```

4. Verify unified events created:
   ```bash
   sqlite3 tournament.db "
   SELECT COUNT(DISTINCT base_event_name) as unique_base_games,
          COUNT(*) as total_events
   FROM events WHERE is_active = 1;
   "
   ```

5. Check specific event structure:
   ```bash
   sqlite3 tournament.db "
   SELECT name, base_event_name, supported_scoring_types
   FROM events 
   WHERE base_event_name = 'Diep';
   "
   ```

6. Restore original database:
   ```bash
   mv tournament_test_backup.db tournament.db
   ```

**Expected Results**:
- ✅ Should create ~69 unique base games as single events (not 86 fragmented ones)
- ✅ Each event should have unified name (e.g., "Diep" not "Diep (1v1)")
- ✅ Each event should have supported_scoring_types populated correctly

## Test 7: Match Creation with Scoring Types

**Objective**: Verify matches can be created with proper scoring_type field.

**Note**: This test requires completing the match creation workflow, which may involve additional Phase 2.4 work.

**Steps**:
1. Create a test challenge (from Test 5)
2. Accept the challenge (requires `/accept` command from Phase 2.4.2)
3. Complete the match workflow
4. Verify match has scoring_type field populated:
   ```bash
   sqlite3 tournament.db "
   SELECT m.id, m.event_id, m.scoring_type, e.name
   FROM matches m
   JOIN events e ON m.event_id = e.id
   ORDER BY m.id DESC LIMIT 1;
   "
   ```

**Expected Results**:
- ✅ Match record should have scoring_type = "1v1", "FFA", or "Team"
- ✅ Match should reference unified event (not fragmented event)

## Test 8: Legacy Data Preservation

**Objective**: Verify migration preserved all historical data.

**Steps**:
1. Check legacy backup tables exist:
   ```bash
   sqlite3 tournament.db ".tables" | grep legacy
   ```

2. Compare data counts in legacy vs current:
   ```bash
   sqlite3 tournament.db "
   SELECT 
       (SELECT COUNT(*) FROM events_legacy_2_4_1) as legacy_events,
       (SELECT COUNT(*) FROM events) as current_events,
       (SELECT COUNT(*) FROM player_event_stats_legacy_2_4_1) as legacy_stats,
       (SELECT COUNT(*) FROM player_event_stats) as current_stats;
   "
   ```

3. Verify rollback script exists:
   ```bash
   ls -la rollback_phase_2_4_1_*.sh
   ```

**Expected Results**:
- ✅ Legacy backup tables should exist with original data
- ✅ Current tables should have consolidated data (fewer records)
- ✅ Rollback script should be executable

## Test 9: Bot Startup and Model Loading

**Objective**: Verify bot starts successfully with updated models.

**Steps**:
1. Check for any SQLAlchemy model errors:
   ```bash
   python -c "
   import asyncio
   from bot.database.database import Database
   from bot.database.models import Event, Match, PlayerEventStats
   
   async def test_models():
       db = Database()
       await db.initialize()
       
       # Test Event model access
       async with db.transaction() as session:
           events = await db.get_all_events(active_only=True)
           print(f'✅ Loaded {len(events)} events')
           
           # Check for events with supported_scoring_types
           events_with_types = [e for e in events if e.supported_scoring_types]
           print(f'✅ {len(events_with_types)} events have supported_scoring_types')
       
       await db.close()
       print('✅ Model loading test passed')
   
   asyncio.run(test_models())
   "
   ```

2. Start bot and check logs for errors:
   ```bash
   timeout 10 python -m bot.main 2>&1 | grep -E "(ERROR|Exception|Traceback)"
   ```

**Expected Results**:
- ✅ Models should load without SQLAlchemy errors
- ✅ Bot should start without database-related errors
- ✅ Events should have supported_scoring_types accessible

## Test 10: End-to-End Unified Elo Workflow

**Objective**: Test complete workflow from event selection to match creation.

**Steps**:
1. Start bot and create challenge:
   ```
   /challenge cluster:IO_Games event:Diep match_type:1v1 players:@testuser
   ```

2. Verify in database:
   ```bash
   sqlite3 tournament.db "
   SELECT c.id, e.name, e.base_event_name, e.supported_scoring_types
   FROM challenges c
   JOIN events e ON c.event_id = e.id
   WHERE c.id = (SELECT MAX(id) FROM challenges);
   "
   ```

3. Check that challenge uses unified event:
   ```bash
   sqlite3 tournament.db "
   SELECT 
       c.id as challenge_id,
       e.name as event_name,
       CASE WHEN e.name = e.base_event_name THEN 'UNIFIED' ELSE 'FRAGMENTED' END as event_type
   FROM challenges c
   JOIN events e ON c.event_id = e.id
   WHERE c.id = (SELECT MAX(id) FROM challenges);
   "
   ```

**Expected Results**:
- ✅ Challenge should be created successfully
- ✅ Challenge should reference unified event (name = base_event_name)
- ✅ Event should have proper supported_scoring_types

## Summary Checklist

After completing all tests, verify:

- [ ] **Database Migration**: All schema changes applied correctly
- [ ] **Event Consolidation**: One active event per base game
- [ ] **PlayerEventStats**: Properly consolidated, no duplicates
- [ ] **Challenge Command**: Works with unified event selection
- [ ] **Population Script**: Creates unified events going forward
- [ ] **Model Loading**: No SQLAlchemy errors with new fields
- [ ] **Data Preservation**: Legacy data safely backed up
- [ ] **Rollback Capability**: Emergency rollback script available
- [ ] **Bot Functionality**: Core functionality preserved
- [ ] **End-to-End**: Complete unified Elo workflow functional

## Expected Final State

After successful Phase 2.4.1 implementation:

- **Events**: ~69 unified events (down from 86 fragmented)
- **PlayerEventStats**: ~1449 consolidated records (down from 1636)
- **Architecture**: Unified Elo per base game achieved
- **Challenge Flow**: Base game → Match type → Unified event selection
- **Match Creation**: Scoring type stored at match level
- **User Experience**: Events show as "Diep" not "Diep (1v1)"

## Troubleshooting

**If tests fail**:

1. **Schema Issues**: Run migration script again (idempotent)
2. **Data Corruption**: Use rollback script and investigate
3. **Model Errors**: Check SQLAlchemy column definitions
4. **Bot Startup**: Check logs for import/initialization errors
5. **Challenge Creation**: Verify event resolution logic in challenge.py

**Emergency Rollback**:
```bash
./rollback_phase_2_4_1_[timestamp].sh
```

## Notes for Manual Testing

1. Use actual Discord users for challenge testing
2. Test with various match types (1v1, FFA, Team)
3. Verify autocomplete behavior in Discord client
4. Check that error messages are user-friendly
5. Confirm no performance regression in event loading