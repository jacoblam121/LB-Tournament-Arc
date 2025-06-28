# Phase 1 Complete - Manual Test Suite

## Overview
This test suite verifies that all Phase 1 components (1.1, 1.2, 1.3) are working correctly and the foundation is ready for Phase 2.

## Pre-Test Setup

1. **Ensure bot is running**:
   ```bash
   python -m bot.main
   ```
   - Look for "MatchCommandsCog: All operations initialized successfully" in logs
   - Bot should show online in Discord

## Test 1: Architecture Enforcement ✅

### Test 1.1: /ffa Command Deprecation
**Instructions**:
1. In Discord, run: `/ffa @yourself`
2. **Expected**: Orange embed with "⚠️ Command Deprecated" title
3. **Expected**: 4-step guidance directing to `/challenge` workflow
4. **Expected**: Message appears as ephemeral (only you can see it)

### Test 1.2: Architecture Functions Removed
**Instructions**:
1. Open Python REPL: `python`
2. Run these commands:
   ```python
   import sys
   sys.path.append('bot')
   from bot.operations.event_operations import EventOperations
   
   # These should all raise AttributeError
   try:
       EventOperations.create_ffa_event
       print("❌ FAIL: create_ffa_event still exists")
   except AttributeError:
       print("✅ PASS: create_ffa_event removed")
   
   try:
       EventOperations.create_team_event  
       print("❌ FAIL: create_team_event still exists")
   except AttributeError:
       print("✅ PASS: create_team_event removed")
   
   try:
       EventOperations.FFA_MIN_PLAYERS
       print("❌ FAIL: FFA_MIN_PLAYERS still exists") 
   except AttributeError:
       print("✅ PASS: FFA_MIN_PLAYERS removed")
   ```
3. Exit Python: `exit()`

## Test 2: Database Population ✅

### Test 2.1: Verify Cluster Creation
**Instructions**:
1. Open SQLite: `sqlite3 tournament.db`
2. Run: `SELECT COUNT(*) as cluster_count FROM clusters;`
3. **Expected**: `cluster_count` = 20
4. Run: `SELECT number, name FROM clusters ORDER BY number LIMIT 5;`
5. **Expected**: Should show clusters 1-5 with proper names

### Test 2.2: Verify Event Creation  
**Instructions** (continue in SQLite):
1. Run: `SELECT COUNT(*) as event_count FROM events;`
2. **Expected**: `event_count` >= 86 (should be exactly what populate script reported)
3. Run: `SELECT name, scoring_type, cluster_id FROM events WHERE cluster_id = 1 LIMIT 3;`
4. **Expected**: Should show events for cluster 1 with proper scoring types
5. Run: `SELECT DISTINCT scoring_type FROM events;`
6. **Expected**: Should show: 1v1, FFA, Team, Leaderboard

### Test 2.3: Verify Base Event Names
**Instructions** (continue in SQLite):
1. Run: `SELECT name, base_event_name FROM events WHERE base_event_name IS NOT NULL LIMIT 5;`
2. **Expected**: base_event_name should be populated and shorter than full name
3. Exit SQLite: `.exit`

## Test 3: Schema Cleanup ✅

### Test 3.1: Legacy Columns Removed
**Instructions**:
1. Open SQLite: `sqlite3 tournament.db`
2. Run: `PRAGMA table_info(challenges);`
3. **Expected**: Should NOT see `challenger_id` or `challenged_id` columns
4. Count columns: Should see exactly 17 columns (not 19)

### Test 3.2: Performance Indexes Created
**Instructions** (continue in SQLite):
1. Run: `.indexes challenges`
2. **Expected**: Should see these indexes:
   - `idx_challenges_status`
   - `idx_challenges_created_at` 
   - `idx_challenges_event_id`
3. Run: `.indexes challenge_participants`
4. **Expected**: Should see these indexes:
   - `idx_challenge_participants_challenge`
   - `idx_challenge_participants_player`
   - `idx_challenge_participants_status`
5. Run: `.indexes events`
6. **Expected**: Should see: `idx_events_base_name`
7. Exit SQLite: `.exit`

### Test 3.3: Migration Backup Exists
**Instructions**:
1. Run: `ls -la tournament_backup_phase_1_3_*.db`
2. **Expected**: Should show backup file with today's timestamp
3. Run: `sqlite3 tournament_backup_phase_1_3_*.db "SELECT COUNT(*) FROM clusters;"`
4. **Expected**: Should show same cluster count as main database

## Test 4: Data Integrity ✅

### Test 4.1: Foreign Key Relationships
**Instructions**:
1. Open SQLite: `sqlite3 tournament.db`
2. Run: `PRAGMA foreign_keys=ON;`
3. Run: `PRAGMA foreign_key_check;`
4. **Expected**: May show violations for `player_event_stats` (orphaned from old FFA data - this is normal)
5. **Expected**: Should NOT show violations for `challenges`, `events`, or `clusters`

### Test 4.2: Cluster-Event Hierarchy
**Instructions** (continue in SQLite):
1. Run:
   ```sql
   SELECT c.name as cluster, COUNT(e.id) as event_count 
   FROM clusters c 
   LEFT JOIN events e ON c.id = e.cluster_id 
   GROUP BY c.id, c.name 
   ORDER BY c.number 
   LIMIT 5;
   ```
2. **Expected**: Each cluster should have multiple events (at least 3-5 each)
3. Exit SQLite: `.exit`

## Test 5: Bot Functionality Preservation ✅

### Test 5.1: Match Reporting Still Works
**Instructions**:
1. In Discord, try to access match reporting functionality
2. **Expected**: Should work without EventOperations errors
3. **Expected**: Modal and placement systems should be functional

### Test 5.2: Help System Updated
**Instructions**:
1. In Discord, run: `!match-help` or `!help`
2. **Expected**: Should NOT mention `/ffa` as available command
3. **Expected**: Should mention `/ffa` deprecation if help system updated

## Test 6: Performance Verification ✅

### Test 6.1: Database Query Performance
**Instructions**:
1. Open SQLite: `sqlite3 tournament.db`
2. Run: `.timer ON`
3. Run: `SELECT * FROM events WHERE base_event_name LIKE 'Diep%';`
4. **Expected**: Should complete quickly (< 50ms) due to index
5. Run: `SELECT * FROM challenge_participants WHERE status = 'PENDING';`
6. **Expected**: Should complete quickly due to status index
7. Exit SQLite: `.exit`

## Expected Results Summary

**All tests should PASS for these counts**:
- ✅ Clusters: 20
- ✅ Events: 86+ 
- ✅ Indexes: 7 total
- ✅ Challenge table columns: 17 (down from 19)
- ✅ No architecture-violating functions
- ✅ /ffa shows deprecation notice
- ✅ Database backup exists
- ✅ All functionality preserved

## Failure Scenarios

**If any test fails**:
1. ❌ **Architecture functions exist**: Phase 1.1 incomplete
2. ❌ **Wrong cluster/event counts**: Phase 1.2 incomplete  
3. ❌ **Missing indexes**: Phase 1.3 incomplete
4. ❌ **Legacy columns present**: Phase 1.3 incomplete
5. ❌ **Bot startup fails**: Critical integration issue

## Post-Test Actions

**When ALL tests pass**:
1. Mark Phase 1 as ✅ **COMPLETELY VERIFIED**
2. Update planB.md with test results
3. Ready to begin Phase 2: /challenge Command implementation

**Test completed by**: [Your name]  
**Date**: [Today's date]  
**Status**: [PASS/FAIL with details]