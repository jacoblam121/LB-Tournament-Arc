# Phase 3.4 Manual Test Plan - Weekly Processing System

## Overview
This test plan covers the manual weekly processing system for leaderboard events. The system processes weekly scores, calculates Z-score based Elos, updates player averages, applies inactivity penalties, and calculates composite rankings.

## Prerequisites
- Bot is running and connected to Discord
- Database is properly migrated with leaderboard fields
- At least one leaderboard event exists with `score_direction` set (HIGH or LOW)
- Test user has bot owner permissions

## Test Environment Setup

### 1. Verify Database State
```sql
-- Check that leaderboard event exists
SELECT id, name, score_direction FROM events WHERE score_direction IS NOT NULL;

-- Check PlayerEventStats table has weekly fields
SELECT player_id, event_id, weekly_elo_average, weeks_participated 
FROM player_event_stats LIMIT 5;

-- Verify LeaderboardScore table exists
SELECT COUNT(*) FROM leaderboard_scores;
```

### 2. Test Data Preparation
Before testing, ensure you have:
- [ ] At least 1 leaderboard event (HIGH or LOW direction)
- [ ] 3-5 test players who can submit scores
- [ ] Some weekly scores already submitted for current week

---

## Test Suite A: Basic Weekly Processing

### Test A1: Single Event Processing with Multiple Players
**Objective**: Verify basic weekly processing functionality works end-to-end.

**Setup**:
1. Identify a leaderboard event: `/submit-event-score` autocomplete to see available events
2. Have 3-5 players submit scores for the current week using `/submit-event-score`
3. Note the event name and submitted scores

**Test Steps**:
1. Run the weekly reset command:
   ```
   /admin-weekly-reset event_name:"[YOUR_EVENT_NAME]" reason:"Test A1 - Basic processing"
   ```

**Expected Results**:
- [ ] Command completes without errors
- [ ] Success embed shows:
  - [ ] Correct week number
  - [ ] Active players count matches submitted scores
  - [ ] Total participants ≥ active players
  - [ ] Scores processed count matches submissions
- [ ] Top 5 leaderboard displayed with:
  - [ ] Player names shown correctly
  - [ ] Green circles (🟢) for active players this week
  - [ ] Composite Elo values calculated
  - [ ] All-time and Weekly Avg Elo shown in parentheses

**Database Validation**:
```sql
-- Verify weekly scores were cleared
SELECT COUNT(*) FROM leaderboard_scores 
WHERE event_id = [EVENT_ID] AND score_type = 'weekly';
-- Should be 0

-- Verify player stats were updated
SELECT player_id, weekly_elo_average, weeks_participated, final_score
FROM player_event_stats WHERE event_id = [EVENT_ID];
-- Should show updated averages and incremented participation counts
```

### Test A2: HIGH Direction Event (Points/Score)
**Objective**: Test processing for events where higher scores are better.

**Setup**:
1. Use an event with `score_direction = 'HIGH'` (like Tetris, points-based games)
2. Submit varying scores: 1000, 2000, 3000, 1500, 2500

**Test Steps**:
1. Run weekly reset for the HIGH direction event
2. Observe the calculated weekly Elos

**Expected Results**:
- [ ] Player with highest score (3000) gets highest weekly Elo
- [ ] Player with lowest score (1000) gets lowest weekly Elo  
- [ ] Z-scores are calculated correctly (above mean = positive)
- [ ] Elo values are reasonable (around 1000 ± 200-400)

### Test A3: LOW Direction Event (Time/Speed)
**Objective**: Test processing for events where lower scores are better.

**Setup**:
1. Use an event with `score_direction = 'LOW'` (like sprint times, speedruns)
2. Submit varying times: 30.5, 45.2, 25.8, 40.1, 35.0

**Test Steps**:
1. Run weekly reset for the LOW direction event

**Expected Results**:
- [ ] Player with lowest score (25.8) gets highest weekly Elo
- [ ] Player with highest score (45.2) gets lowest weekly Elo
- [ ] Z-scores are inverted correctly (lower score = positive Z-score)

---

## Test Suite B: Inactivity Penalty System

### Test B1: Verify Inactivity Penalties
**Objective**: Ensure players who miss a week get penalized appropriately.

**Setup**:
1. Identify players who participated in previous weeks but didn't submit this week
2. Check their stats before processing:
   ```sql
   SELECT player_id, weekly_elo_average, weeks_participated 
   FROM player_event_stats WHERE event_id = [EVENT_ID];
   ```

**Test Steps**:
1. Run weekly processing
2. Check the same players' stats after processing

**Expected Results**:
- [ ] Inactive players have `weeks_participated` incremented by 1
- [ ] Their `weekly_elo_average` is diluted (decreased due to adding 0)
- [ ] Active players maintain or improve their averages
- [ ] Red circles (🔴) shown for inactive players in results

### Test B2: Mixed Activity Pattern
**Objective**: Test system with both active and inactive players.

**Setup**:
1. Have 3 players submit scores this week
2. Ensure 2 other players who participated before don't submit

**Test Steps**:
1. Run weekly processing
2. Verify the leaderboard results

**Expected Results**:
- [ ] Active players: 3 (green circles)
- [ ] Total participants: 5 (includes inactive)
- [ ] Inactive players show lower composite Elos due to penalty
- [ ] Results correctly distinguish active vs inactive players

---

## Test Suite C: Composite Elo Calculation

### Test C1: 50/50 Formula Verification
**Objective**: Verify the composite Elo formula works correctly.

**Setup**:
1. Find a player with existing all-time Elo and weekly average
2. Note their values before processing

**Manual Calculation**:
```
Expected Composite = (All_Time_Elo × 0.5) + (Weekly_Avg_Elo × 0.5)
```

**Test Steps**:
1. Run weekly processing
2. Compare results with manual calculation

**Expected Results**:
- [ ] Composite Elo matches manual calculation (within rounding)
- [ ] Formula balances all-time skill with recent weekly performance
- [ ] Players with high weekly averages but low all-time get boosted
- [ ] Players with high all-time but recent inactivity get balanced

### Test C2: New Player Handling
**Objective**: Test composite calculation for players without all-time Elo.

**Setup**:
1. Have a brand new player (no all-time leaderboard Elo) submit a score
2. This should be their first-ever submission

**Expected Results**:
- [ ] All-time Elo defaults to 1000 in calculations
- [ ] Weekly average equals their first weekly Elo
- [ ] Composite = (1000 × 0.5) + (Weekly_Elo × 0.5)

---

## Test Suite D: Error Handling

### Test D1: Invalid Event Name
**Test Steps**:
1. Try: `/admin-weekly-reset event_name:"NonExistentEvent"`

**Expected Results**:
- [ ] Error message: "Event not found" or similar
- [ ] No database changes occur
- [ ] Graceful error handling

### Test D2: Non-Leaderboard Event
**Test Steps**:
1. Try weekly reset on a regular (non-leaderboard) event

**Expected Results**:
- [ ] Error: "Not a valid leaderboard event"
- [ ] Command fails safely

### Test D3: No Weekly Scores
**Test Steps**:
1. Run weekly reset on an event with no weekly scores submitted

**Expected Results**:
- [ ] Error: "No weekly scores found for event X, week Y"
- [ ] Helpful error message indicating the issue

### Test D4: Permission Check
**Test Steps**:
1. Have a non-admin user try the command

**Expected Results**:
- [ ] Permission denied message
- [ ] Command not executed

---

## Test Suite E: Edge Cases

### Test E1: Single Player Event
**Test Steps**:
1. Process an event where only 1 player submitted a score

**Expected Results**:
- [ ] Z-score calculation handles single data point (std_dev = 1.0)
- [ ] Weekly Elo calculated appropriately
- [ ] No mathematical errors (division by zero, etc.)

### Test E2: Identical Scores
**Test Steps**:
1. Have multiple players submit the exact same score
2. Process the week

**Expected Results**:
- [ ] Standard deviation = 0 is handled (defaults to 1.0)
- [ ] All players get same Z-score (0)
- [ ] All players get base Elo (1000)

### Test E3: Large Score Values
**Test Steps**:
1. Submit very large scores (> 1 million)
2. Process the week

**Expected Results**:
- [ ] Mathematical calculations remain stable
- [ ] No overflow or precision issues
- [ ] Reasonable Elo values produced

---

## Test Suite F: Performance & Scale

### Test F1: Many Participants
**Objective**: Test with realistic player counts.

**Setup**:
1. Simulate or arrange for 20+ players to submit scores
2. Process the weekly reset

**Expected Results**:
- [ ] Command completes within reasonable time (< 30 seconds)
- [ ] No timeout errors
- [ ] All players processed correctly
- [ ] Top 5 leaderboard shows correctly

### Test F2: Database Efficiency
**Objective**: Verify no N+1 query issues.

**Test Steps**:
1. Enable database query logging if possible
2. Run weekly processing with 10+ participants
3. Check query count

**Expected Results**:
- [ ] Minimal database queries (should be < 10 total)
- [ ] No repeated individual player lookups
- [ ] Efficient batch operations

---

## Test Suite G: Integration Tests

### Test G1: Autocomplete Functionality
**Test Steps**:
1. Start typing `/admin-weekly-reset event_name:"`
2. Test autocomplete with partial event names
3. Test cluster->event format

**Expected Results**:
- [ ] Only leaderboard events appear in autocomplete
- [ ] Partial matching works correctly
- [ ] Cluster->event format works for disambiguation

### Test G2: Command History
**Test Steps**:
1. Run multiple weekly resets with different reasons
2. Check if admin operations are logged properly

**Expected Results**:
- [ ] Each operation includes reason in logs
- [ ] Proper audit trail maintained
- [ ] No sensitive data in logs

---

## Post-Test Verification

After completing all tests, verify the overall system state:

### Database Integrity Check
```sql
-- Verify all players have consistent data
SELECT player_id, weekly_elo_average, weeks_participated, final_score
FROM player_event_stats 
WHERE event_id = [TEST_EVENT_ID]
ORDER BY final_score DESC;

-- Check for any orphaned or inconsistent records
SELECT COUNT(*) FROM leaderboard_scores WHERE score_type = 'weekly';
-- Should be 0 after processing

SELECT COUNT(*) FROM leaderboard_scores WHERE score_type = 'all_time';
-- Should be > 0 (personal bests remain)
```

### Final System State
- [ ] All weekly scores cleared for next week
- [ ] Player weekly averages updated correctly
- [ ] Composite Elos calculated and stored in final_score
- [ ] Leaderboard rankings reflect new composite scores
- [ ] No database errors or inconsistencies

---

## Known Issues / Limitations

Document any issues found during testing:

1. **Issue**: [Description]
   - **Severity**: Critical/High/Medium/Low
   - **Workaround**: [If any]
   - **Status**: [Needs fix/Acceptable/etc.]

---

## Test Results Summary

| Test Suite | Tests Passed | Tests Failed | Comments |
|------------|--------------|--------------|----------|
| A - Basic  | ___/3        | ___/3        |          |
| B - Inactivity | ___/2    | ___/2        |          |
| C - Composite | ___/2     | ___/2        |          |
| D - Errors | ___/4        | ___/4        |          |
| E - Edge Cases | ___/3     | ___/3        |          |
| F - Performance | ___/2    | ___/2        |          |
| G - Integration | ___/2    | ___/2        |          |
| **TOTAL**  | **___/18**   | **___/18**   |          |

## Final Recommendation

Based on test results:
- [ ] ✅ Ready for production deployment
- [ ] ⚠️ Ready with minor issues noted
- [ ] ❌ Needs fixes before deployment

**Tester**: _______________  
**Date**: _______________  
**Version**: Phase 3.4