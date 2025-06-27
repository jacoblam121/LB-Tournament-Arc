# Phase 2A2.5 Subphase 1 Manual Test Suite
## Discord Command Foundation Validation

**Objective**: Validate that the Discord command foundation is working correctly and ready for implementation of actual FFA/reporting functionality.

**Prerequisites**:
1. Bot is running with `DISCORD_TOKEN`, `DISCORD_GUILD_ID`, and `OWNER_DISCORD_ID` configured
2. Database is initialized and accessible
3. MatchOperations backend (Phase 2A2.4) is functional
4. You have Discord permissions to run commands in the test server

---

## Test 1: Cog Loading Verification
**Purpose**: Verify the new match_commands cog loads without errors

### Steps:
1. Start the bot with: `python -m bot.main`
2. Check console output for successful cog loading

### Expected Results:
✅ **PASS**: Console shows "Loaded cog: bot.cogs.match_commands"  
❌ **FAIL**: Error messages or missing cog load confirmation

### Notes:
- The cog should load after other cogs
- Watch for any import errors or dependency issues

---

## Test 2: Integration Test Command
**Purpose**: Validate MatchOperations backend connectivity

### Steps:
1. In Discord, run: `!match-test`
2. Alternative: `!mtest`

### Expected Results:
✅ **PASS**: Green embed with "Integration Test Successful"  
✅ **PASS**: Shows "Database connection verified (test value: 1)"  
✅ **PASS**: Displays "MatchOperations connected and operational"  
❌ **FAIL**: Red embed with error message

### What This Tests:
- Cog is properly registered and responsive
- MatchOperations can be instantiated with bot.db
- Database connectivity works through the backend
- Error handling displays user-friendly messages

---

## Test 3: Command Stubs Functionality
**Purpose**: Verify placeholder commands respond appropriately

### Steps:
1. Run: `!ffa-create` (or `!ffa`)
2. Run: `!match-report` (or `!report`) 
3. Run: `!match-help`

### Expected Results for each command:
✅ **PASS**: Orange embed with "Command Under Development"  
✅ **PASS**: Shows current development status  
✅ **PASS**: Directs user to use `!match-test`  
✅ **PASS**: Help command shows all available commands and their status

### What This Tests:
- All stub commands are accessible
- Consistent messaging about development status
- Clear user guidance for testing

---

## Test 4: Error Handling
**Purpose**: Validate graceful handling of error conditions

### Steps:
1. **Simulate database unavailable**: Temporarily stop database or corrupt connection
2. Run: `!match-test`
3. Restart database/fix connection
4. Run: `!match-test` again

### Expected Results:
✅ **PASS**: Step 2 shows red embed with clear error message  
✅ **PASS**: Step 4 returns to green success embed  
❌ **FAIL**: Bot crashes, unhandled exceptions, or unclear error messages

---

## Test 5: Command Discovery
**Purpose**: Ensure commands are discoverable and work as expected

### Steps:
1. Run: `!help` (if bot has help command)
2. Try variations: `!match-test`, `!mtest` 
3. Try variations: `!ffa`, `!ffa-create`
4. Try variations: `!report`, `!match-report`

### Expected Results:
✅ **PASS**: All command variations work as expected  
✅ **PASS**: Commands show up in help (if applicable)  
✅ **PASS**: No command conflicts with existing functionality

---

## Test 6: Concurrent Usage
**Purpose**: Verify commands work with multiple users

### Steps:
1. Have 2-3 different Discord users run `!match-test` simultaneously
2. Run different commands from different users at the same time

### Expected Results:
✅ **PASS**: All users receive appropriate responses  
✅ **PASS**: No database locking issues  
✅ **PASS**: No race conditions or crashes

---

## Test 7: Performance & Responsiveness
**Purpose**: Ensure commands respond quickly

### Steps:
1. Run `!match-test` multiple times in succession
2. Measure response time (should be < 2 seconds typically)

### Expected Results:
✅ **PASS**: Consistent response times  
✅ **PASS**: No memory leaks or performance degradation  
✅ **PASS**: Database connections are properly released

---

## Test 8: Logging & Debugging
**Purpose**: Verify proper logging behavior

### Steps:
1. Check bot console output during all tests
2. Look for log files in `logs/` directory

### Expected Results:
✅ **PASS**: Cog initialization messages appear in logs  
✅ **PASS**: Error conditions are properly logged  
❌ **KNOWN ISSUE**: Some print() statements may appear instead of proper logs (Code Review Item)

---

## Known Issues from Code Review
*(These are not test failures, but improvement opportunities)*

1. **Logging Inconsistency**: Some messages use print() instead of proper logging
2. **Abstraction Bypass**: Test command directly accesses database instead of going through MatchOperations
3. **Generic Exception Handling**: Could be more specific about which exceptions to catch
4. **Command Naming**: `!report` alias might conflict with future features

---

## Success Criteria
**Foundation is READY for Subphase 2 if**:
- ✅ All 7 main tests pass  
- ✅ No critical errors or crashes
- ✅ Commands are responsive and user-friendly
- ✅ Integration with MatchOperations backend works

**Overall Assessment**:
- [ ] **PASS**: Foundation is solid, ready for FFA/report implementation
- [ ] **FAIL**: Critical issues found, needs fixes before proceeding

---

## Next Steps After Testing
1. **If tests pass**: Proceed to Phase 2A2.5 Subphase 2 (FFA Command Implementation)
2. **If tests fail**: Address critical issues and re-test
3. **Optional improvements**: Address code review findings for better maintainability

---

**Testing Notes**:
- Record any unexpected behavior or error messages
- Note performance characteristics
- Document any Discord-specific issues (permissions, rate limits, etc.)
- Pay attention to user experience - are error messages helpful?