# Phase 1: Slash Command Infrastructure Test Suite

## Overview
Tests the foundation infrastructure for slash commands without any actual hybrid commands. Validates that the bot starts properly, syncs commands with Discord, and maintains existing functionality.

## Prerequisites
- Bot must have applications.commands scope in Discord
- DISCORD_GUILD_ID must be set in .env for guild-specific sync
- Bot must have appropriate permissions in the test guild

## Test Cases

### Test 1: Bot Startup and Sync
**Objective:** Verify bot starts successfully and syncs commands

**Steps:**
1. Start the bot with `python -m bot.main`
2. Check console logs for startup sequence

**Expected Results:**
```
INFO:bot.main:Setting up Tournament Bot...
INFO:bot.main:Loaded cog: bot.cogs.admin
INFO:bot.main:Loaded cog: bot.cogs.tournament
INFO:bot.main:Loaded cog: bot.cogs.player
INFO:bot.main:Loaded cog: bot.cogs.challenge
INFO:bot.main:Loaded cog: bot.cogs.leaderboard
INFO:bot.main:Loaded cog: bot.cogs.events
INFO:bot.main:Loaded cog: bot.cogs.match_commands
INFO:bot.main:Synced commands to guild [GUILD_ID]
INFO:bot.main:Tournament Bot setup complete!
INFO:bot.main:[BOT_NAME] has connected to Discord!
INFO:bot.main:Bot is in [N] guilds
```

**Pass Criteria:**
- [ ] Bot starts without errors
- [ ] All cogs load successfully
- [ ] Commands sync to guild (instant) or globally
- [ ] No exceptions in startup process

### Test 2: Bot Status Verification
**Objective:** Confirm bot status reflects both command types

**Steps:**
1. Check bot's Discord presence/status
2. Verify the displayed activity message

**Expected Results:**
- Bot status shows: "Tournament Arc | !help or /help"

**Pass Criteria:**
- [ ] Status message includes both ! and / command references

### Test 3: Existing Prefix Commands Still Work
**Objective:** Ensure no regression in existing functionality

**Steps:**
1. Try existing prefix commands:
   - `!match-test`
   - `!ffa @user1 @user2 @user3` (if you have test users)
   - `!match-help`

**Expected Results:**
- All existing commands work exactly as before
- No changes in command behavior or responses

**Pass Criteria:**
- [ ] !match-test works (shows integration success)
- [ ] !match-help displays command information
- [ ] All existing commands respond normally

### Test 4: Slash Command Infrastructure (Empty State)
**Objective:** Verify slash command system is ready but no commands exist yet

**Steps:**
1. Type `/` in Discord chat
2. Look for the bot in the slash command picker
3. Check if any commands are listed for the bot

**Expected Results:**
- Bot appears in slash command picker
- No commands shown yet (this is expected - we haven't converted any)
- No errors when checking slash command interface

**Pass Criteria:**
- [ ] Bot is recognized by Discord's slash command system
- [ ] No unexpected slash commands present
- [ ] Discord shows bot as having slash command capability

### Test 5: Error Handling Validation
**Objective:** Test that error handlers are properly installed

**Steps:**
1. Check that app command error handler is attached:
   - Look for `self.tree.on_error = self.on_app_command_error` in logs/code
2. Verify both error handlers exist:
   - `on_command_error` (prefix commands)
   - `on_app_command_error` (slash commands)

**Expected Results:**
- Both error handlers are properly defined
- App command error handler is attached to tree
- No runtime errors during error handler setup

**Pass Criteria:**
- [ ] App command error handler attached in __init__
- [ ] Both error handler methods defined
- [ ] Error handlers include proper logging with exc_info=True

### Test 6: Guild vs Global Sync Strategy
**Objective:** Verify sync strategy works correctly

**Steps:**
1. **With DISCORD_GUILD_ID set:**
   - Restart bot
   - Check logs for "Synced commands to guild [ID]"
   
2. **Without DISCORD_GUILD_ID (optional):**
   - Temporarily remove DISCORD_GUILD_ID from .env
   - Restart bot
   - Check logs for "Synced commands globally"
   - **Note:** Global sync can take up to 1 hour to propagate

**Expected Results:**
- Guild sync: Instant updates, logged with guild ID
- Global sync: Successful sync logged, may take time to appear

**Pass Criteria:**
- [ ] Guild sync works and logs correctly
- [ ] Global sync works when guild ID not provided
- [ ] Bot continues working even if sync fails

### Test 7: Graceful Sync Failure Handling
**Objective:** Verify bot resilience to sync failures

**Steps:**
1. **Simulate sync failure** (one of these methods):
   - Temporarily remove applications.commands scope
   - Use invalid guild ID
   - Test with rate-limited bot

**Expected Results:**
- Bot logs sync failure with full traceback
- Bot continues startup process
- Prefix commands remain functional
- No crash or unhandled exceptions

**Pass Criteria:**
- [ ] Sync failure logged with exc_info=True (full traceback)
- [ ] Bot doesn't crash on sync failure
- [ ] Prefix commands still work after sync failure

## Environment Requirements

### Required Environment Variables
```bash
DISCORD_TOKEN=your_bot_token
DISCORD_GUILD_ID=your_test_guild_id  # For instant guild sync
OWNER_DISCORD_ID=your_discord_id
```

### Required Discord Permissions
- applications.commands (slash command scope)
- Send Messages
- Use Slash Commands
- Embed Links

## Success Criteria Summary

**Phase 1 is successful if:**
1. ✅ Bot starts without errors and syncs commands
2. ✅ All existing prefix commands continue working
3. ✅ Bot appears in Discord's slash command picker (but no commands yet)
4. ✅ Both error handlers are properly installed
5. ✅ Sync strategy works (guild for dev, global for prod)
6. ✅ Bot gracefully handles sync failures
7. ✅ No breaking changes to existing functionality

## Next Steps After Phase 1
- Phase 2A: Convert simple commands to hybrid
- Phase 2B: Convert complex commands (ffa, match-report) to hybrid
- Phase 3: Mass migration of remaining commands

## Troubleshooting

### Common Issues
1. **Bot doesn't appear in slash command picker**
   - Check applications.commands scope is enabled
   - Verify DISCORD_GUILD_ID is correct
   - Check bot permissions in guild

2. **Sync fails with permission error**
   - Ensure bot has applications.commands scope
   - Verify bot is in the guild specified by DISCORD_GUILD_ID

3. **Global sync doesn't show commands**
   - Global sync can take up to 1 hour
   - Use guild sync for development/testing

4. **Existing commands stop working**
   - This indicates a breaking change - Phase 1 should not affect prefix commands
   - Check for import errors or missing dependencies