# Phase 1.5 Test Plan: UI Aggregation Layer

## Overview
This test plan validates the UI aggregation functionality that groups events by base name while preserving the underlying data structure.

## Pre-Migration Tests

### 1. Current State Verification
```sql
-- Check events without base_event_name
SELECT COUNT(*) FROM events WHERE base_event_name IS NULL;
```
**Expected**: All events (or error if column doesn't exist yet)

### 2. Event Count by Cluster
```sql
-- Count events in IO Games cluster
SELECT COUNT(*) FROM events WHERE cluster_id = (SELECT id FROM clusters WHERE name = 'IO Games');
```
**Expected**: 7 events (Bonk x3, Diep x3, Paper x1)

## Migration Execution

### 3. Run Migration Script
```bash
python migration_phase_1_5_ui_aggregation.py
```
**Expected**: 
- Backup created
- base_event_name column added
- Index created
- All events populated with base names
- Migration report generated

### 4. Verify Migration Results
```sql
-- Check populated base_event_names
SELECT name, base_event_name FROM events WHERE name LIKE 'Bonk%' ORDER BY name;
```
**Expected**:
- Bonk (1v1) → Bonk
- Bonk (FFA) → Bonk
- Bonk (Team) → Bonk

### 5. Check Aggregation Counts
```sql
-- Count unique base events in IO Games
SELECT base_event_name, COUNT(*) as variations 
FROM events 
WHERE cluster_id = (SELECT id FROM clusters WHERE name = 'IO Games')
GROUP BY base_event_name
ORDER BY base_event_name;
```
**Expected**:
- Bonk: 3 variations
- Diep: 3 variations
- Paper: 1 variation

## Bot Functionality Tests

### 6. Bot Startup Test
```bash
python -m bot.main
```
**Expected**: Bot starts without SQLAlchemy errors

### 7. Discord Command Tests

#### 7.1 Slash Command - Aggregated View (Default)
```
/list-events
```
**Expected**: 
- Shows "Tournament Events (Grouped)"
- IO Games shows 3 events: Bonk, Diep, Paper
- Each shows variation count (e.g., "3 variations: 1v1, FFA, Team")

#### 7.2 Toggle to Detailed View
Click "📊 Detailed View" button
**Expected**:
- Title changes to "Tournament Events"
- Shows all 7 individual events in IO Games
- Button changes to "📋 Grouped View"

#### 7.3 Filter Test with Aggregation
```
/list-events cluster_name:"IO Games"
```
**Expected**: Shows only 3 grouped events for IO Games

### 8. CSV Import Test

#### 8.1 Clear Test Data
```sql
-- Remove a test event to re-import
DELETE FROM events WHERE name = 'Test Import Event';
```

#### 8.2 Import New Event
Add to CSV and run import
**Expected**: New event created with base_event_name populated

### 9. Edge Case Tests

#### 9.1 Events Without Suffix
```sql
SELECT name, base_event_name FROM events WHERE name IN ('Arsenal', 'Bedwars', 'Blitz');
```
**Expected**: base_event_name equals name (no change)

#### 9.2 Events with Non-Scoring Parentheses
Check events like "Game (Winter Edition)" if any exist
**Expected**: Parentheses preserved, not treated as scoring type

### 10. Performance Test
```sql
-- Test aggregation query performance
EXPLAIN QUERY PLAN
SELECT base_event_name, COUNT(*) 
FROM events 
GROUP BY base_event_name;
```
**Expected**: Uses index on base_event_name

## Rollback Test (Optional)

### 11. Test Rollback Script
```bash
# Find the generated rollback script
ls rollback_ui_aggregation_phase1_5_*.sh

# Execute if needed (DO NOT run unless actually rolling back)
# ./rollback_ui_aggregation_phase1_5_[timestamp].sh
```
**Expected**: Would restore database to pre-migration state

## Success Criteria
- [ ] Migration completes without errors
- [ ] All events have base_event_name populated correctly
- [ ] Aggregated view shows correct counts (3 for IO Games)
- [ ] Toggle between grouped/detailed views works
- [ ] No performance degradation
- [ ] CSV import continues to work with base_event_name
- [ ] Existing functionality remains intact