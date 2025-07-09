# Phase 3.2 Score Submission System - Manual Test Plan

## Scope
This test plan covers **Phase 3.2 only** - the basic score submission system:
- `/submit-score` command functionality
- Personal best tracking (all-time scores)
- Weekly score logging (storage only, no processing)
- Input validation and error handling
- Database integration

**Not included** (later phases):
- Phase 3.3: Z-score statistical conversion and Elo calculations
- Phase 3.4: Weekly processing and reset functionality
- Phase 3.5: Admin commands for leaderboard management

## Test Environment Setup

### Prerequisites
1. Discord bot is running and connected to test server
2. Database has been migrated with running statistics fields
3. At least one event with `score_direction` configured (HIGH or LOW)
4. Test user has access to the Discord server

### Test Data Setup
Run these SQL commands to create test events:

```sql
-- Create a HIGH score event (higher is better)
INSERT INTO events (name, cluster_id, score_direction, is_active)
VALUES ('Tetris High Score', 1, 'HIGH', true);

-- Create a LOW score event (lower is better)  
INSERT INTO events (name, cluster_id, score_direction, is_active)
VALUES ('100m Sprint Time', 1, 'LOW', true);
```

## Test Cases

### Test Suite A: Basic Score Submission Functionality

#### Test A1: First Score Submission (HIGH direction)
**Objective**: Verify basic score submission works for HIGH direction events

**Steps**:
1. In Discord, type `/submit-score`
2. Select "Tetris High Score" from event autocomplete
3. Enter score: `1500`
4. Submit command

**Expected Result**:
- ✅ Command executes successfully
- ✅ Response shows "🎉 New Personal Best! **1500** points"
- ✅ No "Previous Best" field shown (first submission)
- ✅ Event field shows "Tetris High Score"

**Notes**: _____________________

#### Test A2: Score Improvement (HIGH direction)
**Objective**: Verify personal best improvement works

**Steps**:
1. Use `/submit-score` with "Tetris High Score"
2. Enter score: `2000` (higher than previous 1500)
3. Submit command

**Expected Result**:
- ✅ Response shows "🎉 New Personal Best! **2000** points"
- ✅ Previous Best field shows "1500 points"
- ✅ Improvement field shows "+500 points"

**Notes**: _____________________

#### Test A3: Score Not Improvement (HIGH direction)
**Objective**: Verify non-improvement submissions are handled correctly

**Steps**:
1. Use `/submit-score` with "Tetris High Score"
2. Enter score: `1800` (lower than current best 2000)
3. Submit command

**Expected Result**:
- ✅ Response shows "Score Submitted **1800** points"
- ✅ Personal Best field shows "2000 points"
- ✅ No "New Personal Best" celebration

**Notes**: _____________________

#### Test A4: First Score Submission (LOW direction)
**Objective**: Verify basic score submission works for LOW direction events

**Steps**:
1. Use `/submit-score` with "100m Sprint Time"
2. Enter score: `12.5`
3. Submit command

**Expected Result**:
- ✅ Response shows "🎉 New Personal Best! **12.5** points"
- ✅ No "Previous Best" field shown

**Notes**: _____________________

#### Test A5: Score Improvement (LOW direction)
**Objective**: Verify personal best improvement works for LOW direction

**Steps**:
1. Use `/submit-score` with "100m Sprint Time"
2. Enter score: `11.8` (lower/better than previous 12.5)
3. Submit command

**Expected Result**:
- ✅ Response shows "🎉 New Personal Best! **11.8** points"
- ✅ Previous Best field shows "12.5 points"
- ✅ Improvement field shows "+0.7 points" (improvement calculation)

**Notes**: _____________________

### Test Suite B: Input Validation

#### Test B1: Invalid Score Range (Too Low)
**Steps**:
1. Use `/submit-score` with any event
2. Enter score: `0`
3. Submit command

**Expected Result**:
- ✅ Error message: "❌ Score must be between 0 and 1,000,000,000!"
- ✅ Message is ephemeral (only you can see it)

**Notes**: _____________________

#### Test B2: Invalid Score Range (Too High)
**Steps**:
1. Use `/submit-score` with any event
2. Enter score: `1000000001`
3. Submit command

**Expected Result**:
- ✅ Error message: "❌ Score must be between 0 and 1,000,000,000!"
- ✅ Message is ephemeral

**Notes**: _____________________

#### Test B3: Invalid Score Value (NaN)
**Steps**:
1. Use `/submit-score` with any event
2. Enter score: `inf` (if Discord allows) or any invalid value
3. Submit command

**Expected Result**:
- ✅ Error message: "❌ Invalid score value!"
- ✅ Message is ephemeral

**Notes**: _____________________

### Test Suite C: Event Validation

#### Test C1: Non-existent Event
**Steps**:
1. Use `/submit-score`
2. Type "NonExistentEvent" for event name
3. Enter any valid score
4. Submit command

**Expected Result**:
- ✅ Error message: "❌ Event not found!"
- ✅ Message is ephemeral

**Notes**: _____________________

#### Test C2: Event Without Score Direction
**Steps**:
1. Create a regular event without score_direction in database
2. Use `/submit-score` with that event
3. Enter any valid score
4. Submit command

**Expected Result**:
- ✅ Error message: "❌ This event is not configured for score submissions!"
- ✅ Message is ephemeral

**Notes**: _____________________

### Test Suite D: Rate Limiting

#### Test D1: Rate Limit Enforcement
**Steps**:
1. Use `/submit-score` with any event and score
2. Immediately use `/submit-score` again (within 60 seconds)
3. Submit command

**Expected Result**:
- ✅ Rate limit error message appears
- ✅ User must wait before submitting again

**Notes**: _____________________

### Test Suite E: Autocomplete Functionality

#### Test E1: Event Autocomplete
**Steps**:
1. Type `/submit-score` and focus on event field
2. Type "Tetris" (partial match)
3. Observe autocomplete suggestions

**Expected Result**:
- ✅ "Tetris High Score" appears in suggestions
- ✅ Only events with score_direction are shown
- ✅ Maximum 25 suggestions displayed

**Notes**: _____________________

### Test Suite F: Database Integration

#### Test F1: Running Statistics Update (Phase 3.2 Basic)
**Steps**:
1. Submit multiple scores for the same event from different players
2. Check database for running statistics updates

**Database Query**:
```sql
SELECT name, score_count, score_mean, score_m2 
FROM events 
WHERE name = 'Tetris High Score';
```

**Expected Result**:
- ✅ `score_count` increments with each new player (if implemented)
- ✅ `score_mean` updates appropriately (if implemented)
- ✅ `score_m2` updates for variance calculation (if implemented)

**Note**: Full statistical processing is part of Phase 3.3. Phase 3.2 may have basic implementation.

**Notes**: _____________________

#### Test F2: Personal Best Storage
**Steps**:
1. Submit several scores for same player/event
2. Check database for personal best records

**Database Query**:
```sql
SELECT player_id, event_id, score, score_type, submitted_at
FROM leaderboard_scores 
WHERE score_type = 'all_time'
ORDER BY submitted_at DESC;
```

**Expected Result**:
- ✅ Only one record per player/event for all_time scores
- ✅ Score reflects the best submission
- ✅ `submitted_at` updates with each improvement

**Notes**: _____________________

#### Test F3: Weekly Score Tracking (Phase 3.2 Only)
**Steps**:
1. Submit scores for same event
2. Check database for weekly score records

**Database Query**:
```sql
SELECT player_id, event_id, score, score_type, week_number, submitted_at
FROM leaderboard_scores 
WHERE score_type = 'weekly'
ORDER BY submitted_at DESC;
```

**Expected Result**:
- ✅ Every submission creates a weekly record
- ✅ `week_number` is populated correctly
- ✅ Multiple weekly records per player/event allowed

**Note**: Weekly processing/reset functionality is part of Phase 3.4 and not tested here

**Notes**: _____________________

### Test Suite G: Error Handling

#### Test G1: Database Connection Issues
**Steps**:
1. Temporarily stop database service
2. Use `/submit-score` with any valid inputs
3. Submit command

**Expected Result**:
- ✅ Generic error message displayed
- ✅ Detailed error logged in bot logs
- ✅ User doesn't see internal error details

**Notes**: _____________________

#### Test G2: Concurrent Submissions
**Steps**:
1. Have multiple users submit scores simultaneously
2. Check for data consistency issues

**Expected Result**:
- ✅ All submissions processed correctly
- ✅ No duplicate personal best records
- ✅ Running statistics remain consistent

**Notes**: _____________________

## Test Results Summary

### Test Suite A (Basic Functionality)
- [ ] A1: First Score Submission (HIGH) - ✅ PASS / ❌ FAIL
- [ ] A2: Score Improvement (HIGH) - ✅ PASS / ❌ FAIL
- [ ] A3: Score Not Improvement (HIGH) - ✅ PASS / ❌ FAIL
- [ ] A4: First Score Submission (LOW) - ✅ PASS / ❌ FAIL
- [ ] A5: Score Improvement (LOW) - ✅ PASS / ❌ FAIL

### Test Suite B (Input Validation)
- [ ] B1: Invalid Score Range (Too Low) - ✅ PASS / ❌ FAIL
- [ ] B2: Invalid Score Range (Too High) - ✅ PASS / ❌ FAIL
- [ ] B3: Invalid Score Value (NaN) - ✅ PASS / ❌ FAIL

### Test Suite C (Event Validation)
- [ ] C1: Non-existent Event - ✅ PASS / ❌ FAIL
- [ ] C2: Event Without Score Direction - ✅ PASS / ❌ FAIL

### Test Suite D (Rate Limiting)
- [ ] D1: Rate Limit Enforcement - ✅ PASS / ❌ FAIL

### Test Suite E (Autocomplete)
- [ ] E1: Event Autocomplete - ✅ PASS / ❌ FAIL

### Test Suite F (Database Integration)
- [ ] F1: Running Statistics Update - ✅ PASS / ❌ FAIL
- [ ] F2: Personal Best Storage - ✅ PASS / ❌ FAIL
- [ ] F3: Weekly Score Tracking - ✅ PASS / ❌ FAIL

### Test Suite G (Error Handling)
- [ ] G1: Database Connection Issues - ✅ PASS / ❌ FAIL
- [ ] G2: Concurrent Submissions - ✅ PASS / ❌ FAIL

## Known Issues to Monitor

Based on code review, watch for these issues during testing:

1. **Database Compatibility**: May fail if using PostgreSQL due to SQLite-specific migration
2. **Transaction Issues**: New players might be created even if score submission fails
3. **Statistics Accuracy**: Running statistics may be incorrect for score replacements
4. **Guild Security**: Users might see events from other servers (if testing in multi-server setup)

## Testing Environment Notes

**Database**: _____________  
**Bot Version**: _____________  
**Test Server**: _____________  
**Test Date**: _____________  
**Tester**: _____________  

## Issues Found During Testing

Document any issues discovered during testing:

1. **Issue**: ________________
   **Steps to Reproduce**: ________________
   **Expected**: ________________
   **Actual**: ________________
   **Severity**: ________________

2. **Issue**: ________________
   **Steps to Reproduce**: ________________
   **Expected**: ________________
   **Actual**: ________________
   **Severity**: ________________

## Overall Assessment

- [ ] **Ready for Production**: All tests pass, no critical issues
- [ ] **Needs Minor Fixes**: Some non-critical issues found
- [ ] **Needs Major Fixes**: Critical issues prevent production deployment
- [ ] **Implementation Incomplete**: Core functionality missing or broken