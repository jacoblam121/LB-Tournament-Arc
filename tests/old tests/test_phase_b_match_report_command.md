# Phase B: Match-Report Command Test Suite

## Overview
This test suite validates the match-report command with the new confirmation workflow integrated in Phase B.

## Prerequisites
1. Bot running with Phase B changes implemented
2. At least 4 Discord test accounts (3 players + 1 non-participant)
3. One admin account (configured in bot settings)
4. Database with Phase B migration applied

## Test Setup
Before running tests, ensure you have:
- Test users ready (we'll call them Alice, Bob, Charlie, Dave)
- Alice is configured as admin (OWNER_DISCORD_ID in .env)
- Dave is a non-participant for permission tests

## Test Cases

### Test 1: Basic Confirmation Flow (3 Players)
**Purpose:** Verify the standard confirmation workflow where all participants confirm

**Steps:**
1. Create an FFA match:
   ```
   !ffa @Alice @Bob @Charlie
   ```
   Note the Match ID (e.g., 101)

2. Alice reports results:
   ```
   /match-report match_id:101
   ```
   - If ≤5 players: Modal appears, fill in placements (Alice:1, Bob:2, Charlie:3)
   - If text command: `/match-report match_id:101 placements:@Alice:1 @Bob:2 @Charlie:3`

3. Verify initial state:
   - Alice should see: "✅ Alice (Proposer)" in confirmation status
   - Bob and Charlie should see: "⏳ Bob" and "⏳ Charlie"
   - Match status shows "Awaiting Confirmation"

4. Bob clicks Confirm button
   - Status updates to show "✅ Bob"

5. Charlie clicks Confirm button
   - Match completes automatically
   - Embed changes to green "✅ Match Results Confirmed!"
   - Shows final standings with Elo changes

**Expected Results:**
- Proposal created with Alice auto-confirmed
- Each confirmation updates the embed
- Match completes when all confirm
- Elo ratings updated in database

**SQL Verification:**
```sql
-- Check match status
SELECT id, status FROM matches WHERE id = 101;
-- Expected: status = 'completed'

-- Check confirmations
SELECT player_id, status FROM match_confirmations WHERE match_id = 101;
-- Expected: 3 rows, all with status = 'confirmed'
```

### Test 2: Rejection Flow
**Purpose:** Verify proposal termination when someone rejects

**Steps:**
1. Create another FFA match:
   ```
   !ffa @Alice @Bob @Charlie
   ```
   Note the Match ID (e.g., 102)

2. Alice reports results:
   ```
   /match-report match_id:102 placements:@Alice:1 @Bob:3 @Charlie:2
   ```

3. Bob clicks Reject button
   - Embed changes to red "❌ Match Proposal Rejected"
   - Shows "Rejected By: Bob"
   - No reason field shown
   - Match status reset to Pending

4. Try to click buttons again:
   - Buttons should be disabled
   - Message: "This proposal is no longer active"

5. Re-report with correct results:
   ```
   /match-report match_id:102 placements:@Alice:1 @Bob:2 @Charlie:3
   ```
   - New proposal created successfully

**Expected Results:**
- Rejection terminates proposal immediately
- Match resets to PENDING status
- Can create new proposal after rejection
- No reason field displayed

**SQL Verification:**
```sql
-- Check match is pending again
SELECT status FROM matches WHERE id = 102;
-- Expected: status = 'pending'

-- Check old proposal is inactive
SELECT is_active FROM match_result_proposals WHERE match_id = 102;
-- Expected: First row has is_active = 0
```

### Test 3: Admin Force - Modal Path (≤5 Players)
**Purpose:** Verify admin force=true works with modal

**Steps:**
1. Create a small match:
   ```
   !ffa @Alice @Bob @Charlie
   ```
   Note the Match ID (e.g., 103)

2. Alice (admin) reports with force:
   ```
   /match-report match_id:103 force:True
   ```

3. Fill modal with placements and submit

**Expected Results:**
- Match completes immediately
- No confirmation buttons shown
- Embed shows "✅ Match Results Recorded! (Admin Override)"
- Elo ratings updated instantly

**SQL Verification:**
```sql
-- Check immediate completion
SELECT status FROM matches WHERE id = 103;
-- Expected: status = 'completed'

-- No confirmations created
SELECT COUNT(*) FROM match_confirmations WHERE match_id = 103;
-- Expected: 0
```

### Test 4: Admin Force - String Path (6+ Players)
**Purpose:** Verify admin force=true works with string parsing

**Steps:**
1. Create a larger match:
   ```
   !ffa @Alice @Bob @Charlie @Dave @Eve @Frank
   ```
   Note the Match ID (e.g., 104)

2. Alice (admin) reports with force:
   ```
   /match-report match_id:104 placements:@Alice:1 @Bob:2 @Charlie:3 @Dave:4 @Eve:5 @Frank:6 force:True
   ```

**Expected Results:**
- Match completes immediately
- Shows "(Admin Override)" in title
- No confirmation workflow initiated

### Test 5: Permission Validation
**Purpose:** Verify only participants can report/confirm

**Steps:**
1. Create match without Dave:
   ```
   !ffa @Alice @Bob @Charlie
   ```
   Note the Match ID (e.g., 105)

2. Dave (non-participant) tries to report:
   ```
   /match-report match_id:105 placements:@Alice:1 @Bob:2 @Charlie:3
   ```
   - Should see error: "You don't have permission to report this match"

3. Alice reports results properly:
   ```
   /match-report match_id:105 placements:@Alice:1 @Bob:2 @Charlie:3
   ```

4. Dave tries to click Confirm button:
   - Should see: "Only match participants can confirm results"

**Expected Results:**
- Non-participants cannot report matches
- Non-participants cannot interact with confirmation buttons
- Clear error messages for permission failures

### Test 6: Edge Cases

#### 6a. Duplicate Confirmation Attempt
1. In an active proposal, Bob clicks Confirm
2. Bob clicks Confirm again
   - Should see: "You have already confirmed the match results"

#### 6b. Proposer Tries to Confirm
1. Alice (proposer) clicks Confirm
   - Should see: "You have already confirmed the match results"

#### 6c. Expired Proposal (Simulated)
1. Create a match and proposal
2. Wait 24 hours (or modify database to simulate)
3. Try to click buttons
   - Should see: "This proposal has expired"

**SQL to simulate expiration:**
```sql
UPDATE match_result_proposals 
SET expires_at = datetime('now', '-1 hour')
WHERE match_id = 106;
```

## Expected Test Summary

All tests should pass with the following results:

✅ Test 1: Basic Confirmation Flow - All participants confirm successfully
✅ Test 2: Rejection Flow - Proposal terminated, match reset to pending
✅ Test 3: Admin Force Modal - Immediate completion for ≤5 players
✅ Test 4: Admin Force String - Immediate completion for 6+ players
✅ Test 5: Permission Validation - Non-participants properly restricted
✅ Test 6: Edge Cases - Duplicate attempts handled, expiration works

## Troubleshooting

### Common Issues

1. **"Already responded" Error**
   - Check if user already has a confirmation record
   - Verify the embed shows correct status

2. **Force Not Working**
   - Ensure user is configured as admin
   - Check both modal and string paths

3. **Buttons Not Appearing**
   - Verify proposal created successfully
   - Check bot has permission to add components

4. **SQL Queries Return Empty**
   - Ensure using correct match IDs
   - Database might be using different schema

## Next Steps

After all tests pass:
1. Run datetime.utcnow() replacement fix
2. Add JSON validation for proposal data
3. Consider implementing background task for expired proposal cleanup