# Phase 2.2 Manual Test Plan: Interactive Profile Command

## Overview
This test plan validates the Phase 2.2 Interactive Profile Command implementation, focusing on the enhanced profile view with navigation buttons, leaderboard integration, and visual polish features.

## Prerequisites
- Discord bot running with Phase 2.2 implementation
- Test server with at least 3-5 registered players
- Players with varying ranks (#1, middle rank, lower rank)
- Test data including cluster stats, match history, and ticket balances

---

## Test Suite 1: Basic Profile Command

### Test 1.1: View Own Profile
**Objective:** Verify `/profile` command displays user's own profile correctly

**Steps:**
1. Run `/profile` command (without member parameter)
2. Verify command defers properly (shows "Bot is thinking...")
3. Check profile embed displays with:
   - Correct username and avatar
   - Core statistics (Final Score, Scoring Elo, Raw Elo, Server Rank)
   - Match history summary (Total, Wins, Losses, Win Rate, Current Streak)
   - Ticket balance
   - Top 3 clusters (if available)
   - Areas for improvement (bottom clusters, if available)

**Expected Results:**
- ✅ Profile loads within 2 seconds
- ✅ All fields populated correctly
- ✅ No error messages
- ✅ Interactive buttons visible

### Test 1.2: View Other Player's Profile  
**Objective:** Verify `/profile @member` displays target player's profile

**Steps:**
1. Run `/profile @[another_player]`
2. Verify target player's information displays
3. Check that it's not your own profile data

**Expected Results:**
- ✅ Target player's data shown
- ✅ Avatar matches target player
- ✅ Navigation buttons still functional

### Test 1.3: View #1 Ranked Player Profile
**Objective:** Verify gold color special treatment for top player

**Steps:**
1. Identify current #1 ranked player
2. Run `/profile @[top_player]` 
3. Check embed color

**Expected Results:**
- ✅ Embed color is gold (not blue)
- ✅ All other functionality works normally

### Test 1.4: Profile for Non-Registered Player
**Objective:** Verify proper error handling for unregistered users

**Steps:**
1. Run `/profile @[unregistered_user]`
2. Check error response

**Expected Results:**
- ✅ Clear "Player Not Found" error message
- ✅ Suggestion to use `/register` 
- ✅ Error is ephemeral (only visible to command user)

---

## Test Suite 2: Interactive Navigation

### Test 2.1: Clusters Overview Button
**Objective:** Verify "Clusters Overview" button navigation

**Steps:**
1. Run `/profile` 
2. Click "Clusters Overview" button
3. Verify clusters display
4. Click "Back to Profile" button

**Expected Results:**
- ✅ Button responds immediately (defers)
- ✅ Clusters embed shows:
  - All clusters with stats
  - Proper ranking numbers (1, 2, 3...)
  - 💀 skull for below-threshold clusters
  - Scoring elo, raw elo, matches, rank
- ✅ "Back to Profile" button visible
- ✅ Back button returns to main profile

### Test 2.2: Match History Button
**Objective:** Verify "Match History" button navigation

**Steps:**
1. Run `/profile`
2. Click "Match History" button  
3. Review match history display
4. Click "Back to Profile" button

**Expected Results:**
- ✅ Match history shows recent matches
- ✅ Each match shows:
  - Result indicator (🟢 win, 🔴 loss, 🟡 draw)
  - Opponent name (may show "Unknown" - acceptable)
  - Event name
  - Elo change (+/- value)
  - Relative timestamp
- ✅ Back navigation works

### Test 2.3: Ticket Ledger Button
**Objective:** Verify "Ticket Ledger" button navigation

**Steps:**
1. Run `/profile`
2. Click "Ticket Ledger" button
3. Check ticket balance display
4. Click "Back to Profile" button

**Expected Results:**
- ✅ Current ticket balance displayed
- ✅ "Detailed transaction history coming soon!" message
- ✅ Back navigation works

### Test 2.4: View on Leaderboard Button ⭐ **NEW FEATURE**
**Objective:** Verify leaderboard navigation integration

**Steps:**
1. Run `/profile` for a player ranked somewhere in middle (not #1)
2. Click "View on Leaderboard" button
3. Verify leaderboard display
4. Check player's position highlighted

**Expected Results:**
- ✅ Leaderboard embed appears (ephemeral)
- ✅ Shows page containing the player's rank
- ✅ Message indicates "Showing leaderboard around rank #X"
- ✅ Leaderboard has proper formatting:
  - Rank, Player, Score, S.Elo, R.Elo columns
  - 💀 skull for players below threshold
  - Page navigation buttons functional
- ✅ Interactive leaderboard view with pagination works

---

## Test Suite 3: Edge Cases & Error Handling

### Test 3.1: Ghost Player Profile
**Objective:** Verify ghost player (left server) handling

**Steps:**
1. Identify a player who has left the server but has data
2. Run `/profile @[ghost_player]` (if possible to reference)
3. Check ghost status display

**Expected Results:**
- ✅ Profile displays with "(Left Server)" in name
- ✅ "This player has left the server but their data is preserved" warning
- ✅ All other data accessible

### Test 3.2: Player with No Cluster Data
**Objective:** Test profile for player with minimal data

**Steps:**
1. Find newly registered player with no match history
2. Run `/profile @[new_player]`
3. Check graceful handling of empty data

**Expected Results:**
- ✅ Profile displays basic info
- ✅ Zero/default values shown appropriately
- ✅ No crashes or error messages
- ✅ Empty sections handled gracefully

### Test 3.3: Very Long Player Names
**Objective:** Test display with long Discord names

**Steps:**
1. Test with player having very long display name
2. Check embed formatting

**Expected Results:**
- ✅ Names truncated appropriately in tables
- ✅ No embed overflow
- ✅ Layout remains readable

### Test 3.4: Rapid Button Clicking
**Objective:** Test interaction rate limiting and stability

**Steps:**
1. Run `/profile`
2. Rapidly click navigation buttons
3. Check for errors or crashes

**Expected Results:**
- ✅ No duplicate responses
- ✅ No error messages
- ✅ System remains stable
- ✅ Rate limiting prevents abuse

---

## Test Suite 4: Performance & User Experience

### Test 4.1: Response Times
**Objective:** Verify acceptable performance

**Steps:**
1. Run `/profile` command multiple times
2. Time response from command execution to embed display
3. Test navigation button response times

**Expected Results:**
- ✅ Initial profile load: < 2 seconds
- ✅ Navigation clicks: < 1 second response
- ✅ Consistent performance across tests

### Test 4.2: Concurrent Usage
**Objective:** Test system under multiple user load

**Steps:**
1. Have multiple users run `/profile` simultaneously
2. Check for performance degradation
3. Verify each user gets correct data

**Expected Results:**
- ✅ No performance degradation
- ✅ Each user sees their own data
- ✅ No data mixing between users

### Test 4.3: Data Freshness
**Objective:** Verify caching doesn't show stale data

**Steps:**
1. Run `/profile` to cache data
2. Have the user play a match (if possible)
3. Run `/profile` again within cache window
4. Wait for cache expiry and test again

**Expected Results:**
- ✅ Recent changes may not appear immediately (caching)
- ✅ Data refreshes after cache expiry
- ✅ Critical data (rank) eventually consistent

---

## Test Suite 5: Integration Testing

### Test 5.1: Leaderboard Integration
**Objective:** Verify profile-to-leaderboard navigation works properly

**Steps:**
1. Run `/profile` for different ranked players
2. Click "View on Leaderboard" for each
3. Verify correct page calculation
4. Test leaderboard pagination from profile view

**Expected Results:**
- ✅ Top ranked player shows first page
- ✅ Middle ranked players show appropriate pages
- ✅ Page calculation correct: rank 23 shows page 3
- ✅ Leaderboard pagination functional

### Test 5.2: Cross-Feature Consistency  
**Objective:** Verify data consistency across features

**Steps:**
1. Run `/profile` and note player's rank
2. Run `/leaderboard` and find same player
3. Compare displayed statistics

**Expected Results:**
- ✅ Rank matches between profile and leaderboard
- ✅ Final score, elos match
- ✅ Player name consistent

---

## Test Completion Checklist

### Core Functionality ✅
- [ ] Basic profile display works
- [ ] Other player profiles work  
- [ ] #1 ranked player shows gold color
- [ ] Error handling for non-registered players

### Interactive Navigation ✅
- [ ] Clusters Overview button and back navigation
- [ ] Match History button and back navigation  
- [ ] Ticket Ledger button and back navigation
- [ ] **NEW:** View on Leaderboard button works

### Edge Cases ✅
- [ ] Ghost player handling
- [ ] Players with minimal data
- [ ] Long player names
- [ ] Rapid button clicking stability

### Performance ✅
- [ ] Response times under 2 seconds
- [ ] Concurrent usage stable
- [ ] Data caching working

### Integration ✅
- [ ] Leaderboard navigation integration
- [ ] Data consistency across features

---

## Bug Report Template

When reporting issues, include:

**Bug Description:**
[Brief description of the issue]

**Steps to Reproduce:**
1. [Step 1]
2. [Step 2] 
3. [Result]

**Expected Behavior:**
[What should happen]

**Actual Behavior:**  
[What actually happened]

**Environment:**
- Player tested: [username/ID]
- Player rank: [#X of Y total]
- Timestamp: [when test was run]
- Any error messages: [exact text]

**Screenshots:**
[Attach Discord screenshots if applicable]

---

## Test Results Summary

After completing all tests, summarize results:

- **Tests Passed:** __ / __
- **Tests Failed:** __ / __  
- **Critical Issues:** [List]
- **Minor Issues:** [List]
- **Ready for Production:** ✅ / ❌

## Notes
- All tests should be performed by different users when possible
- Test with various permission levels if applicable
- Document any unexpected behaviors for future improvements
- Pay special attention to the new "View on Leaderboard" functionality