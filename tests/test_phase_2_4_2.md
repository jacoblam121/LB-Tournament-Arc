# Test Suite: Phase 2.4.2 - Challenge Acceptance Workflow

## Overview

This test suite validates the implementation of Phase 2.4.2: Challenge Acceptance Workflow, which adds `/accept` and `/decline` slash commands to complete the challenge system. The implementation allows participants to respond to challenge invitations and automatically transitions to Match creation when all participants accept.

## Implementation Components Tested

- **bot/operations/challenge_operations.py**: Enhanced with accept/decline logic and auto-transition
- **bot/cogs/challenge.py**: Added `/accept` and `/decline` slash commands  
- **bot/cogs/housekeeping.py**: New background cleanup task for expired challenges
- **planB.md**: Updated with implementation completion notes

## Test Prerequisites

1. **Database Setup**: Ensure tournament.db has populated cluster/event data
2. **Bot Running**: Discord bot must be active and connected
3. **Test Users**: At least 2 Discord users for challenge testing
4. **Permissions**: Test users should have command access

## Test Environment Setup

```bash
# Ensure bot is running
python -m bot.main

# Verify database has events (optional)
sqlite3 tournament.db "SELECT COUNT(*) FROM events;"
```

## Test Categories

### Category 1: Basic Accept/Decline Commands

#### Test 1.1: Accept Command Auto-Discovery
**Objective**: Verify `/accept` auto-detects pending challenges when no ID provided

**Steps**:
1. User A creates a 1v1 challenge: `/challenge cluster:IO_Games event:Diep match_type:1v1 players:@UserB`
2. Note the Challenge ID from the embed response
3. User B runs `/accept` (without challenge_id parameter)
4. Verify the command auto-detects the pending challenge

**Expected Results**:
- ✅ User B receives challenge status update embed
- ✅ Challenge shows "1/2 participants accepted" 
- ✅ User A's status shows ✅ (confirmed)
- ✅ User B's status shows ✅ (confirmed)

#### Test 1.2: Accept Command with Explicit ID
**Objective**: Verify `/accept` works with explicit challenge_id parameter

**Steps**:
1. User A creates a FFA challenge: `/challenge cluster:IO_Games event:Diep match_type:ffa players:@UserB @UserC`
2. Note the Challenge ID from the embed response  
3. User B runs `/accept challenge_id:123` (use actual challenge ID)
4. User C runs `/accept challenge_id:123`

**Expected Results**:
- ✅ After User B accepts: "2/3 participants accepted" status
- ✅ After User C accepts: "Match Ready!" embed appears
- ✅ Match record created with all 3 participants
- ✅ Challenge status changes to COMPLETED

#### Test 1.3: Decline Command with Reason
**Objective**: Verify `/decline` cancels challenge and records reason

**Steps**:
1. User A creates a team challenge: `/challenge cluster:IO_Games event:Diep match_type:team players:@UserB @UserC @UserD`
2. Complete team formation modal (assign teams)
3. User B runs `/decline reason:Can't play today`
4. Verify challenge cancellation

**Expected Results**:
- ✅ "Challenge Cancelled" embed appears
- ✅ Shows User B declined with reason "Can't play today"
- ✅ Challenge status changes to CANCELLED
- ✅ All other participants notified of cancellation

#### Test 1.4: Decline Command without Reason
**Objective**: Verify `/decline` works without optional reason parameter

**Steps**:
1. User A creates a 1v1 challenge: `/challenge cluster:IO_Games event:Diep match_type:1v1 players:@UserB`
2. User B runs `/decline` (no reason parameter)
3. Verify challenge cancellation

**Expected Results**:
- ✅ "Challenge Cancelled" embed appears
- ✅ Shows User B declined (no reason shown)
- ✅ Challenge status changes to CANCELLED

### Category 2: Auto-Transition to Match Creation

#### Test 2.1: 1v1 Auto-Transition
**Objective**: Verify 1v1 challenge auto-creates Match when both players accept

**Steps**:
1. User A creates 1v1 challenge: `/challenge cluster:IO_Games event:Diep match_type:1v1 players:@UserB`
2. User B runs `/accept`
3. Verify Match creation

**Expected Results**:
- ✅ "Match Ready!" embed appears after User B accepts
- ✅ Match ID is provided (e.g., "Match #456 created")
- ✅ Match format shows "ONE_V_ONE" 
- ✅ Match scoring_type shows "1v1"
- ✅ Both participants listed in Match
- ✅ Challenge status is COMPLETED

#### Test 2.2: FFA Auto-Transition  
**Objective**: Verify FFA challenge auto-creates Match when all players accept

**Steps**:
1. User A creates FFA challenge: `/challenge cluster:IO_Games event:Diep match_type:ffa players:@UserB @UserC @UserD`
2. User B runs `/accept`
3. User C runs `/accept`
4. User D runs `/accept`
5. Verify Match creation after final accept

**Expected Results**:
- ✅ "Match Ready!" embed appears after User D accepts
- ✅ Match format shows "FFA"
- ✅ Match scoring_type shows "FFA"
- ✅ All 4 participants listed in Match
- ✅ Next steps mention "/match_result" command

#### Test 2.3: Team Auto-Transition
**Objective**: Verify team challenge auto-creates Match with team assignments preserved

**Steps**:
1. User A creates team challenge: `/challenge cluster:IO_Games event:Diep match_type:team players:@UserB @UserC @UserD`
2. Complete team modal: Assign User A, User B to Team A; User C, User D to Team B
3. All users accept: User B `/accept`, User C `/accept`, User D `/accept`
4. Verify Match creation with teams

**Expected Results**:
- ✅ "Match Ready!" embed shows team assignments
- ✅ Match format shows "TEAM"
- ✅ Match scoring_type shows "Team"  
- ✅ MatchParticipant records preserve team_id values
- ✅ Embed shows participants with team labels (e.g., "Team A", "Team B")

### Category 3: Error Handling and Edge Cases

#### Test 3.1: Accept Non-Existent Challenge
**Objective**: Verify proper error handling for invalid challenge IDs

**Steps**:
1. User A runs `/accept challenge_id:99999` (non-existent ID)
2. Verify error response

**Expected Results**:
- ✅ Error embed: "Challenge not found or expired"
- ✅ Response is ephemeral (only visible to User A)

#### Test 3.2: Accept Already Responded Challenge
**Objective**: Verify users cannot accept/decline twice

**Steps**:
1. User A creates 1v1 challenge with User B
2. User B runs `/accept`
3. User B runs `/accept` again
4. Verify error response

**Expected Results**:
- ✅ Error embed: "You have already confirmed this challenge"
- ✅ Response is ephemeral

#### Test 3.3: Non-Participant Acceptance
**Objective**: Verify only invited users can accept challenges

**Steps**:
1. User A creates 1v1 challenge with User B
2. User C (not invited) runs `/accept challenge_id:123`
3. Verify error response

**Expected Results**:
- ✅ Error embed: "You are not invited to this challenge"
- ✅ Response is ephemeral

#### Test 3.4: Accept Cancelled Challenge
**Objective**: Verify users cannot accept cancelled challenges

**Steps**:
1. User A creates 1v1 challenge with User B
2. User B runs `/decline`
3. User A tries `/accept challenge_id:123`
4. Verify error response

**Expected Results**:
- ✅ Error embed: "Challenge is cancelled, cannot accept"
- ✅ Response is ephemeral

#### Test 3.5: No Pending Challenges Auto-Discovery
**Objective**: Verify helpful message when user has no pending challenges

**Steps**:
1. Ensure User A has no pending challenges
2. User A runs `/accept` (no challenge_id parameter)
3. Verify helpful response

**Expected Results**:
- ✅ Error embed: "No Pending Challenges"
- ✅ Message suggests using `/challenge` to create new challenges
- ✅ Response is ephemeral

### Category 4: Background Cleanup System

#### Test 4.1: Manual Cleanup Command
**Objective**: Verify owner can manually trigger challenge cleanup

**Steps**:
1. Create expired challenge (modify database or wait for expiration)
2. Bot owner runs `!cleanup_challenges`
3. Verify cleanup execution

**Expected Results**:
- ✅ Response: "✅ Cleaned up X expired challenges"
- ✅ Expired challenges marked as EXPIRED status
- ✅ Command only accessible to bot owner

#### Test 4.2: Automatic Cleanup Task
**Objective**: Verify hourly background cleanup task runs

**Steps**:
1. Create challenge and manually set expires_at to past time in database:
   ```sql
   UPDATE challenges SET expires_at = datetime('now', '-2 hours') WHERE id = 123;
   ```
2. Wait for next hour boundary OR restart bot to trigger immediate run
3. Check logs for cleanup activity

**Expected Results**:
- ✅ Log message: "Cleaned up X expired challenges"
- ✅ Background task runs automatically every hour
- ✅ No errors in task execution

#### Test 4.3: Cleanup Task Error Handling
**Objective**: Verify cleanup task handles errors gracefully

**Steps**:
1. Monitor bot logs during normal operation
2. Verify task continues despite any errors

**Expected Results**:
- ✅ Task doesn't crash bot if database errors occur
- ✅ Errors logged but task continues running
- ✅ Task restarts properly after bot restart

### Category 5: Database Integration

#### Test 5.1: Match Record Accuracy
**Objective**: Verify Match records are created correctly from Challenges

**Steps**:
1. Create and complete various challenge types (1v1, FFA, Team)
2. Query database to verify Match records:
   ```sql
   SELECT m.*, mp.* FROM matches m 
   JOIN match_participants mp ON m.id = mp.match_id 
   WHERE m.challenge_id = 123;
   ```

**Expected Results**:
- ✅ Match.challenge_id correctly links to original Challenge
- ✅ Match.match_format matches challenge type
- ✅ Match.scoring_type correct ("1v1", "FFA", "Team")
- ✅ MatchParticipant records for all participants
- ✅ Team assignments preserved in MatchParticipant.team_id

#### Test 5.2: Challenge Status Transitions
**Objective**: Verify Challenge status updates correctly throughout workflow

**Steps**:
1. Create challenge and monitor status field
2. Track status through accept/decline workflow
3. Query database at each step

**Expected Results**:
- ✅ Initial status: PENDING
- ✅ After partial accepts: Still PENDING
- ✅ After all accepts: COMPLETED
- ✅ After any decline: CANCELLED
- ✅ After expiration: EXPIRED

#### Test 5.3: Participant Status Tracking
**Objective**: Verify ChallengeParticipant status updates correctly

**Steps**:
1. Create multi-participant challenge
2. Have participants accept/decline in sequence
3. Monitor ChallengeParticipant.status field

**Expected Results**:
- ✅ Initial status: PENDING for all participants
- ✅ After accept: CONFIRMED for that participant
- ✅ After decline: REJECTED for that participant
- ✅ responded_at timestamp updated when status changes

## Troubleshooting Common Issues

### Issue: Commands not appearing
**Solution**: Sync slash commands: `!sync` or restart bot

### Issue: Auto-discovery not working
**Check**: User has exactly one pending challenge, not zero or multiple

### Issue: Match not created
**Check**: All participants accepted (check Challenge status)

### Issue: Database errors
**Check**: Ensure foreign key constraints are satisfied

### Issue: Background task not running
**Check**: Bot has been running for at least 1 hour, check logs

## Success Criteria Summary

Phase 2.4.2 implementation is successful when:

- ✅ `/accept` command works with auto-discovery and explicit IDs
- ✅ `/decline` command cancels challenges with optional reasons
- ✅ Auto-transition creates Match records when all participants accept
- ✅ Error handling prevents invalid operations with helpful messages
- ✅ Background cleanup maintains database health
- ✅ All database relationships maintained correctly
- ✅ Real-time Discord embeds provide clear status updates

## Test Completion Report

After running all tests, complete this checklist:

- [ ] Category 1: Basic Accept/Decline Commands (4 tests)
- [ ] Category 2: Auto-Transition to Match Creation (3 tests) 
- [ ] Category 3: Error Handling and Edge Cases (5 tests)
- [ ] Category 4: Background Cleanup System (3 tests)
- [ ] Category 5: Database Integration (3 tests)

**Total Tests**: 18
**Tests Passed**: ___/18
**Tests Failed**: ___/18

## Notes Section

Use this space to record any issues encountered during testing:

```
Test Issues Found:
- 
- 
- 

Suggestions for Improvement:
-
-
-
```