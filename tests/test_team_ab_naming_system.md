# Team A/B Naming System Test Suite

This test suite validates that the team challenge system correctly displays "Team A" and "Team B" instead of "Team 0" and "Team 1" in all user-facing interfaces.

## Prerequisites

- Database populated with clusters and events (Phase 1.2 complete)
- Bot running with Phase 2.2 challenge command implementation
- Discord server with at least 4 test members available for team challenges
- Working directory: `/home/jacob/LB-Tournament-Arc`

## Test Overview

**Key Finding**: Team A/B functionality is already implemented in the code. These tests verify it works correctly and identify any gaps.

## Test 1: Code Verification - Team Mapping Logic

**Purpose**: Verify the Team A/B mapping logic exists in the codebase

**Steps**:
```bash
# Check that team mapping logic is present in challenge.py
grep -n -A 5 "team_letter_map" bot/cogs/challenge.py

# Check TeamFormationModal shows correct labels
grep -n -A 3 '"Team A", "Team B"' bot/ui/team_formation_modal.py

# Verify team assignment storage format
grep -n 'f"Team_{team_id}"' bot/ui/team_formation_modal.py
```

**Expected Results**:
- [ ] `team_letter_map = {"Team_0": "A", "Team_1": "B"}` found in challenge.py
- [ ] `team_labels = ["Team A", "Team B"]` found in team_formation_modal.py  
- [ ] Team assignments stored as `"Team_0"` and `"Team_1"` format
- [ ] No references to "Team 0" or "Team 1" in display logic

## Test 2: Team Formation Modal UI

**Purpose**: Verify the team formation modal shows "Team A" and "Team B" labels

**Steps**:
1. Start the bot: `python -m bot.main`
2. In Discord, run a team challenge command:
   ```
   /challenge cluster:IO Games event:Diep match_type:team players:@member1 @member2 @member3
   ```
3. Observe the modal that appears
4. Check the field labels in the modal

**Expected Results**:
- [ ] Modal appears with title "Team Formation"
- [ ] Field 1 labeled: "Team A Members"
- [ ] Field 2 labeled: "Team B Members"  
- [ ] Participant reference shows numbered list of players
- [ ] No references to "Team 0" or "Team 1" in modal interface

## Test 3: Team Assignment Functionality

**Purpose**: Test that team assignments work correctly through the modal

**Steps**:
1. Continue from Test 2 with the open modal
2. In "Team A Members" field, enter: `1 2`
3. In "Team B Members" field, enter: `3`
4. Submit the modal
5. Observe the resulting challenge embed

**Expected Results**:
- [ ] Modal submission succeeds without errors
- [ ] Challenge embed appears in Discord
- [ ] Embed shows "Team A" as a field name (not "Team 0")
- [ ] Embed shows "Team B" as a field name (not "Team 1")
- [ ] Players are correctly assigned to their respective teams
- [ ] Team A shows members 1 and 2 from the participant list
- [ ] Team B shows member 3 from the participant list

## Test 4: Database Storage Verification

**Purpose**: Verify team assignments are stored correctly in the database

**Steps**:
```bash
# After completing Test 3, check the database
sqlite3 tournament.db "
SELECT cp.team_id, p.username 
FROM challenge_participants cp 
JOIN players p ON cp.player_id = p.id 
WHERE cp.challenge_id = (SELECT MAX(id) FROM challenges)
ORDER BY cp.team_id, p.username;
"
```

**Expected Results**:
- [ ] Query returns results without errors
- [ ] Team assignments stored as "Team_0" and "Team_1" (internal format)
- [ ] Players correctly assigned to their respective teams
- [ ] No null team_id values for team challenge participants

## Test 5: Edge Case - Uneven Team Assignment

**Purpose**: Test team assignment with uneven team sizes

**Steps**:
1. Create another team challenge with 5 players:
   ```
   /challenge cluster:IO Games event:Bonk match_type:team players:@member1 @member2 @member3 @member4 @member5
   ```
2. Assign teams unevenly in the modal:
   - Team A: `1 2 3`
   - Team B: `4 5`
3. Submit and observe the result

**Expected Results**:
- [ ] Modal accepts uneven team assignment
- [ ] Challenge embed shows "Team A" with 3 members
- [ ] Challenge embed shows "Team B" with 2 members
- [ ] All 5 players are accounted for
- [ ] No "Team 0" or "Team 1" references in display

## Test 6: Error Case - Missing Player Assignment

**Purpose**: Test validation when players are not assigned to teams

**Steps**:
1. Create a team challenge with 4 players
2. In the modal, only assign some players:
   - Team A: `1 2`
   - Team B: (leave empty)
3. Submit the modal

**Expected Results**:
- [ ] Modal submission fails with validation error
- [ ] Error message mentions unassigned players
- [ ] Error message lists missing players by number and name
- [ ] User can retry with correct assignments

## Test 7: Error Case - Duplicate Assignment

**Purpose**: Test validation when a player is assigned to multiple teams

**Steps**:
1. Create a team challenge with 4 players
2. In the modal, assign player 1 to both teams:
   - Team A: `1 2`
   - Team B: `1 3`
3. Submit the modal

**Expected Results**:
- [ ] Modal submission fails with validation error
- [ ] Error message indicates specific player assigned to multiple teams
- [ ] Error message shows player's display name
- [ ] User can retry with correct assignments

## Test 8: Architecture Assessment - N-Team vs 2-Team

**Purpose**: Evaluate if the current N-team architecture is over-engineered

**Analysis Questions**:
1. Does the code unnecessarily support more than 2 teams?
2. Would a simpler 2-team-only architecture be cleaner?
3. Are there places where generic team handling adds complexity?

**Code Review Points**:
```bash
# Check for hardcoded team count
grep -n "team_count = 2" bot/ui/team_formation_modal.py

# Check for N-team flexibility that's unused
grep -n -A 3 -B 3 "replace.*_.*title" bot/cogs/challenge.py

# Look for team validation logic
grep -n -A 5 "len(team_sizes)" bot/ui/team_formation_modal.py
```

**Assessment Results**:
- [ ] Team count is hardcoded to 2 (no real N-team support)
- [ ] Generic fallback `team_id.replace("_", " ").title()` exists but unused
- [ ] Validation requires exactly 2 teams
- [ ] Architecture could be simplified to direct Team A/B handling

## Test 9: Alternative Architecture Proposal

**Purpose**: Document how the system could be simplified for 2-team only

**Current Architecture**:
- Modal creates: `{"player_id": "Team_0"}`, `{"player_id": "Team_1"}`
- Storage: `team_id = "Team_0"` or `"Team_1"`  
- Display: Maps `"Team_0" → "Team A"`, `"Team_1" → "Team B"`

**Simplified Architecture Proposal**:
- Modal creates: `{"player_id": "Team_A"}`, `{"player_id": "Team_B"}`
- Storage: `team_id = "Team_A"` or `"Team_B"`
- Display: Direct usage, no mapping needed

**Benefits of Simplification**:
- [ ] Removes mapping layer complexity
- [ ] More direct and readable code
- [ ] Eliminates internal vs display naming inconsistency
- [ ] Easier to maintain and understand

## Test 10: Performance and Scalability

**Purpose**: Verify team system performs well with maximum players

**Steps**:
1. Create team challenge with 8 players (maximum)
2. Assign teams through modal interface
3. Observe response times and any issues

**Expected Results**:
- [ ] Modal loads quickly with 8 players
- [ ] Team assignment completes without delays
- [ ] Challenge embed renders all teams clearly
- [ ] No performance degradation with maximum players

## Summary Checklist

After completing all tests:

**Functionality Verification**:
- [ ] Team A/B display works correctly in all interfaces
- [ ] No "Team 0" or "Team 1" references in user-facing text
- [ ] Team assignment validation works properly
- [ ] Database storage is consistent and correct

**Architecture Assessment**:
- [ ] Current system works but may be over-engineered
- [ ] Simplification opportunity identified
- [ ] Performance is acceptable
- [ ] Code quality is good overall

**Recommendation**:
Based on test results, choose one of:
1. **Keep Current**: System works correctly, only needed testing verification
2. **Simplify Architecture**: Implement direct Team A/B storage for cleaner code

## Notes

- If all tests pass, the Team A/B functionality is working correctly
- If any tests fail, specific bugs need to be addressed
- Architecture simplification is optional based on maintainability preferences
- Focus should be on verification rather than reimplementation