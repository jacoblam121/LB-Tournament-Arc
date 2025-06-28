# Phase 1.1 Test Plan: /ffa Command Removal

## Overview
This test plan validates the successful removal of the /ffa command and all related architecture-violating functions while ensuring the bot starts correctly and provides proper user guidance.

## Pre-Test Setup
1. Ensure the bot is stopped
2. Verify all Phase 1.1 changes are implemented
3. Check that database connection is configured in .env

## Test Suite

### Test 1: Bot Startup (Critical)
**Objective**: Verify bot starts without crashes after EventOperations removal

**Steps**:
1. Start the bot: `python -m bot.main`
2. Wait for bot to fully initialize
3. Check console output for any errors

**Expected Results**:
- ✅ Bot starts successfully
- ✅ No NameError or import errors in console
- ✅ "MatchCommandsCog: All operations initialized successfully" appears in logs
- ✅ Bot shows as online in Discord

**Critical Issue**: If bot crashes with NameError about EventOperations, the fix wasn't applied correctly.

---

### Test 2: /ffa Command Deprecation Notice
**Objective**: Verify /ffa command shows helpful deprecation message

**Steps**:
1. In Discord, run: `/ffa players:@user1 @user2`
2. Check the response message

**Expected Results**:
- ✅ Command executes without errors
- ✅ Shows orange embed with "⚠️ Command Deprecated" title
- ✅ Explains that /ffa is no longer available
- ✅ Provides 4-step guidance for /challenge workflow
- ✅ Explains why the change was made
- ✅ Message appears as ephemeral (only visible to command user)

---

### Test 3: Help Command Updated
**Objective**: Verify help command no longer advertises deprecated /ffa

**Steps**:
1. Run: `!match-help`
2. Review the "Available Commands" section

**Expected Results**:
- ✅ No longer shows "`!ffa @user1 @user2 ...`" instruction
- ✅ Still shows `!match-report` command
- ✅ Includes note about /ffa deprecation and /challenge alternative

---

### Test 4: Architecture Enforcement
**Objective**: Confirm ad-hoc event creation is no longer possible

**Steps**:
1. Try to access the removed functions through Python console:
   ```python
   from bot.operations.event_operations import EventOperations
   ops = EventOperations(None)
   # Try to call removed functions
   ops.create_ffa_event  # Should not exist
   ops.create_team_event  # Should not exist
   ```

**Expected Results**:
- ✅ `create_ffa_event` method does not exist (AttributeError)
- ✅ `create_team_event` method does not exist (AttributeError)
- ✅ EventOperations class still exists but simplified
- ✅ Only `get_or_create_default_cluster` and `validate_cluster_exists` methods remain

---

### Test 5: Match Reporting Still Works
**Objective**: Ensure existing functionality remains intact

**Steps**:
1. If any existing matches exist, try: `!match-report <match_id>`
2. Verify the command still functions

**Expected Results**:
- ✅ Match reporting command still works
- ✅ No errors related to removed EventOperations
- ✅ Modal or placement input system still functional

---

## Test Results Template

```
## Phase 1.1 Test Results - [Date]

### Test 1: Bot Startup
- [ ] Bot starts successfully
- [ ] No import errors
- [ ] Operations initialized message appears
- [ ] Bot shows online in Discord
- **Notes**: 

### Test 2: /ffa Deprecation Notice  
- [ ] Command executes without errors
- [ ] Shows proper deprecation embed
- [ ] Provides /challenge guidance
- [ ] Message is ephemeral
- **Notes**:

### Test 3: Help Command Updated
- [ ] No longer shows /ffa instruction
- [ ] Still shows match-report
- [ ] Includes deprecation note
- **Notes**:

### Test 4: Architecture Enforcement
- [ ] create_ffa_event method removed
- [ ] create_team_event method removed
- [ ] EventOperations class simplified
- **Notes**:

### Test 5: Match Reporting Works
- [ ] Match reporting still functional
- [ ] No EventOperations errors
- **Notes**:

### Overall Status
- [ ] All tests pass - Phase 1.1 successful
- [ ] Some issues found (details below)

### Issues Found
1. 
2. 

### Next Steps
- [ ] Proceed to Phase 1.2 (Database Population)
- [ ] Fix identified issues first
```

## Troubleshooting

### If Bot Won't Start
- Check for remaining EventOperations references in match_commands.py
- Verify imports are correctly cleaned up
- Check console for specific error messages

### If /ffa Still Creates Matches
- Verify the function body was replaced, not just commented
- Check if there are multiple /ffa command definitions

### If Architecture Violations Remain
- Search codebase for any remaining create_ffa_event calls
- Verify event_operations.py changes were saved

## Success Criteria
✅ All 5 tests pass without issues
✅ Bot starts and runs normally  
✅ Users get helpful guidance about new workflow
✅ No way to create ad-hoc events remains
✅ Existing functionality preserved