# Phase 1.1.3 Rate Limiting Infrastructure - Manual Test Plan

## Overview
Test plan for validating the Phase 1.1.3 SimpleRateLimiter implementation, including sliding window algorithm, decorator pattern integration, and Discord command rate limiting.

## Prerequisites
- Phase 1.1.1 and 1.1.2 completed successfully
- Discord bot configured and running
- Test Discord server with appropriate permissions
- Ability to create test commands or cogs

## Test Categories

### 1. Rate Limiter Core Functionality

#### Test 1.1: Rate Limiter Instantiation
**Objective**: Verify SimpleRateLimiter can be created and integrated with bot

**Steps**:
1. Check that rate limiter is properly instantiated in main.py:
   ```python
   # Verify in TournamentBot.__init__():
   print(f"Rate limiter type: {type(self.rate_limiter)}")
   print(f"Rate limiter available: {hasattr(self, 'rate_limiter')}")
   ```

2. Start the bot and verify no import errors
3. Check that `bot.rate_limiter` is accessible from cogs

**Expected Results**:
- No import errors on startup
- `SimpleRateLimiter` instance created successfully
- Bot has `rate_limiter` attribute available
- Rate limiter accessible from command contexts

**Pass/Fail**: ___________

#### Test 1.2: Basic Rate Limiting Logic
**Objective**: Test core rate limiting algorithm with direct calls

**Steps**:
1. Create test script to test rate limiter directly:
   ```python
   from bot.services.rate_limiter import SimpleRateLimiter
   import time
   
   rate_limiter = SimpleRateLimiter()
   user_id = 12345
   command = "test_command"
   
   # Test normal operation (limit=2, window=60)
   result1 = rate_limiter.is_allowed(user_id, command, limit=2, window=60)
   result2 = rate_limiter.is_allowed(user_id, command, limit=2, window=60)
   result3 = rate_limiter.is_allowed(user_id, command, limit=2, window=60)
   
   print(f"Request 1: {result1}")  # Should be True
   print(f"Request 2: {result2}")  # Should be True
   print(f"Request 3: {result3}")  # Should be False
   
   # Test different user
   result4 = rate_limiter.is_allowed(67890, command, limit=2, window=60)
   print(f"Different user: {result4}")  # Should be True
   ```

**Expected Results**:
- First 2 requests for same user allowed (True)
- 3rd request for same user blocked (False)
- Different user not affected by first user's limits
- Rate limiting isolated per user

**Pass/Fail**: ___________

#### Test 1.3: Sliding Window Algorithm
**Objective**: Test that rate limiting window slides correctly over time

**Steps**:
1. Test window expiration:
   ```python
   rate_limiter = SimpleRateLimiter()
   user_id = 11111
   command = "window_test"
   
   # Fill up the limit (2 requests in 5 seconds)
   result1 = rate_limiter.is_allowed(user_id, command, limit=2, window=5)
   result2 = rate_limiter.is_allowed(user_id, command, limit=2, window=5)
   result3 = rate_limiter.is_allowed(user_id, command, limit=2, window=5)
   
   print(f"Requests 1-3: {result1}, {result2}, {result3}")
   
   # Wait for window to expire
   print("Waiting 6 seconds for window to expire...")
   time.sleep(6)
   
   # Should be allowed again
   result4 = rate_limiter.is_allowed(user_id, command, limit=2, window=5)
   print(f"After window expiry: {result4}")  # Should be True
   ```

**Expected Results**:
- Initial requests follow limit correctly
- After window expires, requests allowed again
- Old requests properly removed from sliding window
- Window sliding works as expected

**Pass/Fail**: ___________

#### Test 1.4: Multiple Command Isolation
**Objective**: Test that different commands have separate rate limits

**Steps**:
1. Test command isolation:
   ```python
   rate_limiter = SimpleRateLimiter()
   user_id = 22222
   
   # Max out limit for command1
   result1a = rate_limiter.is_allowed(user_id, "command1", limit=1, window=60)
   result1b = rate_limiter.is_allowed(user_id, "command1", limit=1, window=60)
   
   # Test command2 (should not be affected)
   result2a = rate_limiter.is_allowed(user_id, "command2", limit=1, window=60)
   
   print(f"Command1: {result1a}, {result1b}")  # True, False
   print(f"Command2: {result2a}")              # True
   ```

**Expected Results**:
- Commands have independent rate limits
- Hitting limit on one command doesn't affect others
- User-command combination creates unique rate limit buckets

**Pass/Fail**: ___________

### 2. Decorator Pattern Integration

#### Test 2.1: Rate Limit Decorator Basic Function
**Objective**: Test @rate_limit decorator on Discord commands

**Steps**:
1. Create test cog with rate-limited command:
   ```python
   from discord.ext import commands
   from bot.services.rate_limiter import rate_limit
   
   class TestRateLimitCog(commands.Cog):
       def __init__(self, bot):
           self.bot = bot
       
       @commands.command(name="testrate")
       @rate_limit("testrate", limit=2, window=30)
       async def test_rate_command(self, ctx):
           await ctx.send(f"✅ Command executed! User: {ctx.author.id}")
   
   # Add to bot: await bot.add_cog(TestRateLimitCog(bot))
   ```

2. Test in Discord:
   - Use `!testrate` command 3 times quickly
   - Verify first 2 succeed, 3rd shows rate limit message

**Expected Results**:
- First 2 command uses succeed with ✅ message
- 3rd command shows rate limit warning
- Rate limit message is ephemeral/user-specific
- Decorator integrates seamlessly with Discord.py

**Pass/Fail**: ___________

#### Test 2.2: Admin Bypass Functionality
**Objective**: Test that administrators bypass rate limits

**Steps**:
1. Test with administrator permissions:
   - Use the rate-limited test command multiple times rapidly
   - Verify administrator users bypass rate limits

2. Test with regular user:
   - Same command should respect rate limits
   - Compare behavior between admin and regular users

**Expected Results**:
- Administrators bypass rate limits completely
- Regular users still subject to rate limits
- Permission check works correctly
- No errors in admin bypass logic

**Pass/Fail**: ___________

#### Test 2.3: Decorator Parameter Validation
**Objective**: Test decorator with various parameter combinations

**Steps**:
1. Create commands with different rate limit settings:
   ```python
   @rate_limit("fast", limit=5, window=10)     # 5 per 10 seconds
   async def fast_command(self, ctx): pass
   
   @rate_limit("slow", limit=1, window=60)     # 1 per minute
   async def slow_command(self, ctx): pass
   
   @rate_limit("burst", limit=10, window=5)    # 10 per 5 seconds
   async def burst_command(self, ctx): pass
   ```

2. Test each command's rate limiting behavior
3. Verify different limits work independently

**Expected Results**:
- Each command respects its specific rate limits
- Different window sizes work correctly
- Different limit counts enforced properly
- No interference between different rate limit configs

**Pass/Fail**: ___________

### 3. Discord Integration Test

#### Test 3.1: Slash Command Rate Limiting
**Objective**: Test rate limiting on Discord slash commands

**Steps**:
1. Create rate-limited slash command:
   ```python
   from discord import app_commands
   
   @app_commands.command(name="slashtest", description="Test slash command rate limiting")
   @rate_limit("slashtest", limit=2, window=30)
   async def test_slash_rate(self, interaction: discord.Interaction):
       await interaction.response.send_message("✅ Slash command executed!", ephemeral=True)
   ```

2. Test in Discord:
   - Use `/slashtest` command 3 times quickly
   - Verify rate limiting works with slash commands

**Expected Results**:
- Rate limiting works with slash commands
- Error messages are ephemeral (private)
- Interaction responses handled correctly
- No timing issues with Discord interactions

**Pass/Fail**: ___________

#### Test 3.2: Mixed Command Types
**Objective**: Test rate limiting across different Discord command types

**Steps**:
1. Create both prefix and slash versions of same command
2. Test if rate limits are shared or separate
3. Test hybrid commands if available

**Expected Results**:
- Rate limiting behavior is consistent across command types
- Same command name shares rate limits regardless of invocation method
- No confusion between different command implementations

**Pass/Fail**: ___________

#### Test 3.3: Error Message Customization
**Objective**: Test rate limit error message display

**Steps**:
1. Trigger rate limit on various commands
2. Check error message format and content:
   ```
   Expected: "⏰ Rate limit exceeded. Please wait before using `/command` again."
   ```
3. Verify message is user-friendly and informative

**Expected Results**:
- Error messages are clear and helpful
- Command name included in error message
- Messages use appropriate Discord formatting
- No technical jargon in user-facing messages

**Pass/Fail**: ___________

### 4. Edge Cases & Stress Testing

#### Test 4.1: Concurrent User Rate Limiting
**Objective**: Test rate limiting with multiple simultaneous users

**Steps**:
1. If possible, test with multiple Discord accounts or simulate:
   ```python
   import asyncio
   
   async def simulate_user_requests(user_id, rate_limiter):
       results = []
       for i in range(5):
           allowed = rate_limiter.is_allowed(user_id, "concurrent_test", limit=2, window=10)
           results.append(f"User {user_id} request {i+1}: {allowed}")
           await asyncio.sleep(0.1)
       return results
   
   # Test multiple users concurrently
   tasks = [
       simulate_user_requests(1001, rate_limiter),
       simulate_user_requests(1002, rate_limiter),
       simulate_user_requests(1003, rate_limiter)
   ]
   
   results = await asyncio.gather(*tasks)
   for user_results in results:
       for result in user_results:
           print(result)
   ```

**Expected Results**:
- Each user has independent rate limits
- No interference between concurrent users
- Thread safety maintained
- No race conditions in rate limiting logic

**Pass/Fail**: ___________

#### Test 4.2: Memory Usage Under Load
**Objective**: Test memory behavior with many users and commands

**Steps**:
1. Simulate high usage:
   ```python
   import random
   
   rate_limiter = SimpleRateLimiter()
   
   # Simulate 1000 users using various commands
   for i in range(10000):
       user_id = random.randint(100000, 999999)
       command = random.choice(["cmd1", "cmd2", "cmd3", "cmd4", "cmd5"])
       rate_limiter.is_allowed(user_id, command, limit=5, window=60)
   
   # Check internal data structure size
   print(f"Rate limiter tracking {len(rate_limiter._requests)} user-command combinations")
   ```

2. Monitor memory usage during test
3. Verify old entries are cleaned up properly

**Expected Results**:
- Memory usage remains reasonable
- Old expired entries are cleaned up
- No memory leaks in long-running usage
- Data structure size doesn't grow indefinitely

**Pass/Fail**: ___________

#### Test 4.3: Edge Case Parameters
**Objective**: Test rate limiter with edge case parameters

**Steps**:
1. Test extreme parameters:
   ```python
   rate_limiter = SimpleRateLimiter()
   user_id = 99999
   
   # Test very short window
   result1 = rate_limiter.is_allowed(user_id, "short", limit=1, window=1)
   time.sleep(2)
   result2 = rate_limiter.is_allowed(user_id, "short", limit=1, window=1)
   
   # Test very high limit
   results_high = []
   for i in range(1000):
       results_high.append(rate_limiter.is_allowed(user_id, "high", limit=999, window=60))
   
   # Test zero parameters (should handle gracefully)
   try:
       result_zero = rate_limiter.is_allowed(user_id, "zero", limit=0, window=60)
       print(f"Zero limit result: {result_zero}")
   except Exception as e:
       print(f"Zero limit error: {e}")
   ```

**Expected Results**:
- Very short windows work correctly
- High limits don't cause performance issues
- Edge cases handled gracefully
- No crashes with unusual parameters

**Pass/Fail**: ___________

### 5. Performance & Scalability Test

#### Test 5.1: Rate Limiter Performance
**Objective**: Test rate limiter performance under normal load

**Steps**:
1. Performance benchmark:
   ```python
   import time
   
   rate_limiter = SimpleRateLimiter()
   
   # Benchmark 1000 rate limit checks
   start_time = time.time()
   
   for i in range(1000):
       user_id = i % 100  # 100 different users
       command = f"cmd{i % 10}"  # 10 different commands
       rate_limiter.is_allowed(user_id, command, limit=5, window=60)
   
   end_time = time.time()
   total_time = end_time - start_time
   
   print(f"1000 rate limit checks took {total_time:.4f} seconds")
   print(f"Average: {(total_time/1000)*1000:.2f} ms per check")
   ```

**Expected Results**:
- Rate limit checks complete quickly (<1ms average)
- Performance scales well with user count
- No significant slowdown with realistic loads
- Memory usage remains constant

**Pass/Fail**: ___________

#### Test 5.2: Cleanup Efficiency
**Objective**: Test cleanup of expired rate limit entries

**Steps**:
1. Test cleanup behavior:
   ```python
   rate_limiter = SimpleRateLimiter()
   
   # Fill with entries that will expire
   for i in range(100):
       rate_limiter.is_allowed(i, "cleanup_test", limit=5, window=2)
   
   print(f"Initial entries: {len(rate_limiter._requests)}")
   
   # Wait for expiry
   time.sleep(3)
   
   # Trigger cleanup by making new request
   rate_limiter.is_allowed(999, "cleanup_trigger", limit=1, window=60)
   
   print(f"After cleanup: {len(rate_limiter._requests)}")
   ```

**Expected Results**:
- Expired entries are cleaned up automatically
- Cleanup happens during normal operation
- Memory usage decreases after cleanup
- Performance remains good after cleanup

**Pass/Fail**: ___________

### 6. Error Handling & Recovery Test

#### Test 6.1: Missing Bot Instance Handling
**Objective**: Test decorator behavior when bot instance unavailable

**Steps**:
1. Test decorator with missing rate_limiter:
   ```python
   # Temporarily remove rate limiter from bot
   original_rate_limiter = bot.rate_limiter
   bot.rate_limiter = None
   
   # Try to use rate-limited command
   # Should handle gracefully without crashing
   
   # Restore rate limiter
   bot.rate_limiter = original_rate_limiter
   ```

**Expected Results**:
- Commands handle missing rate limiter gracefully
- No unhandled exceptions
- Appropriate error messages or fallback behavior
- System remains stable

**Pass/Fail**: ___________

#### Test 6.2: Invalid Parameter Handling
**Objective**: Test rate limiter with invalid inputs

**Steps**:
1. Test invalid parameters:
   ```python
   rate_limiter = SimpleRateLimiter()
   
   try:
       # Test negative values
       result1 = rate_limiter.is_allowed(12345, "test", limit=-1, window=60)
       result2 = rate_limiter.is_allowed(12345, "test", limit=5, window=-10)
       
       # Test None values
       result3 = rate_limiter.is_allowed(None, "test", limit=5, window=60)
       result4 = rate_limiter.is_allowed(12345, None, limit=5, window=60)
       
       print("Results with invalid params:", result1, result2, result3, result4)
   except Exception as e:
       print(f"Exception with invalid params: {e}")
   ```

**Expected Results**:
- Invalid parameters handled gracefully
- No crashes with bad input
- Appropriate error handling or fallback behavior
- System maintains stability

**Pass/Fail**: ___________

## Summary

### Overall Test Results
- Rate Limiter Core Functionality: ___/4 tests passed
- Decorator Pattern Integration: ___/3 tests passed  
- Discord Integration: ___/3 tests passed
- Edge Cases & Stress Testing: ___/3 tests passed
- Performance & Scalability: ___/2 tests passed
- Error Handling & Recovery: ___/2 tests passed

**Total: ___/17 tests passed**

### Critical Issues Found
_(List any critical issues that prevent production deployment)_

1. ________________________________
2. ________________________________
3. ________________________________

### Performance Issues Found
_(List any performance concerns)_

1. ________________________________
2. ________________________________
3. ________________________________

### Integration Issues Found
_(List any Discord integration problems)_

1. ________________________________
2. ________________________________
3. ________________________________

### Recommendations
_(List recommendations for improvements)_

1. ________________________________
2. ________________________________
3. ________________________________

### Ready for Phase 1.2?
Based on test results: **YES** / **NO**

**Required for next phase:**
- [ ] Basic rate limiting works correctly
- [ ] Decorator pattern functions properly
- [ ] Discord integration successful
- [ ] Admin bypass working
- [ ] Performance acceptable
- [ ] Error handling robust

**Tester**: _________________ **Date**: _________

## Notes
_(Additional testing notes and observations)_

________________________________________________________
________________________________________________________
________________________________________________________