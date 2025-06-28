# Test Plan: Phase 1 - Unified Event Elo Schema Changes

## Overview
This test plan verifies that making `Event.scoring_type` nullable doesn't break existing functionality while preparing for unified event Elo implementation.

## Pre-Migration Checks

### 1. Backup Verification
```bash
# Verify backup exists
ls -la tournament_backup_unified_elo_phase1_*.db
```
**Expected**: Backup file exists with current timestamp

### 2. Current Data State
```bash
# Check current events
sqlite3 tournament.db "SELECT id, name, scoring_type FROM events LIMIT 10;"
```
**Expected**: All events have non-null scoring_type values

## Migration Execution

### 3. Run Migration
```bash
python migration_phase_1_unified_elo.py
```
**Expected Output**:
- "Starting Phase 1: Unified Event Elo - Schema Migration"
- "Created backup: tournament_backup_unified_elo_phase1_[timestamp].db"
- "Successfully made scoring_type nullable"
- "Phase 1 Migration: SUCCESS"

## Post-Migration Tests

### 4. Schema Verification
```bash
# Check that scoring_type is nullable
sqlite3 tournament.db ".schema events" | grep scoring_type
```
**Expected**: `scoring_type VARCHAR(20),` (no NOT NULL constraint)

### 5. Data Integrity
```bash
# Verify all existing events retained their scoring_type
sqlite3 tournament.db "SELECT COUNT(*) as total, COUNT(scoring_type) as with_type FROM events;"
```
**Expected**: total = with_type (no data loss)

### 6. Bot Startup Test
```bash
# Start the bot and ensure it loads without errors
python -m bot.main
```
**Expected**: Bot starts normally, no SQLAlchemy errors

### 7. Basic Command Tests

#### 7.1 List Events
In Discord:
```
/list-events
```
**Expected**: Lists all events normally with their scoring types displayed (separated events like "Rat.quiz (1v1)", "Rat.quiz (Team)" is CORRECT for Phase 1)

#### 7.2 List Events with Cluster Filter
```
/list-events cluster_name:"Rat"
```
**Expected**: Shows events in specific cluster, still separated by scoring type (CORRECT for Phase 1)

### 8. Match Creation Tests

#### 8.1 Challenge Creation (1v1)
```
!challenge @opponent "Diep (1v1)"
```
**Expected**: Challenge created successfully

#### 8.2 Match Creation via Challenges
```
/challenge @opponent event_name:"Test Event"
```
**Expected**: Challenge system works (FFA is now part of challenge system, not separate command)

### 9. Match Completion Test
```
# Complete a challenge
!challenge_complete [challenge_id] win
```
**Expected**: 
- Match completes successfully
- Elo changes calculated correctly
- Uses event.scoring_type for strategy selection (current behavior)

### 10. CSV Import Test
```bash
# Test that CSV import still works
python populate_from_csv.py
```
**Expected**: Events created with scoring_type values from CSV

## Rollback Test

### 11. Test Rollback Script
```bash
# First, make a test change
sqlite3 tournament.db "UPDATE events SET scoring_type = NULL WHERE id = 1;"

# Run rollback
./rollback_unified_elo_phase1_[timestamp].sh

# Verify rollback
sqlite3 tournament.db "SELECT scoring_type FROM events WHERE id = 1;"
```
**Expected**: Original scoring_type value restored

## Edge Cases

### 12. Null Scoring Type Handling
```bash
# Manually create event with null scoring_type
sqlite3 tournament.db "INSERT INTO events (name, cluster_id) VALUES ('Test Event', 1);"

# Try to create match with this event
# This should fail gracefully in current code
```
**Expected**: Error handling prevents using events without scoring_type

## Performance Tests

### 13. Query Performance
```bash
# Check that nullable column doesn't impact performance
sqlite3 tournament.db "EXPLAIN QUERY PLAN SELECT * FROM events WHERE scoring_type = '1v1';"
```
**Expected**: Query plan shows efficient execution

## Summary Checklist

- [ ] Backup created successfully
- [ ] Migration completes without errors
- [ ] All existing events retain scoring_type values
- [ ] Bot starts normally
- [ ] All Discord commands work as before
- [ ] Match creation and completion work correctly
- [ ] CSV import continues to function
- [ ] Rollback script works if needed
- [ ] No performance degradation

## Next Phase Prerequisites

Before proceeding to Phase 2, ensure:
1. All tests pass
2. No errors in bot logs
3. User functionality unchanged
4. Backup and rollback scripts available

## Notes
- This is a non-destructive change that maintains backward compatibility
- The scoring_type field is deprecated but still functional
- Phase 2 will begin transitioning to match_format for scoring strategy selection