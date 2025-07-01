# Phase 2.4.3: Challenge Management Commands - Test Suite

## Overview
This test suite covers the new challenge management commands implemented in Phase 2.4.3:
- `/outgoing-challenges` - View challenges you've created
- `/incoming-challenges` - View pending invitations
- `/active-challenges` - View accepted challenges
- `/cancel-challenge` - Cancel pending challenges

## Prerequisites
1. Bot running with Phase 2.4.3 implementation
2. Database indexes applied (see Migration Instructions below)
3. At least 2 test Discord accounts (User A and User B)
4. Populated clusters and events in database

## Migration Instructions

### Apply Database Changes
```bash
# Make sure you're in the project root directory
cd ~/LB-Tournament-Arc

# Apply the migration
python apply_phase_2_4_3_migration.py

# The script will:
# - Create indexes for optimized queries
# - Add updated_at column to challenges table
# - Verify all changes were applied
```

### Manual Database Verification (Optional)
```bash
# Open SQLite database
sqlite3 tournament.db

# Check indexes
.indexes challenge_participants

# Check table structure
.schema challenges

# Exit SQLite
.quit
```

## Test Environment Setup

```bash
# Ensure bot is running
python -m bot.main

# Verify database has events (optional)
sqlite3 tournament.db "SELECT COUNT(*) FROM events;"

# Check if indexes were created
sqlite3 tournament.db "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';"
```

## Test Scenarios

### 1. Database Index Verification
**Purpose**: Ensure indexes are properly created

**Steps**:
1. Run the migration script: `python apply_phase_2_4_3_migration.py`
2. Check output shows all 4 indexes created
3. Verify no errors during migration

**Expected**: 
- ✅ idx_challenge_participant_lookup
- ✅ idx_challenge_status  
- ✅ idx_cp_pending_challenger
- ✅ idx_cp_pending_challenged
- ✅ updated_at column added

---

### 2. Outgoing Challenges Command
**Purpose**: Test viewing created challenges

**Setup**:
1. User A creates 3 challenges in different states:
   - Challenge 1: To User B (pending)
   - Challenge 2: To User B (have User B accept it)
   - Challenge 3: To User B (have User B decline it)

**Test Steps**:
1. User A runs `/outgoing-challenges`
2. Verify all 3 challenges appear with correct status emojis:
   - ⏳ Pending
   - ✅ Accepted
   - 🚫 Cancelled
3. Verify challenge details show:
   - Event name
   - Participants
   - Your role (Challenger)
   - Time info (expiry/accepted time)

**Expected**: All outgoing challenges visible with accurate status

---

### 3. Incoming Challenges Command
**Purpose**: Test viewing pending invitations

**Setup**:
1. User A creates 2 challenges to User B
2. User B accepts one of them

**Test Steps**:
1. User B runs `/incoming-challenges`
2. Verify only PENDING challenge appears
3. Verify accepted challenge does NOT appear
4. Check that command hint shows "Use /accept to respond"

**Expected**: Only actionable (pending) challenges shown

---

### 4. Active Challenges Command
**Purpose**: Test viewing accepted challenges

**Setup**:
1. Create and accept 2 challenges between users

**Test Steps**:
1. Both users run `/active-challenges`
2. Verify both see the accepted challenges
3. Check hint shows "Use /match_result to report results"
4. Verify ordering (most recent accepts first)

**Expected**: All participants see active challenges

---

### 5. Cancel Challenge - Auto Cancel
**Purpose**: Test auto-cancel of latest pending challenge

**Setup**:
1. User A creates 3 pending challenges (different timestamps)

**Test Steps**:
1. User A runs `/cancel-challenge` (no ID)
2. Verify most recent challenge is cancelled
3. Check other participants receive DM notification
4. Verify challenge status updated to CANCELLED
5. Run `/outgoing-challenges` to confirm status change

**Expected**: Latest pending challenge cancelled automatically

---

### 6. Cancel Challenge - Specific ID
**Purpose**: Test cancelling specific challenge

**Test Steps**:
1. User A creates challenge, note the ID
2. User A runs `/cancel-challenge challenge_id:<id>`
3. Verify correct challenge cancelled
4. Try to cancel already cancelled challenge
5. User B tries to cancel User A's challenge

**Expected**: 
- Correct challenge cancelled
- Error on already cancelled
- Error on permission denied

---

### 7. Pagination Test
**Purpose**: Test pagination for >10 challenges

**Setup**:
1. Create 15 outgoing challenges for User A

**Test Steps**:
1. User A runs `/outgoing-challenges`
2. Verify pagination buttons appear
3. Test "Next ▶" button
4. Test "◀ Previous" button
5. Verify page indicator in footer
6. Wait 5+ minutes for timeout

**Expected**:
- 10 challenges per page
- Navigation works correctly
- Buttons disable at first/last page
- Buttons disable after timeout

---

### 8. Auto-Discovery Edge Cases
**Purpose**: Test accept/decline with multiple pending

**Setup**:
1. User A creates 3 pending challenges to User B

**Test Steps**:
1. User B runs `/accept` (no ID)
2. Verify error message lists challenges
3. Verify command suggests using `/incoming-challenges`
4. User B runs `/accept challenge_id:<id>`
5. Verify correct challenge accepted

**Expected**: Clear guidance when multiple pending challenges exist

---

### 9. DM Notification Test
**Purpose**: Test cancellation notifications

**Test Steps**:
1. User A creates challenge to User B
2. User B disables DMs from non-friends
3. User A cancels the challenge
4. Check bot logs for DM failure

**Expected**: Graceful handling of DM failures

---

### 10. Race Condition Test
**Purpose**: Verify atomic cancel operation

**Setup**:
1. User A creates challenge to User B

**Test Steps**:
1. Have User B prepare to accept
2. User A cancels at nearly same time
3. Only one operation should succeed
4. Check challenge final status

**Expected**: No corrupted state, one operation wins

---

### 11. Admin Notes Test
**Purpose**: Verify admin_notes handling

**Test Steps**:
1. Create challenge with no admin_notes
2. User B declines with reason
3. Check database for admin_notes update
4. Create another challenge
5. User A cancels it
6. Verify cancel note added

**Expected**: Notes properly appended without errors

---

### 12. Error Handling Test
**Purpose**: Test various error conditions

**Test Steps**:
1. Try `/cancel-challenge challenge_id:99999`
2. Run commands with database offline
3. Create challenge to non-existent user ID

**Expected**: User-friendly error messages

---

## Performance Tests

### 13. Query Performance
**Purpose**: Verify indexed queries are fast

**Test Steps**:
1. Create 100 challenges for a user
2. Time `/outgoing-challenges` command
3. Time `/incoming-challenges` command
4. Check database query logs

**Expected**: Commands respond within 2 seconds

---

## Success Criteria
- [ ] All commands respond correctly
- [ ] Pagination works for large result sets
- [ ] Auto-discovery handles edge cases properly
- [ ] Cancel operation is atomic (no race conditions)
- [ ] DM notifications work with graceful failures
- [ ] Performance meets <2 second response time
- [ ] Error messages are clear and helpful

## Known Issues to Watch For
1. **Auto-discovery confusion**: Fixed - now shows error if multiple pending
2. **admin_notes concatenation**: Fixed - handles None values
3. **Local imports**: Working but unconventional

## Notes
- The atomic UPDATE pattern in cancel_challenge prevents race conditions
- Indexes significantly improve query performance
- Pagination prevents Discord embed size limits
- All commands use consistent embed formatting