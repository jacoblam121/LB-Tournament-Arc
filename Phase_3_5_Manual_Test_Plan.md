# Phase 3.5 Manual Test Plan - Enhanced Match History System

## Overview
This test plan covers the enhanced match history system with comprehensive pagination and multi-view support. The system provides three new commands: `/match-history-player`, `/match-history-cluster`, and `/match-history-event` with cursor-based pagination and Discord UI components.

## Prerequisites
- Bot is running and connected to Discord
- Database has match and leaderboard data
- Phase 3.5 implementation is deployed
- Test user has appropriate permissions

## Test Environment Setup

### 1. Verify Database State
```sql
-- Check that matches exist with participants
SELECT COUNT(*) as match_count FROM matches WHERE status = 'completed';
SELECT COUNT(*) as participant_count FROM match_participants;

-- Check leaderboard scores exist  
SELECT COUNT(*) as leaderboard_count FROM leaderboard_scores WHERE score_type = 'all_time';

-- Verify test player exists with some history
SELECT p.discord_id, p.display_name, 
       COUNT(DISTINCT mp.match_id) as matches,
       COUNT(DISTINCT ls.id) as leaderboard_scores
FROM players p
LEFT JOIN match_participants mp ON p.id = mp.player_id
LEFT JOIN leaderboard_scores ls ON p.id = ls.player_id
WHERE p.discord_id = YOUR_DISCORD_ID
GROUP BY p.discord_id, p.display_name;

-- Check cluster and event structure
SELECT c.name as cluster_name, e.name as event_name, e.scoring_type
FROM clusters c 
JOIN events e ON c.id = e.cluster_id 
WHERE c.is_active = true
LIMIT 10;
```

### 2. Test Data Preparation
Before testing, ensure you have:
- [ ] At least 5-10 completed matches with different participants
- [ ] At least 3-5 leaderboard score submissions  
- [ ] Multiple clusters with events
- [ ] Test players with varying amounts of history
- [ ] Both 1v1 and multi-player matches (if supported)

## Test Cases

### Test Group 1: Player Match History Command

#### Test 1.1: Basic Player History Display
**Command:** `/match-history-player`
**Expected:** Display current user's match history with default pagination (6 entries)

**Steps:**
1. Run `/match-history-player` 
2. Verify embed shows with title "📜 Match History - [YourName]"
3. Check that entries are displayed in reverse chronological order (newest first)
4. Verify each match entry shows:
   - Result indicator (🟢 win, 🔴 loss, 🟡 draw)
   - Event name
   - Opponent name(s)
   - Elo change (if available)
   - Time ago (e.g., "2h ago", "3d ago")
   - Cluster name
5. Check that leaderboard entries show:
   - 🏆 indicator
   - Event name with "(Leaderboard)" suffix
   - Score value
   - Time ago and cluster name

**Expected Results:**
- [ ] Embed displays properly formatted
- [ ] Entries are in correct chronological order
- [ ] All required fields are present and formatted correctly
- [ ] Mix of matches and leaderboard scores appears correctly

#### Test 1.2: Player History for Another User
**Command:** `/match-history-player player:@TestUser`
**Expected:** Display specified user's match history

**Steps:**
1. Run `/match-history-player player:@TestUser` (replace with actual test user)
2. Verify embed title shows target user's name
3. Confirm entries belong to the specified user
4. Check that private information is not exposed

**Expected Results:**
- [ ] Correct user's history is displayed
- [ ] Title reflects target user
- [ ] No unauthorized data exposure

#### Test 1.3: Player History Pagination
**Command:** `/match-history-player page_size:3`
**Expected:** Test pagination controls with smaller page size

**Steps:**
1. Run command with `page_size:3`
2. Verify only 3 entries are shown
3. Check pagination buttons:
   - Previous button should be disabled initially
   - Next button should be enabled if more than 3 entries exist
4. Click "Next ▶" button
5. Verify new entries load and Previous button becomes enabled
6. Click "◀ Previous" button  
7. Verify return to first page
8. Click "🔄 Refresh" button
9. Verify page refreshes with current data

**Expected Results:**
- [ ] Page size respected (only 3 entries shown)
- [ ] Next button works and loads new entries
- [ ] Previous button works and returns to first page
- [ ] Refresh button works
- [ ] Button states update correctly

#### Test 1.4: Player with No History
**Command:** `/match-history-player player:@NewUser`
**Expected:** Handle user with no match history gracefully

**Steps:**
1. Find or create a user with no matches/leaderboard scores
2. Run command for that user
3. Verify appropriate "No history found" message

**Expected Results:**
- [ ] "No match history found" message displayed
- [ ] No errors or crashes
- [ ] Embed still formatted properly

#### Test 1.5: Large Page Size Limits
**Command:** `/match-history-player page_size:50`
**Expected:** Page size should be clamped to maximum (24)

**Steps:**
1. Run command with page_size greater than 24
2. Verify only maximum entries are shown
3. Check no errors occur

**Expected Results:**
- [ ] Page size clamped to 24 or fewer
- [ ] No performance issues
- [ ] Proper error handling

### Test Group 2: Cluster Match History Command

#### Test 2.1: Basic Cluster History
**Command:** `/match-history-cluster cluster:1`
**Expected:** Display match history for all players in cluster 1

**Steps:**
1. Run `/match-history-cluster cluster:1`
2. Verify embed title shows "📜 Cluster History - [ClusterName]"
3. Check entries include matches from multiple players in the cluster
4. Verify chronological ordering
5. Confirm cluster information is correct

**Expected Results:**
- [ ] Cluster history displays correctly
- [ ] Multiple players' matches included
- [ ] Proper chronological ordering
- [ ] Correct cluster identification

#### Test 2.2: Cluster Search by Name
**Command:** `/match-history-cluster cluster:Tetris`
**Expected:** Find cluster by partial name match

**Steps:**
1. Run command with cluster name instead of number
2. Verify correct cluster is found and displayed
3. Test partial name matching (e.g., if cluster is "Tetris Masters", try "Tetris")

**Expected Results:**
- [ ] Cluster found by name
- [ ] Partial name matching works
- [ ] Correct cluster history displayed

#### Test 2.3: Invalid Cluster
**Command:** `/match-history-cluster cluster:NonExistent`
**Expected:** Handle invalid cluster gracefully

**Steps:**
1. Run command with non-existent cluster name/number
2. Verify appropriate error message
3. Check no crashes occur

**Expected Results:**
- [ ] "Cluster Not Found" error message
- [ ] No crashes or unexpected behavior
- [ ] User-friendly error format

#### Test 2.4: Cluster Pagination
**Command:** `/match-history-cluster cluster:1 page_size:5`
**Expected:** Test pagination with cluster history

**Steps:**
1. Run command with small page size
2. Test pagination buttons as in Test 1.3
3. Verify all functionality works with cluster data

**Expected Results:**
- [ ] Pagination works correctly for cluster history
- [ ] All navigation buttons function
- [ ] Data consistency maintained

### Test Group 3: Event Match History Command

#### Test 3.1: Basic Event History
**Command:** `/match-history-event cluster:1 event:1v1`
**Expected:** Display match history for specific event

**Steps:**
1. Run `/match-history-event cluster:1 event:1v1`
2. Verify embed title shows "📜 Event History - [ClusterName]: [EventName]"
3. Check entries are specific to the event
4. Confirm auto-sorting by cluster if applicable
5. Verify both matches and leaderboard scores for the event

**Expected Results:**
- [ ] Event-specific history displayed
- [ ] Proper title formatting
- [ ] Only relevant event data shown
- [ ] Correct cluster-event combination

#### Test 3.2: Event Search by Partial Name
**Command:** `/match-history-event cluster:Tetris event:sprint`
**Expected:** Find event by partial name within cluster

**Steps:**
1. Use partial cluster and event names
2. Verify correct event is found
3. Check history is specific to that event

**Expected Results:**
- [ ] Partial name matching works for both cluster and event
- [ ] Correct event identified and displayed
- [ ] History specific to the event

#### Test 3.3: Invalid Event/Cluster Combination
**Command:** `/match-history-event cluster:1 event:NonExistent`
**Expected:** Handle invalid event gracefully

**Steps:**
1. Use valid cluster but invalid event name
2. Use invalid cluster name
3. Verify appropriate error messages

**Expected Results:**
- [ ] "Event Not Found" error for invalid event
- [ ] "Cluster Not Found" error for invalid cluster
- [ ] User-friendly error messages

### Test Group 4: Performance and Edge Cases

#### Test 4.1: Large History Dataset
**Expected:** System handles large amounts of data efficiently

**Steps:**
1. Test commands on players/clusters with extensive history (50+ entries)
2. Monitor response times
3. Test pagination through many pages
4. Verify no timeouts or performance issues

**Expected Results:**
- [ ] Reasonable response times (< 5 seconds)
- [ ] Smooth pagination
- [ ] No memory issues
- [ ] Cursor pagination performs well

#### Test 4.2: Mixed Content Types
**Expected:** Matches and leaderboard scores display together correctly

**Steps:**
1. Test on player/cluster/event with both match and leaderboard history
2. Verify proper ordering and formatting
3. Check transitions between different entry types

**Expected Results:**
- [ ] Mixed content displays properly
- [ ] Chronological ordering maintained across types
- [ ] Different formatting for matches vs leaderboard scores

#### Test 4.3: Unicode and Special Characters
**Expected:** Handle special characters in names gracefully

**Steps:**
1. Test with players/clusters/events containing unicode, emoji, or special characters
2. Verify embed formatting remains intact
3. Check for any display issues

**Expected Results:**
- [ ] Unicode characters display correctly
- [ ] No formatting breaks
- [ ] Embed limits respected

#### Test 4.4: Rapid Button Clicking
**Expected:** Handle rapid user interactions gracefully

**Steps:**
1. Rapidly click pagination buttons
2. Click multiple buttons simultaneously
3. Verify no duplicate requests or errors

**Expected Results:**
- [ ] No duplicate API calls
- [ ] Proper error handling
- [ ] UI remains responsive

### Test Group 5: Integration and Error Handling

#### Test 5.1: Database Connection Issues
**Expected:** Graceful degradation when database is unavailable

**Steps:**
1. Simulate database connectivity issues (if possible in test environment)
2. Verify appropriate error messages
3. Check no crashes occur

**Expected Results:**
- [ ] User-friendly error messages
- [ ] No crashes or hangs
- [ ] Proper error logging

#### Test 5.2: Concurrent Usage
**Expected:** System handles multiple users simultaneously

**Steps:**
1. Have multiple test users run commands simultaneously
2. Test different combinations of commands
3. Verify no conflicts or data corruption

**Expected Results:**
- [ ] All users receive correct data
- [ ] No cross-user data leakage
- [ ] Performance remains acceptable

#### Test 5.3: Command Cooldowns
**Expected:** Rate limiting works correctly

**Steps:**
1. Rapidly execute commands within cooldown period
2. Verify cooldown messages appear
3. Wait for cooldown to expire and retry

**Expected Results:**
- [ ] Rate limiting enforced correctly
- [ ] Appropriate cooldown messages
- [ ] Commands work after cooldown expires

## Success Criteria

### Functionality
- [ ] All three commands work as specified
- [ ] Pagination works smoothly with proper navigation
- [ ] Mixed match and leaderboard data displays correctly
- [ ] Search functionality works for clusters and events
- [ ] Error handling is user-friendly and robust

### Performance  
- [ ] Response times under 5 seconds for typical datasets
- [ ] Cursor-based pagination performs efficiently
- [ ] No memory leaks or resource issues
- [ ] Handles concurrent usage appropriately

### User Experience
- [ ] Intuitive command parameters and help text
- [ ] Clear, readable embed formatting  
- [ ] Responsive button interactions
- [ ] Meaningful error messages
- [ ] Proper Discord embed limits handling

### Data Integrity
- [ ] Correct chronological ordering
- [ ] Accurate opponent resolution
- [ ] Proper cluster and event associations
- [ ] No data cross-contamination between users

## Test Data Cleanup

After testing completion:
```sql
-- Optional: Clean up any test data if needed
-- DELETE FROM matches WHERE created_at > 'your_test_start_time';
-- DELETE FROM leaderboard_scores WHERE submitted_at > 'your_test_start_time';
```

## Reporting Issues

For any test failures, please report:
1. Exact command used
2. Expected vs actual behavior  
3. Error messages or stack traces
4. Database state when issue occurred
5. Steps to reproduce

## Implementation Notes

- Commands use cursor-based pagination for O(1) performance
- Discord embed character limits (4096) are enforced with graceful truncation
- Mixed match/leaderboard data uses unified HistoryEntry format
- Opponent resolution uses efficient batch queries to avoid N+1 problems
- All commands include proper rate limiting and error handling