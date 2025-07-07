# Phase 2.1.1 Manual Test Plan
## Slash Command Foundation Testing

### Prerequisites
- Bot is running with Phase 2.1.1 implementation
- Test server has some registered players with data
- Test user has appropriate permissions

### Test Cases

#### TC-001: Basic Profile Command
**Objective**: Test `/profile` command basic functionality
**Steps**:
1. Run `/profile` (without parameters)
2. Verify profile embed displays with:
   - Tournament Profile title
   - Core Statistics section (Final Score, Scoring Elo, Raw Elo, Server Rank)
   - Match History section (Total Matches, Wins/Losses/Draws, Win Rate)
   - Economy section (Tickets)
   - Navigation buttons appear below embed

**Expected Results**:
- Profile loads within 2 seconds
- All stats display correctly
- Buttons are functional and respond to clicks
- No error messages appear

#### TC-002: Profile Command with Target User
**Objective**: Test viewing another player's profile
**Steps**:
1. Run `/profile member:@target_user`
2. Verify target user's profile displays
3. Confirm ghost status if user has left server

**Expected Results**:
- Target user's profile loads correctly
- "(Left Server)" appears if user is ghost
- Warning message shows for ghost users

#### TC-003: Profile Interactive Navigation
**Objective**: Test profile navigation buttons
**Steps**:
1. Open a profile with `/profile`
2. Click "Clusters Overview" button
3. Verify cluster view displays
4. Click "Back to Profile" button
5. Try "Match History" and "Ticket Ledger" buttons

**Expected Results**:
- Each view loads without errors
- Back button returns to main profile
- Views show appropriate data or placeholder messages

#### TC-004: Basic Leaderboard Command
**Objective**: Test `/leaderboard` command default behavior
**Steps**:
1. Run `/leaderboard` (default parameters)
2. Verify leaderboard displays with:
   - Overall Leaderboard title
   - Sorted by Final Score
   - Table format with ranks, players, scores
   - Navigation buttons and sort dropdown

**Expected Results**:
- Leaderboard loads within 2 seconds
- Players ranked correctly by Final Score
- Table formatting is readable
- Pagination controls appear

#### TC-005: Leaderboard Sorting
**Objective**: Test leaderboard sort functionality
**Steps**:
1. Open `/leaderboard`
2. Use sort dropdown to select "Scoring Elo"
3. Verify rankings update
4. Try other sort options (Raw Elo, Shard Bonus, Shop Bonus)

**Expected Results**:
- Sort dropdown responds to selection
- Rankings update correctly for each sort type
- Page resets to 1 when sorting changes

#### TC-006: Leaderboard Pagination
**Objective**: Test leaderboard page navigation
**Steps**:
1. Open `/leaderboard` on server with >10 players
2. Click "Next" button
3. Verify page 2 displays
4. Click "Previous" button
5. Verify page 1 returns

**Expected Results**:
- Next/Previous buttons work correctly
- Page indicator updates
- Buttons disable appropriately at boundaries

#### TC-007: Cluster/Event Autocomplete
**Objective**: Test autocomplete functionality
**Steps**:
1. Type `/leaderboard cluster:` and start typing
2. Verify cluster suggestions appear
3. Select a cluster and verify
4. Try `/leaderboard event:` with typing

**Expected Results**:
- Autocomplete suggestions appear as typing
- Suggestions filter based on input
- Selection works correctly

#### TC-008: Error Handling - Unregistered Player
**Objective**: Test profile command for unregistered user
**Steps**:
1. Run `/profile member:@unregistered_user`
2. Verify appropriate error message

**Expected Results**:
- "Player Not Found" error displays
- Suggests using `/register` to get started
- Error is ephemeral (only visible to user)

#### TC-009: Error Handling - Empty Leaderboard
**Objective**: Test leaderboard with no data
**Steps**:
1. Run `/leaderboard` with filter that returns no results
2. Verify empty state handling

**Expected Results**:
- "The leaderboard is empty" message displays
- No table shows
- Navigation buttons are appropriately disabled

#### TC-010: Rate Limiting
**Objective**: Test rate limiting functionality
**Steps**:
1. Run `/profile` command rapidly (>3 times in 30 seconds)
2. Verify rate limit message appears
3. Wait and verify command works again

**Expected Results**:
- Rate limit message displays after limit exceeded
- Error is ephemeral
- Command becomes available after cooldown

#### TC-011: Ghost Player Handling
**Objective**: Test handling of players who left server
**Steps**:
1. View profile of player who left server
2. Verify ghost status indicators
3. Check that data is preserved

**Expected Results**:
- Profile shows "(Left Server)" in name
- Warning about ghost status appears
- Historical data remains accessible

### Performance Tests

#### PT-001: Profile Load Time
**Objective**: Verify profile loads efficiently
**Steps**:
1. Time `/profile` command execution
2. Record load time for 10 different profiles

**Expected Results**:
- Average load time < 2 seconds
- No timeouts or Discord interaction errors

#### PT-002: Leaderboard Load Time
**Objective**: Verify leaderboard loads efficiently
**Steps**:
1. Time `/leaderboard` command execution
2. Test with different sort options

**Expected Results**:
- Average load time < 2 seconds
- Sorting changes load quickly

### Integration Tests

#### IT-001: Cross-Command Integration
**Objective**: Test interactions between commands
**Steps**:
1. Use `/profile` to view a player
2. Click "View on Leaderboard" button (when implemented)
3. Navigate between different views

**Expected Results**:
- Navigation between commands works smoothly
- Data consistency across views

### Regression Tests

#### RT-001: Legacy Command Compatibility
**Objective**: Verify legacy commands still work
**Steps**:
1. Test `!register` command
2. Verify it still creates players correctly
3. Check that it suggests new slash commands

**Expected Results**:
- Legacy registration works
- User is directed to use `/profile` and `/leaderboard`

### Test Data Requirements

- At least 5 registered players with match history
- Players with varying scores and rankings
- Some players with no matches (edge case)
- At least one player who has left the server (ghost)
- Multiple clusters and events with data

### Known Issues/Limitations

1. Match history shows "Unknown" opponents (planned improvement)
2. Ticket ledger shows placeholder content (planned improvement)
3. Cluster dropdown in profile view shows placeholder (planned improvement)

### Test Environment Setup

1. Ensure bot has latest Phase 2.1.1 code deployed
2. Verify database contains test data
3. Test in server with appropriate permissions
4. Have both admin and regular user accounts for testing

### Success Criteria

- All test cases pass without critical errors
- Performance meets specified thresholds
- User experience is smooth and intuitive
- Error handling provides helpful feedback
- No data corruption or loss occurs