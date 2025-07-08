# Phase 2.3 Implementation Coordination - Manual Test Plan

## Overview
This test plan validates the Phase 2.3 Implementation Coordination features, focusing on the CTE pattern consistency, shared ranking utility, and enhanced leaderboard functionality.

## Pre-Test Setup

### Prerequisites
1. Bot is running with Phase 2.3 changes deployed
2. Database contains test players with varied stats
3. Multiple clusters and events exist in the database
4. At least 10+ players for meaningful leaderboard testing

### Critical Bug Fixes COMPLETED ✅
✅ **FIXED**: All critical bugs in RankingUtility have been resolved:
- **CRITICAL**: Eliminated duplicate player rows in cluster/event leaderboards through proper aggregation
- **HIGH**: Fixed sort parameter being ignored - now honors user's sort selection
- **HIGH**: Resolved column name conflicts between Player and PlayerEventStats tables

**PRIORITY TESTING**: Focus on cluster/event leaderboards to validate these fixes work correctly.

## Test Categories

### 🔧 1. Core Functionality Tests

#### Test 1.1: Basic Leaderboard Command
**Objective**: Verify `/leaderboard` command works in LeaderboardCog

**Steps**:
1. Run `/leaderboard` command
2. Verify leaderboard displays correctly
3. Check pagination buttons work
4. Verify sorting dropdown functions

**Expected Results**:
- Leaderboard displays players ranked by final score
- Pagination works (Previous/Next buttons)
- Sort dropdown allows changing sort criteria
- No errors in console

**Pass/Fail**: [ ]

#### Test 1.2: Leaderboard Types (CRITICAL FIX VALIDATION)
**Objective**: Test overall, cluster, and event leaderboards - PRIORITY TEST for bug fixes

**Steps**:
1. Run `/leaderboard type:overall`
2. Run `/leaderboard type:cluster` (use autocomplete)
3. Run `/leaderboard type:event` (use autocomplete)
4. **CRITICAL**: Verify NO duplicate players appear in cluster/event leaderboards
5. **CRITICAL**: Verify player counts are accurate (not inflated by duplicates)
6. Verify each shows appropriate data

**Expected Results**:
- Overall shows global rankings
- Cluster shows cluster-specific rankings with ONE entry per player ✅
- Event shows event-specific rankings with ONE entry per player ✅
- Accurate total player counts (not inflated) ✅
- Autocomplete works for cluster/event names

**Pass/Fail**: [ ]

#### Test 1.3: Sorting Options (CRITICAL FIX VALIDATION)
**Objective**: Verify all sorting options work correctly - PRIORITY TEST for sort fix

**Steps**:
1. Test each sort option for **CLUSTER** leaderboards:
   - `/leaderboard type:cluster cluster:[name] sort:final_score`
   - `/leaderboard type:cluster cluster:[name] sort:scoring_elo`
   - `/leaderboard type:cluster cluster:[name] sort:raw_elo`
   - `/leaderboard type:cluster cluster:[name] sort:shard_bonus`
   - `/leaderboard type:cluster cluster:[name] sort:shop_bonus`
2. Test each sort option for **EVENT** leaderboards:
   - `/leaderboard type:event event:[name] sort:final_score`
   - `/leaderboard type:event event:[name] sort:scoring_elo`
   - `/leaderboard type:event event:[name] sort:raw_elo`
3. **CRITICAL**: Verify rankings actually change when sort parameter changes ✅

**Expected Results**:
- Each sort displays players in correct order FOR THAT SORT TYPE ✅
- Rankings change appropriately when sort parameter changes ✅
- Crown emoji (👑) appears for #1 player
- Skull emoji (💀) appears for players with raw_elo < 1000

**Pass/Fail**: [ ]

### 🎛️ 2. Interactive Features Tests

#### Test 2.1: Pagination Navigation
**Objective**: Test leaderboard pagination thoroughly

**Steps**:
1. Navigate to page 2 using "Next" button
2. Navigate back to page 1 using "Previous" button
3. Test pagination with different page sizes (if applicable)
4. Verify page indicator updates correctly

**Expected Results**:
- Navigation works smoothly
- Page numbers update correctly
- Previous button disabled on page 1
- Next button disabled on last page

**Pass/Fail**: [ ]

#### Test 2.2: Sort Dropdown Interaction
**Objective**: Test dynamic sorting through UI

**Steps**:
1. Open leaderboard with default sort
2. Use sort dropdown to change to "Raw Elo"
3. Use sort dropdown to change to "Scoring Elo"
4. Verify each change updates the ranking

**Expected Results**:
- Dropdown shows current sort selection
- Rankings update when sort changes
- Page resets to 1 when sort changes

**Pass/Fail**: [ ]

#### Test 2.3: Autocomplete Functionality
**Objective**: Test cluster and event autocomplete

**Steps**:
1. Type `/leaderboard type:cluster cluster:` and test autocomplete
2. Type `/leaderboard type:event event:` and test autocomplete
3. Type partial names and verify filtering works

**Expected Results**:
- Autocomplete shows available clusters/events
- Typing filters the suggestions
- Maximum 25 suggestions shown (Discord limit)

**Pass/Fail**: [ ]

### 🔄 3. Coordination & Consistency Tests

#### Test 3.1: CTE Pattern Consistency
**Objective**: Verify ProfileService and LeaderboardService show consistent rankings

**Steps**:
1. Note a player's rank from `/leaderboard`
2. Run `/profile` for the same player
3. Compare the server rank shown in profile vs leaderboard
4. Test with multiple players

**Expected Results**:
- Profile service shows same rank as leaderboard service
- No discrepancies in ranking between services
- Both use the same CTE pattern internally

**Pass/Fail**: [ ]

#### Test 3.2: Shared Ranking Utility
**Objective**: Verify RankingUtility is working across services

**Steps**:
1. Check console logs for ranking queries
2. Verify no "old ranking pattern" queries appear
3. Test edge cases (ghost players, new players)

**Expected Results**:
- All ranking queries use CTE pattern
- Consistent handling of edge cases
- No fallback to old ranking methods

**Pass/Fail**: [ ]

#### Test 3.3: Architectural Organization
**Objective**: Verify proper command organization

**Steps**:
1. Verify `/leaderboard` command is NOT in PlayerCog
2. Verify `/leaderboard` command IS in LeaderboardCog
3. Test legacy `!ranks` command for information
4. Verify `/profile` still works correctly

**Expected Results**:
- `/leaderboard` only accessible through LeaderboardCog
- No duplicate commands between cogs
- Legacy commands provide migration guidance
- Profile command unaffected by leaderboard move

**Pass/Fail**: [ ]

### 🚀 4. Performance & Reliability Tests

#### Test 4.1: Response Time Performance
**Objective**: Verify acceptable response times

**Steps**:
1. Time `/leaderboard` response (should be < 3 seconds)
2. Time cluster-specific leaderboard response
3. Time event-specific leaderboard response
4. Test with different page numbers

**Expected Results**:
- All responses under 3 seconds
- Caching improves subsequent requests
- No timeouts or Discord interaction failures

**Response Times**:
- Overall leaderboard: _____ seconds
- Cluster leaderboard: _____ seconds  
- Event leaderboard: _____ seconds

**Pass/Fail**: [ ]

#### Test 4.2: Caching Behavior
**Objective**: Verify caching improves performance

**Steps**:
1. Run same leaderboard query twice rapidly
2. Verify second request is faster (cached)
3. Wait 3+ minutes, test cache expiration
4. Check cache cleanup works

**Expected Results**:
- Second identical request much faster
- Cache expires after TTL period
- Memory usage remains reasonable

**Pass/Fail**: [ ]

#### Test 4.3: Error Handling
**Objective**: Test error scenarios

**Steps**:
1. Test invalid cluster name: `/leaderboard type:cluster cluster:invalid`
2. Test invalid event name: `/leaderboard type:event event:invalid`
3. Test invalid sort parameter (if possible)
4. Test with no permissions (if applicable)

**Expected Results**:
- Clear error messages for invalid inputs
- No crashes or stack traces visible to users
- Graceful degradation for edge cases

**Pass/Fail**: [ ]

### 🎯 5. Edge Cases & Ghost Players

#### Test 5.1: Ghost Player Handling
**Objective**: Test players who left the server

**Steps**:
1. Find a ghost player in the database
2. Verify they appear in leaderboards with "(Left Server)" tag
3. Test filtering ghost players (if option exists)
4. Check profile view of ghost player

**Expected Results**:
- Ghost players show "(Left Server)" in name
- Ranking still accurate including ghosts
- No crashes when viewing ghost profiles

**Pass/Fail**: [ ]

#### Test 5.2: Empty Results
**Objective**: Test scenarios with no data

**Steps**:
1. Test cluster leaderboard with no players
2. Test event leaderboard with no participants
3. Test pagination on very small datasets

**Expected Results**:
- Appropriate "empty" messages shown
- No pagination controls when unnecessary
- No crashes on empty results

**Pass/Fail**: [ ]

#### Test 5.3: Large Dataset Behavior
**Objective**: Test with maximum expected data

**Steps**:
1. Test leaderboard with full server (if possible)
2. Navigate to final pages of leaderboard
3. Test search/filter with large datasets

**Expected Results**:
- Performance remains acceptable
- Pagination works correctly
- No memory issues or timeouts

**Pass/Fail**: [ ]

## 🔍 6. Regression Tests

#### Test 6.1: Profile Command Integration
**Objective**: Ensure profile features still work

**Steps**:
1. Test `/profile` command for various users
2. Verify "View on Leaderboard" button works
3. Test profile navigation buttons
4. Check profile data accuracy

**Expected Results**:
- Profile command works without errors
- All profile navigation functions
- Data matches leaderboard data

**Pass/Fail**: [ ]

#### Test 6.2: Other Command Compatibility
**Objective**: Verify other bot functions unaffected

**Steps**:
1. Test other major bot commands
2. Verify database operations work
3. Check match reporting (if applicable)

**Expected Results**:
- No regressions in other functionality
- Database remains consistent
- All services operate normally

**Pass/Fail**: [ ]

## Test Results Summary

### Overall Test Status
- **Total Tests**: 18
- **Passed**: ___
- **Failed**: ___
- **Not Applicable**: ___

### Critical Issues Found
List any critical issues that need immediate attention:

1. ________________________________
2. ________________________________
3. ________________________________

### Performance Notes
Record any performance observations:

- Average response time: _____ seconds
- Cache hit rate: _____%
- Memory usage: Normal/High/Concerning

### Recommendations
Based on testing, list recommendations for production deployment:

1. ________________________________
2. ________________________________
3. ________________________________

## Sign-off

**Tested by**: ________________  
**Date**: ________________  
**Environment**: Dev/Staging/Production  
**Bot Version**: Phase 2.3 Implementation Coordination  

**Ready for Production**: Yes/No/With Fixes

**Additional Notes**:
________________________________________________
________________________________________________
________________________________________________