# Phase 2.4.1: Unified Elo Architecture - Test Suite

## Overview
This test suite validates the unified Elo architecture implementation, which consolidates fragmented events (e.g., "Diep (1v1)", "Diep (Team)", "Diep (FFA)") into unified events with a single Elo rating per base game.

## Prerequisites
1. Ensure database backup exists before testing
2. Run the migration script: `python migration_phase_2_4_1_unified_elo.py`
3. Run the population script: `python populate_from_csv.py`
4. Start the bot: `python -m bot.main`

## Test 1: Database Schema Validation
**Objective**: Verify new columns exist in the database

### Steps:
```bash
sqlite3 tournament.db
```

### Execute:
```sql
-- Check matches table has scoring_type column
PRAGMA table_info(matches);

-- Check events table has supported_scoring_types column
PRAGMA table_info(events);
```

### Expected Results:
- `matches` table should have `scoring_type` column (VARCHAR(20), default '1v1')
- `events` table should have `supported_scoring_types` column (VARCHAR(100))

### Actual Results:
- [ ] Matches table has scoring_type column
- [ ] Events table has supported_scoring_types column

---

## Test 2: Event Consolidation Verification
**Objective**: Verify events are properly unified

### Execute:
```sql
-- Check total event count
SELECT COUNT(*) FROM events WHERE is_active = 1;

-- Check for unified events with multiple scoring types
SELECT name, supported_scoring_types 
FROM events 
WHERE supported_scoring_types LIKE '%,%' 
ORDER BY name 
LIMIT 10;

-- Verify no fragmented events exist
SELECT name FROM events 
WHERE name LIKE '% (1v1)' 
   OR name LIKE '% (Team)' 
   OR name LIKE '% (FFA)' 
   OR name LIKE '% (Leaderboard)';

-- Check specific unified events
SELECT name, supported_scoring_types 
FROM events 
WHERE name IN ('Diep', 'Bonk', 'Krunker') 
ORDER BY name;
```

### Expected Results:
- Total events: ~70 (reduced from 86)
- Multiple events should show comma-separated scoring types
- NO events with suffixes like "(1v1)", "(Team)", "(FFA)"
- Diep: "1v1,FFA,Team"
- Bonk: "1v1,FFA,Team"
- Krunker: "1v1,FFA"

### Actual Results:
- [ ] Total active events: _____
- [ ] Events with multiple scoring types found
- [ ] No fragmented events with suffixes
- [ ] Diep supports: _____
- [ ] Bonk supports: _____
- [ ] Krunker supports: _____

---

## Test 3: Supported Scoring Types Completeness
**Objective**: Verify all events have supported_scoring_types populated

### Execute:
```sql
-- Check for events missing supported_scoring_types
SELECT COUNT(*) 
FROM events 
WHERE is_active = 1 
  AND (supported_scoring_types IS NULL OR supported_scoring_types = '');

-- Sample events with their supported types
SELECT name, scoring_type, supported_scoring_types 
FROM events 
WHERE is_active = 1 
ORDER BY name 
LIMIT 20;
```

### Expected Results:
- 0 events missing supported_scoring_types
- All events should have at least their primary scoring_type in supported_scoring_types

### Actual Results:
- [ ] Events missing supported_scoring_types: _____
- [ ] All sampled events have valid supported_scoring_types

---

## Test 4: Challenge Command - Unified Event Resolution
**Objective**: Verify /challenge command works with unified events

### Discord Bot Test Steps:
1. Use `/challenge` command
2. Select cluster: "IO Games"
3. For event autocomplete, start typing "Diep"
4. Select "Diep" from autocomplete (should show only one option, not multiple)
5. Select match_type: "ffa"
6. Add players: mention 3-4 users

### Expected Results:
- Event autocomplete shows "Diep" (not "Diep (FFA)")
- Challenge creation succeeds
- Challenge embed shows correct event name and type

### Actual Results:
- [ ] Event autocomplete shows unified "Diep"
- [ ] No duplicate Diep entries in autocomplete
- [ ] FFA challenge created successfully
- [ ] Challenge embed displays correctly

---

## Test 5: Team Challenge - Team Name Display
**Objective**: Verify team challenges show "Team A" and "Team B"

### Discord Bot Test Steps:
1. Use `/challenge` command
2. Select any cluster and event
3. Select match_type: "team"
4. Add 4 players
5. In the modal, assign players 1,2 to Team A and players 3,4 to Team B
6. Submit the modal

### Expected Results:
- Modal shows "Team A Members" and "Team B Members" fields
- Only 2 team fields available (no Team C or D)
- Challenge embed displays teams as "Team A" and "Team B"
- NOT "Team 0" and "Team 1"

### Actual Results:
- [ ] Modal has only 2 team fields
- [ ] Fields labeled "Team A Members" and "Team B Members"
- [ ] Challenge embed shows "Team A" and "Team B"
- [ ] No "Team 0" or "Team 1" displayed

---

## Test 6: Cross-Mode Challenge Validation
**Objective**: Test that unsupported scoring types are rejected

### Discord Bot Test Steps:
1. Find an event that only supports 1v1 (e.g., Chess events)
2. Try to create a team challenge for that event
3. Try to create an FFA challenge for that event

### Execute in DB to find 1v1-only events:
```sql
SELECT name, supported_scoring_types 
FROM events 
WHERE supported_scoring_types = '1v1' 
LIMIT 5;
```

### Expected Results:
- Error message when trying unsupported match types
- Clear indication that the event doesn't support that mode

### Actual Results:
- [ ] 1v1-only event identified: _____
- [ ] Team challenge rejected with error
- [ ] FFA challenge rejected with error
- [ ] Error messages are clear and helpful

---

## Test 7: PlayerEventStats Consolidation
**Objective**: Verify player stats were properly consolidated

### Execute:
```sql
-- Check for duplicate PlayerEventStats
SELECT player_id, COUNT(DISTINCT event_id) as event_count
FROM player_event_stats
GROUP BY player_id
HAVING COUNT(DISTINCT event_id) > 20
LIMIT 5;

-- Verify no orphaned stats for deprecated events
SELECT COUNT(*) 
FROM player_event_stats pes
JOIN events e ON pes.event_id = e.id
WHERE e.is_active = 0;
```

### Expected Results:
- Players should have reasonable event counts (not duplicates)
- No stats should exist for inactive/deprecated events

### Actual Results:
- [ ] Player event counts appear reasonable
- [ ] Orphaned stats count: _____

---

## Test 8: Match Creation with Scoring Type
**Objective**: Verify new matches use Match.scoring_type field

### Discord Bot Test Steps:
1. Create a challenge and have all players accept
2. Complete the match with results
3. Check database for the created match

### Execute after match completion:
```sql
-- Check recent matches
SELECT id, event_id, scoring_type, created_at 
FROM matches 
ORDER BY created_at DESC 
LIMIT 5;

-- Verify scoring_type is populated
SELECT COUNT(*) 
FROM matches 
WHERE scoring_type IS NULL OR scoring_type = '';
```

### Expected Results:
- New matches have scoring_type field populated
- Scoring type matches the challenge type (1v1, FFA, Team)

### Actual Results:
- [ ] Recent match has scoring_type: _____
- [ ] Matches missing scoring_type: _____

---

## Test 9: Event Browsing and Selection
**Objective**: Verify event browser shows unified events correctly

### Discord Bot Test Steps:
1. Use any command that shows event lists
2. Browse through IO Games cluster events

### Expected Results:
- Event list shows "Diep", "Bonk", "Paper" (3 events)
- NOT "Diep (1v1)", "Diep (Team)", etc. (was 7 events)

### Actual Results:
- [ ] IO Games shows 3 unified events
- [ ] No fragmented events visible

---

## Test 10: Rollback Script Validation
**Objective**: Ensure rollback script exists and is executable

### Execute:
```bash
# Check rollback script exists
ls -la rollback_phase_2_4_1_*.sh

# Check it's executable
# DO NOT RUN unless you want to rollback!
# ./rollback_phase_2_4_1_*.sh
```

### Expected Results:
- Rollback script exists with timestamp
- Script has executable permissions (rwxr-xr-x)

### Actual Results:
- [ ] Rollback script found: _____
- [ ] Script is executable

---

## Summary Checklist

### Database Changes
- [ ] Match.scoring_type column added
- [ ] Event.supported_scoring_types column added
- [ ] Events properly consolidated (~70 unified from 86 fragmented)
- [ ] All events have supported_scoring_types populated

### Challenge Command
- [ ] Autocomplete shows unified event names
- [ ] Correct validation of supported match types
- [ ] Team challenges display as "Team A" and "Team B"
- [ ] Only 2 teams supported (no Team C/D)

### Data Integrity
- [ ] PlayerEventStats properly consolidated
- [ ] No orphaned stats for deprecated events
- [ ] New matches use scoring_type field

### Overall Result
- [ ] **PASS** - All tests successful
- [ ] **FAIL** - Issues found (list below)

### Issues Found:
1. 
2. 
3. 

### Notes: