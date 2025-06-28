# Phase 2.2 Test Suite - Challenge Command Implementation

This test suite validates the hierarchical /challenge command system with autocomplete and N-player support.

## Prerequisites

- Database populated with clusters and events (Phase 1.2 complete)
- Bot running with Phase 2.1.1 role field migration applied
- Discord server with test members available
- Working directory: `/home/jacob/LB-Tournament-Arc`

## Test 1: Service Layer Verification

**Purpose**: Verify ChallengeOperations service is properly initialized

**Steps**:
```bash
# Test that the service imports correctly
python -c "
from bot.operations.challenge_operations import ChallengeOperations, DuplicateChallengeError, InvalidPlayerCountError
print('✅ ChallengeOperations imports successful')
"

# Test modal import
python -c "
from bot.ui.team_formation_modal import TeamFormationModal
print('✅ TeamFormationModal imports successful')
"

# Verify challenge.py imports
python -c "
from bot.cogs.challenge import ChallengeCog
print('✅ ChallengeCog imports successful')
"
```

**Expected Result**: All imports succeed without errors

## Test 2: Database Methods Check

**Purpose**: Verify required database methods exist

**Steps**:
```bash
# Check if database has required methods
python -c "
from bot.database.database import Database
db = Database()

# Check for required methods
methods = ['get_all_clusters', 'get_all_events', 'get_event_by_id']
missing = []
for method in methods:
    if not hasattr(db, method):
        missing.append(method)

if missing:
    print(f'❌ Missing database methods: {missing}')
else:
    print('✅ All required database methods present')
"
```

**Expected Result**: 
- If methods are missing, they need to be implemented
- Otherwise, all methods should be present

## Test 3: Bot Startup with Challenge Command

**Purpose**: Ensure bot starts with new challenge command

**Steps**:
1. Start the bot:
```bash
# Start bot and check for errors
timeout 15 python -m bot.main || true

# Check logs for challenge cog loading
tail -30 logs/tournament_bot_*.log | grep -i "challenge" || echo "No challenge-related entries"
```

2. In Discord, check if `/challenge` command appears in slash command list

**Expected Result**:
- Bot starts without errors
- ChallengeCog loads successfully
- `/challenge` command visible in Discord

## Test 4: Autocomplete Testing

**Purpose**: Test cluster and event autocomplete functionality

**Steps** (in Discord):
1. Type `/challenge cluster:`
   - Should show list of available clusters
   - Type partial name to test filtering

2. Select a cluster, then type `event:`
   - Should show events only from selected cluster
   - Test filtering with partial names

3. Verify match_type shows static choices:
   - 1v1
   - Free for All
   - Team

**Expected Result**:
- Autocomplete shows up to 25 clusters
- Event list filtered by selected cluster
- Match type shows 3 static options

## Test 5: 1v1 Challenge Creation

**Purpose**: Test creating a simple 1v1 challenge

**Steps** (in Discord):
1. Use command: `/challenge cluster:[select] event:[select] match_type:1v1 players:@testuser`

2. Check database for created challenge:
```bash
sqlite3 tournament.db "
SELECT c.id, c.event_id, c.status, COUNT(cp.id) as participants
FROM challenges c
LEFT JOIN challenge_participants cp ON c.id = cp.challenge_id
GROUP BY c.id
ORDER BY c.id DESC
LIMIT 1;
"
```

3. Check participant roles:
```bash
sqlite3 tournament.db "
SELECT cp.role, p.username
FROM challenge_participants cp
JOIN players p ON cp.player_id = p.id
WHERE cp.challenge_id = (SELECT MAX(id) FROM challenges);
"
```

**Expected Result**:
- Challenge created with status 'pending'
- 2 participants (challenger + challenged)
- One participant has role 'challenger', other has 'challenged'

## Test 6: FFA Challenge Creation

**Purpose**: Test creating a Free-for-All challenge with 4 players

**Steps** (in Discord):
1. Use command: `/challenge cluster:[select] event:[select] match_type:ffa players:@user1 @user2 @user3`

2. Verify participant count:
```bash
sqlite3 tournament.db "
SELECT COUNT(*) as participant_count
FROM challenge_participants
WHERE challenge_id = (SELECT MAX(id) FROM challenges);
"
```

**Expected Result**:
- Challenge created successfully
- 4 participants total (including challenger)
- All participants except challenger have 'challenged' role

## Test 7: Team Challenge with Modal

**Purpose**: Test team challenge creation with modal

**Steps** (in Discord):
1. Use command: `/challenge cluster:[select] event:[select] match_type:team players:@user1 @user2 @user3`

2. Modal should appear with team assignment fields

3. Enter team assignments:
   - Team A: 1 2
   - Team B: 3 4

4. Submit modal

5. Check team assignments in database:
```bash
sqlite3 tournament.db "
SELECT cp.team_id, p.username
FROM challenge_participants cp
JOIN players p ON cp.player_id = p.id
WHERE cp.challenge_id = (SELECT MAX(id) FROM challenges)
ORDER BY cp.team_id;
"
```

**Expected Result**:
- Modal appears immediately (no defer)
- Teams assigned correctly in database
- Challenge created with team_id values

## Test 8: Duplicate Challenge Prevention

**Purpose**: Verify duplicate challenges are prevented

**Steps**:
1. Create a challenge with specific players
2. Try to create the same challenge again
3. Should receive "Duplicate Challenge" error

**Expected Result**: Second challenge attempt fails with duplicate error

## Test 9: Invalid Player Count

**Purpose**: Test player count validation

**Steps**:
1. Try 1v1 with 3 players: Should fail
2. Try FFA with 1 player: Should fail
3. Try Team with 9 players: Should fail

**Expected Result**: Each attempt shows appropriate error message

## Test 10: Member Parsing

**Purpose**: Test various member input formats

**Steps** (in Discord):
1. Test with mentions: `@user1 @user2`
2. Test with IDs: `123456789 987654321`
3. Test with names: `JohnDoe JaneDoe`
4. Test with quoted names: `"John Doe" "Jane Doe"`

**Expected Result**: All formats should parse correctly

## Test Summary

Run all tests in order:

- [ ] Test 1: Service imports ✅
- [ ] Test 2: Database methods check ✅
- [ ] Test 3: Bot startup ✅
- [ ] Test 4: Autocomplete functionality ✅
- [ ] Test 5: 1v1 challenge creation ✅
- [ ] Test 6: FFA challenge creation ✅
- [ ] Test 7: Team challenge with modal ✅
- [ ] Test 8: Duplicate prevention ✅
- [ ] Test 9: Player count validation ✅
- [ ] Test 10: Member parsing ✅

## Known Limitations

Based on code review findings:
1. `/accept` command not yet implemented (Phase 2.5)
2. No automatic cleanup for expired challenges
3. Database methods may need implementation if missing

## Next Steps

After all tests pass:
1. Implement missing database methods if needed
2. Phase 2.3: Match type validation (already done via static choices)
3. Phase 2.4: Challenge creation logic (implemented)
4. Phase 2.5: Challenge acceptance system (next phase)