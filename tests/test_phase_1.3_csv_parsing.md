# Phase 1.3: CSV Parsing and Data Population - Manual Test Suite

## Overview
This test suite validates the CSV parsing system, data population functionality, and admin commands for managing tournament clusters and events.

## Prerequisites
- Discord bot is running and connected
- You have owner permissions (Config.OWNER_DISCORD_ID)
- CSV file "LB Culling Games List.csv" exists in project root
- Database is initialized

## Test Environment Setup

### Before Testing
1. **Backup Current Database** (if needed):
   ```bash
   cp tournament.db tournament_backup_phase_1.3_$(date +%Y%m%d_%H%M%S).db
   ```

2. **Verify CSV File**: Ensure "LB Culling Games List.csv" is present and readable

3. **Check Bot Status**: Confirm bot is online and responsive

---

## Test 1: Standalone CSV Population Script

### Test 1.1: Basic Script Execution
**Objective**: Verify the standalone populate_from_csv.py script works correctly

**Steps**:
1. Run the standalone script:
   ```bash
   python populate_from_csv.py
   ```

2. Check console output for:
   - "Starting CSV population script..."
   - Progress messages for cluster creation
   - Final summary with counts
   - No error messages

**Expected Results**:
- Script completes without errors
- Reports creation of 20 clusters
- Reports creation of 60+ events
- Log file created in logs/ directory

**Pass/Fail**: ___________

### Test 1.2: Script Output Validation
**Objective**: Verify correct parsing of complex scoring types

**Steps**:
1. Check the log file for evidence of complex parsing:
   - Look for events with suffixes like "Krunker (1v1)" and "Krunker (FFA)"
   - Verify "2v2" events are converted to "Team"
   - Check that leaderboard events have score_direction set

2. Count total events created (should be >70 due to mixed types)

**Expected Results**:
- Mixed scoring types create multiple events with suffixes
- All "2v2" entries become "Team" scoring type
- Leaderboard events have HIGH/LOW direction set appropriately
- Running/time events have "LOW" direction
- Score/points events have "HIGH" direction

**Pass/Fail**: ___________

---

## Test 2: Database Integration

### Test 2.1: Database Population via Bot
**Objective**: Verify the enhanced database import method works

**Steps**:
1. Clear existing data (if any):
   ```bash
   sqlite3 tournament.db "DELETE FROM events; DELETE FROM clusters;"
   ```

2. Use the bot's database method to import:
   ```python
   # In a Python shell or test script:
   import asyncio
   from bot.database.database import Database
   
   async def test_import():
       db = Database()
       await db.initialize()
       async with db.get_session() as session:
           await db.import_clusters_and_events_from_csv(session, clear_existing=True)
       await db.close()
   
   asyncio.run(test_import())
   ```

**Expected Results**:
- No errors during import
- Same results as standalone script
- Enhanced parsing functions are used
- Existing data is cleared before import

**Pass/Fail**: ___________

### Test 2.2: Data Integrity Verification
**Objective**: Verify database contains correct data structure

**Steps**:
1. Check cluster count:
   ```bash
   sqlite3 tournament.db "SELECT COUNT(*) FROM clusters;"
   ```

2. Check event count:
   ```bash
   sqlite3 tournament.db "SELECT COUNT(*) FROM events;"
   ```

3. Verify complex events exist:
   ```bash
   sqlite3 tournament.db "SELECT name, scoring_type FROM events WHERE name LIKE '%(%';"
   ```

4. Check score direction for leaderboard events:
   ```bash
   sqlite3 tournament.db "SELECT name, score_direction FROM events WHERE scoring_type = 'Leaderboard';"
   ```

**Expected Results**:
- 20 clusters in database
- 70+ events in database
- Events with suffixes like "Krunker (1v1)" exist
- Leaderboard events have score_direction set (HIGH/LOW)

**Pass/Fail**: ___________

---

## Test 3: Discord Admin Commands

### Test 3.1: admin-populate-data Command
**Objective**: Test the Discord command for data population

**Steps**:
1. In Discord, run: `/admin-populate-data`

2. Observe the response embeds:
   - Initial "Starting CSV Data Population" message
   - Final success message with counts

3. Verify no error messages

**Expected Results**:
- Blue "starting" embed appears immediately
- Green "completed" embed appears after processing
- Counts match expected values (20 clusters, 70+ events)
- No red error embeds

**Pass/Fail**: ___________

### Test 3.2: admin-list-clusters Command
**Objective**: Test cluster listing functionality

**Steps**:
1. In Discord, run: `/admin-list-clusters`

2. Verify the response shows:
   - All 20 clusters numbered 1-20
   - Cluster names match CSV
   - Event counts for each cluster
   - Green status indicators (active)

**Expected Results**:
- Clean formatted list of clusters
- Correct numbering and names
- Event counts shown for each cluster
- All clusters marked as active (🟢)

**Pass/Fail**: ___________

### Test 3.3: admin-list-events Command (All Events)
**Objective**: Test event listing without filter

**Steps**:
1. In Discord, run: `/admin-list-events`

2. Check the response:
   - Events grouped by cluster
   - Scoring types shown correctly
   - Status indicators present
   - Reasonable truncation if too many events

**Expected Results**:
- Events organized by cluster fields
- Mixed scoring types show with suffixes
- Score direction shown for leaderboard events
- Clean formatting within Discord limits

**Pass/Fail**: ___________

### Test 3.4: admin-list-events Command (Filtered)
**Objective**: Test event listing with cluster filter

**Steps**:
1. In Discord, run: `/admin-list-events cluster_name:Chess`

2. Verify response shows only Chess events:
   - Bullet (1v1)
   - Blitz (1v1)
   - Rapid (1v1)

3. Test with a cluster that has mixed scoring types:
   `/admin-list-events cluster_name:IO Games`

**Expected Results**:
- Chess cluster shows 3 events, all 1v1
- IO Games shows events with different scoring types
- Mixed events show with appropriate suffixes
- Clear formatting and status indicators

**Pass/Fail**: ___________

---

## Test 4: Error Handling and Edge Cases

### Test 4.1: Missing CSV File
**Objective**: Test behavior when CSV file is missing

**Steps**:
1. Temporarily rename the CSV file:
   ```bash
   mv "LB Culling Games List.csv" "LB Culling Games List.csv.backup"
   ```

2. Try to run `/admin-populate-data`

3. Restore the file:
   ```bash
   mv "LB Culling Games List.csv.backup" "LB Culling Games List.csv"
   ```

**Expected Results**:
- Red error embed appears
- Clear error message about missing file
- No partial data corruption
- System remains stable

**Pass/Fail**: ___________

### Test 4.2: Invalid CSV Data
**Objective**: Test handling of malformed CSV data

**Steps**:
1. Create a test CSV with invalid data:
   ```csv
   Cluster Number,Cluster,Game Mode,Scoring Type,Notes
   999,Test Cluster,Test Event,InvalidType,Test
   abc,Bad Cluster,Bad Event,1v1,Test
   ```

2. Temporarily replace the CSV file and run population

3. Restore original CSV

**Expected Results**:
- Invalid scoring types are skipped with warnings
- Invalid cluster numbers are skipped
- Valid data is still processed
- Clear error reporting in logs

**Pass/Fail**: ___________

### Test 4.3: Permission Verification
**Objective**: Verify admin commands are owner-only

**Steps**:
1. Have a non-owner user try: `/admin-populate-data`
2. Verify they get a permission denied response
3. Test with all three admin commands

**Expected Results**:
- Non-owner users cannot execute admin commands
- Clear permission error messages
- No data access or modification by unauthorized users

**Pass/Fail**: ___________

---

## Test 5: Data Verification and Business Logic

### Test 5.1: Complex Scoring Type Parsing
**Objective**: Verify specific complex cases are handled correctly

**Steps**:
1. Check for these specific events in the database:
   ```bash
   sqlite3 tournament.db "SELECT name, scoring_type FROM events WHERE name LIKE 'Krunker%';"
   sqlite3 tournament.db "SELECT name, scoring_type FROM events WHERE name LIKE 'Brawhalla%';"
   sqlite3 tournament.db "SELECT name, scoring_type FROM events WHERE name LIKE 'Rat.%';"
   ```

2. Verify the results match expected parsing:
   - "Krunker" with "1v1/FFA" should create "Krunker (1v1)" and "Krunker (FFA)"
   - "Brawhalla" with "1v1/2v2" should create "Brawhalla (1v1)" and "Brawhalla (Team)"
   - Rat games with "1v1, 2v2" should create both variants

**Expected Results**:
- Complex scoring types correctly split into separate events
- "2v2" normalized to "Team" scoring type
- Comma and slash separators both handled
- Event names have appropriate suffixes

**Pass/Fail**: ___________

### Test 5.2: Score Direction Inference
**Objective**: Verify score direction is correctly inferred for leaderboard events

**Steps**:
1. Check specific leaderboard events:
   ```bash
   sqlite3 tournament.db "SELECT name, score_direction FROM events WHERE name LIKE '%run%' OR name LIKE '%time%';"
   sqlite3 tournament.db "SELECT name, score_direction FROM events WHERE name LIKE '%score%' OR name LIKE '%points%';"
   ```

2. Verify running/time events have "LOW" direction
3. Verify score/points events have "HIGH" direction

**Expected Results**:
- Running events (40 yd dash, 1 mi run, etc.) have score_direction = "LOW"
- Score-based events have score_direction = "HIGH"
- Time-based events (completion time) have score_direction = "LOW"
- Default leaderboard events have score_direction = "HIGH"

**Pass/Fail**: ___________

### Test 5.3: Player Limits Configuration
**Objective**: Verify events have correct min/max player limits

**Steps**:
1. Check player limits by scoring type:
   ```bash
   sqlite3 tournament.db "SELECT DISTINCT scoring_type, min_players, max_players FROM events ORDER BY scoring_type;"
   ```

**Expected Results**:
- 1v1 events: min_players=2, max_players=2
- Team events: min_players=4, max_players=10
- FFA events: min_players=3, max_players=16
- Leaderboard events: min_players=3, max_players=16

**Pass/Fail**: ___________

---

## Test 6: Performance and Reliability

### Test 6.1: Multiple Population Runs
**Objective**: Test idempotent behavior and performance

**Steps**:
1. Run `/admin-populate-data` multiple times in succession
2. Time each execution
3. Verify data consistency after each run

**Expected Results**:
- Each run completes successfully
- Data counts remain consistent
- No duplicate entries created
- Performance remains acceptable (<30 seconds)

**Pass/Fail**: ___________

### Test 6.2: Transaction Integrity
**Objective**: Verify atomic transactions work correctly

**Steps**:
1. Interrupt the population process (if possible)
2. Check database state
3. Run population again

**Expected Results**:
- Interrupted operations don't leave partial data
- Database remains in consistent state
- Subsequent operations complete successfully

**Pass/Fail**: ___________

---

## Test Summary

### Overall Results
**Tests Passed**: _____ / 15
**Tests Failed**: _____ / 15
**Overall Status**: PASS / FAIL

### Critical Issues Found
(List any critical issues that must be addressed)

### Minor Issues Found
(List any minor issues or improvements)

### Recommendations
(Any suggestions for improvements or additional testing)

---

## Test Environment Information
- **Date**: ___________
- **Tester**: ___________
- **Bot Version**: ___________
- **Database State**: ___________
- **CSV File Date**: ___________

### Final Verification
After all tests, verify the system is ready for Phase 1.4:
- [ ] All clusters and events properly loaded
- [ ] Admin commands working correctly
- [ ] No data integrity issues
- [ ] Performance is acceptable
- [ ] Error handling is robust

**Phase 1.3 Status**: READY FOR NEXT PHASE / NEEDS FIXES