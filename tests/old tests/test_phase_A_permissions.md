# Phase A Permission System Test Suite

## Overview
This test suite validates the match result permission system implementation that restricts match reporting to only match participants or admin.

## Test Environment Setup

### Prerequisites
1. Discord bot running with Phase A implementation
2. Test server with configured `OWNER_DISCORD_ID`
3. At least 3 test users:
   - **Admin**: User with ID matching `OWNER_DISCORD_ID`
   - **Participant**: User participating in test matches
   - **Outsider**: User NOT participating in test matches
4. Pre-created test matches (use `!ffa` command)

### Test Data Preparation
```bash
# Create test matches for validation
!ffa @participant1 @participant2 @participant3
# Note the returned Match ID (e.g., Match ID: 42)

!ffa @participant1 @participant2 @participant3 @participant4 @participant5
# Note Match ID for ≤5 player modal tests

!ffa @p1 @p2 @p3 @p4 @p5 @p6 @p7
# Note Match ID for 6-8 player enhanced guidance tests
```

## Test Cases

### 1. Permission Validation - Basic Access Control

#### Test 1.1: Participant Can Report (Prefix Command)
**Objective**: Verify match participants can report results using prefix commands
**Steps**:
1. As **Participant**: `!match-report 42 @participant1:1 @participant2:2 @participant3:3`
**Expected**: ✅ Success - Results recorded successfully
**Validates**: Basic participant permission works for prefix commands

#### Test 1.2: Participant Can Report (Slash Command)
**Objective**: Verify match participants can report results using slash commands  
**Steps**:
1. As **Participant**: `/match-report match_id:42 placements:@participant1:1 @participant2:2 @participant3:3`
**Expected**: ✅ Success - Results recorded successfully
**Validates**: Basic participant permission works for slash commands

#### Test 1.3: Admin Can Report
**Objective**: Verify admin can report results for any match
**Steps**:
1. As **Admin**: `!match-report 42 @participant1:1 @participant2:2 @participant3:3`
**Expected**: ✅ Success - Results recorded successfully  
**Validates**: Admin override functionality works

#### Test 1.4: Outsider Cannot Report (Prefix)
**Objective**: Verify non-participants cannot report results via prefix commands
**Steps**:
1. As **Outsider**: `!match-report 42 @participant1:1 @participant2:2 @participant3:3`
**Expected**: ❌ Error - "Only match participants or admin can report results"
**Validates**: Permission blocking works for prefix commands

#### Test 1.5: Outsider Cannot Report (Slash)
**Objective**: Verify non-participants cannot report results via slash commands
**Steps**:
1. As **Outsider**: `/match-report match_id:42 placements:@participant1:1 @participant2:2 @participant3:3`
**Expected**: ❌ Error - "Only match participants or admin can report results"
**Validates**: Permission blocking works for slash commands

### 2. Modal Permission Validation (≤5 Players)

#### Test 2.1: Modal Display Permission Check
**Objective**: Verify only authorized users get modal for ≤5 player matches
**Steps**:
1. As **Outsider**: `/match-report match_id:[5-player-match-id]` (no placements parameter)
**Expected**: ❌ Error - Permission denied before modal appears
**Validates**: Modal path respects permission checks

#### Test 2.2: Modal Submission Permission Check (CRITICAL)
**Objective**: Verify modal submission validates permissions at submission time
**Steps**:
1. As **Participant**: `/match-report match_id:[5-player-match-id]` (triggers modal)
2. Fill out modal with valid placements
3. Submit modal
**Expected**: ✅ Success - Results recorded
**Validates**: Modal submission accepts authorized users

**⚠️ CRITICAL TEST**: 
If implementation has the modal permission bypass vulnerability identified in code review:
1. Somehow obtain/access a modal instance for a match you're not in
2. Submit the modal
**Current Expected Behavior**: ❌ BUG - Results would be accepted (vulnerability)
**Fixed Expected Behavior**: ❌ Error - Permission validation on submission

### 3. Enhanced Guidance Permission Validation (6-8 Players)

#### Test 3.1: Enhanced Guidance Permission Check
**Objective**: Verify 6-8 player guidance respects permissions
**Steps**:
1. As **Outsider**: `/match-report match_id:[7-player-match-id]` (no placements)
**Expected**: ❌ Error - Permission denied before guidance appears
**Validates**: Enhanced guidance path respects permission checks

#### Test 3.2: Guidance Template Generation
**Objective**: Verify authorized users get helpful guidance for 6-8 players
**Steps**:
1. As **Participant**: `/match-report match_id:[7-player-match-id]` (no placements)
**Expected**: ✅ Guidance embed with copy-paste template
**Validates**: Enhanced guidance works for authorized users

### 4. Edge Cases & Error Handling

#### Test 4.1: Invalid Match ID
**Objective**: Verify permission system handles non-existent matches gracefully
**Steps**:
1. As **Participant**: `!match-report 99999 @someone:1`
**Expected**: ❌ Error - "Match 99999 could not be found"
**Validates**: Permission system doesn't crash on invalid matches

#### Test 4.2: Completed Match Protection
**Objective**: Verify permission system respects match status
**Steps**:
1. Complete a match first: `!match-report [match-id] @p1:1 @p2:2 @p3:3`
2. As **Participant**: Try to report again: `!match-report [same-match-id] @p1:2 @p2:1 @p3:3`
**Expected**: ❌ Error - "Match already completed or cancelled"
**Validates**: Status validation works alongside permissions

#### Test 4.3: Permission Error Message Quality
**Objective**: Verify error messages are helpful and informative
**Steps**:
1. As **Outsider**: `/match-report match_id:42 placements:@someone:1`
2. Read the error message carefully
**Expected**: Clear message explaining who can report + helpful context
**Validates**: User experience for permission denials

### 5. Integration & Performance Tests

#### Test 5.1: Database Query Optimization
**Objective**: Monitor for redundant database queries (code review found double-loading)
**Steps**:
1. Enable database query logging if possible
2. As **Participant**: `/match-report match_id:42` (no placements, triggers modal path)
3. Check logs for duplicate match queries
**Expected**: Minimal necessary queries (ideally single match load)
**Validates**: Performance optimization (if fixed)

#### Test 5.2: Hybrid Command Compatibility
**Objective**: Verify permissions work consistently across command types
**Steps**:
1. Test same scenario with prefix: `!match-report 42 @p1:1 @p2:2`
2. Test same scenario with slash: `/match-report match_id:42 placements:@p1:1 @p2:2`
**Expected**: Identical permission behavior for both
**Validates**: Hybrid command integration

## Test Results Template

### Test Execution Record
```
Date: _________
Tester: _________
Bot Version: Phase A

Test 1.1 - Participant Prefix: [PASS/FAIL] ___________
Test 1.2 - Participant Slash: [PASS/FAIL] ___________
Test 1.3 - Admin Override: [PASS/FAIL] ___________
Test 1.4 - Outsider Prefix Block: [PASS/FAIL] ___________
Test 1.5 - Outsider Slash Block: [PASS/FAIL] ___________
Test 2.1 - Modal Permission: [PASS/FAIL] ___________
Test 2.2 - Modal Submission: [PASS/FAIL] ___________
Test 3.1 - Guidance Permission: [PASS/FAIL] ___________
Test 3.2 - Guidance Template: [PASS/FAIL] ___________
Test 4.1 - Invalid Match: [PASS/FAIL] ___________
Test 4.2 - Completed Match: [PASS/FAIL] ___________
Test 4.3 - Error Messages: [PASS/FAIL] ___________
Test 5.1 - DB Optimization: [PASS/FAIL] ___________
Test 5.2 - Hybrid Compatibility: [PASS/FAIL] ___________

Critical Issues Found: ___________
Performance Issues: ___________
UX Issues: ___________
```

## Expected Critical Issue

⚠️ **KNOWN VULNERABILITY**: Test 2.2 Modal Submission may reveal the permission bypass vulnerability identified in code review. The modal submission handler (`PlacementModal.on_submit()`) lacks permission validation, potentially allowing unauthorized result submission.

## Next Steps After Testing

1. **If tests reveal the modal vulnerability**: Implement the fix suggested in code review
2. **If double-query performance issue observed**: Refactor to single match load
3. **If all tests pass**: Proceed to Phase B (Database infrastructure for confirmation system)

## Success Criteria

- ✅ All permission blocks work correctly (Tests 1.4, 1.5, 2.1, 3.1)
- ✅ All authorized access works (Tests 1.1, 1.2, 1.3, 2.2, 3.2)  
- ✅ Error handling is robust (Tests 4.1, 4.2, 4.3)
- ✅ No critical security vulnerabilities in production
- ✅ Performance is acceptable with minimal redundant queries