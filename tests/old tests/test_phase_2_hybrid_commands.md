# Phase 2: Hybrid Command Test Suite

## Overview
Tests the conversion of !ffa and !match-report to hybrid commands (both prefix and slash). Validates backwards compatibility, new slash command functionality, and critical bug fixes.

## Prerequisites
- Bot must be running with Phase 2 implementation
- Slash commands synced successfully (should show 3 commands: ping, ffa, match-report)
- At least 3 test users available for FFA testing
- HYBRID_COMMANDS.md documentation should be accessible

## Test Cases

### Test 1: Hybrid Command Infrastructure Verification
**Objective:** Confirm all hybrid commands appear in Discord

**Steps:**
1. Type `/` in Discord
2. Look for bot in the command picker
3. Type `/Kenjaku` to filter bot commands

**Expected Results:**
- Bot appears in slash command picker
- Shows 3 commands: ping, ffa, match-report
- All commands have descriptions and parameter help

**Pass Criteria:**
- [ ] `/ping` command works and shows hybrid status
- [ ] `/ffa` command appears with players parameter
- [ ] `/match-report` command appears with match_id and placements parameters

### Test 2: FFA Command - Backwards Compatibility (Prefix)
**Objective:** Ensure existing !ffa usage still works exactly as before

**Steps:**
1. Test basic FFA: `!ffa @user1 @user2`
2. Test with more users: `!ffa @user1 @user2 @user3 @user4`
3. Test auto-include: `!ffa @user1 @user2` (you should be auto-included)
4. Test validation: `!ffa` (no users)
5. Test validation: `!ffa @user1` (too few users)

**Expected Results:**
- All existing functionality preserved
- Auto-include logic works (you + 2 others = 3 total)
- Error messages show both prefix and slash examples
- FFA matches created successfully
- Transaction safety maintained

**Pass Criteria:**
- [ ] `!ffa @user1 @user2` creates 3-player match (auto-includes you)
- [ ] `!ffa @user1 @user2 @user3 @user4` creates 5-player match
- [ ] `!ffa` shows helpful error with usage examples
- [ ] `!ffa @user1` shows "not enough players" error
- [ ] Error messages include both `!ffa` and `/ffa` examples

### Test 3: FFA Command - Slash Command Functionality
**Objective:** Test new slash command behavior

**Steps:**
1. Basic slash FFA: `/ffa players:@user1 @user2`
2. Test with multiple users: `/ffa players:@user1 @user2 @user3`
3. Test edge cases: `/ffa players:` (empty)
4. Test with quoted names: `/ffa players:"User Name" @user2`
5. Test parameter autocomplete and help text

**Expected Results:**
- Slash commands work identically to prefix
- Parameter descriptions appear clearly
- Auto-include logic preserved
- Error handling consistent with prefix

**Pass Criteria:**
- [ ] `/ffa players:@user1 @user2` creates 3-player match
- [ ] Parameter help shows: "Players for the match (space-separated mentions)"
- [ ] Empty players parameter shows helpful error
- [ ] Auto-include works (you're added if not mentioned)
- [ ] Error messages are clear and actionable

### Test 4: Match Report - Backwards Compatibility (Prefix)
**Objective:** Ensure existing !match-report usage works

**Steps:**
1. Create an FFA match first: `!ffa @user1 @user2 @user3`
2. Note the match ID from the response
3. Test basic report: `!match-report <match_id> @user1:1 @user2:2 @user3:3`
4. Test different format: `!match-report <match_id> @winner:1 @second:2 @third:3`
5. Test validation: `!match-report` (no args)
6. Test validation: `!match-report 123` (no placements)

**Expected Results:**
- Placement parsing works correctly
- Elo calculations applied
- Match marked as completed
- Error handling for invalid input

**Pass Criteria:**
- [ ] `!match-report 123 @user1:1 @user2:2 @user3:3` works
- [ ] Elo ratings updated correctly
- [ ] Match status changes to completed
- [ ] Missing arguments show clear error messages
- [ ] Invalid placement format shows helpful examples

### Test 5: Match Report - Slash Command Functionality  
**Objective:** Test new slash command parsing (CRITICAL TEST)

**Steps:**
1. Create FFA match: `/ffa players:@user1 @user2 @user3`
2. Note the match ID
3. Test slash report: `/match-report match_id:123 placements:@user1:1 @user2:2 @user3:3`
4. Test validation: `/match-report match_id:123 placements:` (empty placements)
5. Test invalid format: `/match-report match_id:123 placements:@user1 @user2:3`

**Expected Results:**
- **CRITICAL**: No longer relies on ctx.message.mentions
- String parsing works for both command types
- Parameter validation is consistent

**Pass Criteria:**
- [ ] `/match-report match_id:123 placements:@user1:1 @user2:2 @user3:3` works
- [ ] No errors related to ctx.message.mentions
- [ ] Parameter help shows format clearly
- [ ] Invalid placement format shows helpful error
- [ ] Empty placements shows clear validation message

### Test 6: String Parsing Edge Cases
**Objective:** Test robust parsing with unusual input

**Steps:**
1. Test with user IDs: `/ffa players:123456789 987654321`
2. Test with nicknames: `/ffa players:"Nickname With Spaces" @user2`
3. Test mixed formats: `/ffa players:@user1 123456789 "nickname"`
4. Test placement edge cases: `/match-report match_id:123 placements:@user1:0 @user2:1`
5. Test duplicate users: `/ffa players:@user1 @user1 @user2`

**Expected Results:**
- shlex parsing handles quotes correctly
- MemberConverter resolves various user formats
- Validation catches edge cases gracefully

**Pass Criteria:**
- [ ] User ID format works: `123456789`
- [ ] Quoted nicknames work: `"User Name"`
- [ ] Mixed formats work together
- [ ] Invalid placements (0, negative) show errors
- [ ] Duplicate users detected and prevented

### Test 7: Error Handling Consistency
**Objective:** Ensure errors are handled consistently across both command types

**Steps:**
1. Test invalid users: `!ffa @nonexistentuser @user2` vs `/ffa players:@nonexistentuser @user2`
2. Test permission errors (if applicable)
3. Test database errors (if applicable)
4. Test malformed input: `!match-report 123 invalidformat` vs `/match-report match_id:123 placements:invalidformat`

**Expected Results:**
- Error messages are consistent
- Both command types handle errors gracefully
- User gets helpful guidance for fixing input

**Pass Criteria:**
- [ ] Nonexistent user errors are the same for both types
- [ ] Error messages are clear and actionable
- [ ] No crashes or unhandled exceptions
- [ ] Error format consistent (embed with examples)

### Test 8: Auto-Include Logic Validation
**Objective:** Verify command author auto-inclusion works properly

**Steps:**
1. Mention yourself: `!ffa @yourself @user1 @user2`
2. Don't mention yourself: `!ffa @user1 @user2`
3. Test slash version: `/ffa players:@user1 @user2`
4. Test slash with self: `/ffa players:@yourself @user1 @user2`

**Expected Results:**
- Auto-include only when not already mentioned
- Participant count is correct
- No duplicate inclusions

**Pass Criteria:**
- [ ] Self-mention prevents auto-include
- [ ] Auto-include works when not mentioned
- [ ] Participant count is accurate in both cases
- [ ] No "duplicate user" errors when self-mentioned

### Test 9: Documentation Verification
**Objective:** Confirm documentation is accurate and helpful

**Steps:**
1. Review HYBRID_COMMANDS.md
2. Check that examples match actual behavior
3. Verify helper method documentation is accurate
4. Test patterns described in documentation

**Expected Results:**
- Documentation matches implementation
- Examples work when tested
- Patterns are clearly explained

**Pass Criteria:**
- [ ] HYBRID_COMMANDS.md examples work correctly
- [ ] Helper method documentation is accurate
- [ ] Migration patterns are clear
- [ ] Best practices are demonstrated

## Integration Tests

### Integration Test 1: Full Match Workflow
**Objective:** Test complete match creation and reporting flow

**Steps:**
1. Create FFA with slash: `/ffa players:@user1 @user2 @user3`
2. Report results with prefix: `!match-report <id> @user1:1 @user2:2 @user3:3`
3. Verify Elo changes
4. Create another FFA with prefix: `!ffa @user1 @user2`
5. Report with slash: `/match-report match_id:<id> placements:@user1:1 @user2:2`

**Pass Criteria:**
- [ ] Cross-mode workflow works seamlessly
- [ ] Data consistency maintained
- [ ] Elo calculations correct
- [ ] No mode-specific issues

### Integration Test 2: Stress Testing
**Objective:** Test with maximum participants and edge cases

**Steps:**
1. Test 16-player FFA (max): `/ffa players:@u1 @u2 @u3 ... @u15`
2. Test 17-player FFA (over limit): Should fail gracefully
3. Test complex placement: All 16 players with different placements
4. Test database transaction rollback (if possible to simulate failure)

**Pass Criteria:**
- [ ] 16-player matches work correctly
- [ ] 17+ players rejected with clear error
- [ ] Complex placements processed correctly
- [ ] Transaction safety maintained

## Success Criteria Summary

**Phase 2 is successful if:**
1. ✅ All existing prefix commands work exactly as before
2. ✅ New slash commands work identically to prefix versions
3. ✅ String parsing handles all edge cases robustly
4. ✅ Error handling is consistent across both command types
5. ✅ Auto-include logic preserved
6. ✅ Transaction safety maintained
7. ✅ No ctx.message.mentions dependencies remain
8. ✅ Documentation is accurate and comprehensive

## Critical Issues to Watch For

### 🔴 Critical Issues
- **ctx.message.mentions failures**: Slash commands failing due to missing mentions
- **Parameter validation bypassed**: Required parameters not enforced
- **Transaction rollback failures**: Database inconsistency
- **Auto-include logic broken**: User not added when expected

### 🟡 Medium Issues  
- **Inconsistent error messages**: Different behavior between command types
- **Performance degradation**: String parsing causing delays
- **Edge case failures**: Unusual input causing crashes

### 🟢 Minor Issues
- **Help text unclear**: Parameter descriptions could be better
- **Error message formatting**: Cosmetic improvements needed

## Troubleshooting

### Common Issues
1. **Slash commands not appearing**
   - Check bot restart after Phase 2 changes
   - Verify sync logs show 3 commands
   - Clear Discord client cache (Ctrl+R)

2. **ctx.message.mentions errors**
   - Indicates incomplete conversion
   - Should use string parsing helpers instead

3. **String parsing failures**
   - Check shlex import and error handling
   - Verify MemberConverter usage

4. **Auto-include not working**
   - Check order of auto-include vs validation
   - Verify ctx.author comparison logic

## Next Steps After Phase 2
- Phase 3: Mass migration of remaining commands
- Performance optimization if needed
- Additional slash command features (autocomplete, choices)