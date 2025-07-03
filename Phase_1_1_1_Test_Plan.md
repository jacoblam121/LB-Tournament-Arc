# Phase 1.1.1 Base Service Pattern - Manual Test Plan

## Overview
Test plan for validating the Phase 1.1.1 implementation including BaseService class, Configuration/AuditLog models, and SimpleRateLimiter functionality.

## Prerequisites
- Discord bot token configured
- Database connection working
- Bot has necessary permissions in test server

## Test Categories

### 1. Database Models Test

#### Test 1.1: Verify New Tables Creation
**Objective**: Confirm Configuration and AuditLog tables are created correctly

**Steps**:
1. Start the bot application
2. Check database schema using SQLite browser or command line
3. Verify tables exist: `configurations`, `audit_logs`
4. Verify column structures match the models

**Expected Results**:
- `configurations` table exists with columns: key (TEXT PRIMARY KEY), value (TEXT), updated_at (DATETIME)
- `audit_logs` table exists with columns: id (INTEGER PRIMARY KEY), user_id (BIGINT), action (TEXT), details (TEXT), created_at (DATETIME)

**Pass/Fail**: ___________

#### Test 1.2: Basic Configuration Model Operations
**Objective**: Test Configuration model CRUD operations

**Steps**:
1. Connect to database manually or via bot console
2. Insert test configuration: `INSERT INTO configurations (key, value) VALUES ('test.param', '{"value": 42}')`
3. Query the record: `SELECT * FROM configurations WHERE key = 'test.param'`
4. Update the record: `UPDATE configurations SET value = '{"value": 100}' WHERE key = 'test.param'`
5. Verify updated_at timestamp changed

**Expected Results**:
- Insert succeeds
- Query returns correct data
- Update succeeds and timestamp updates
- JSON storage works correctly

**Pass/Fail**: ___________

### 2. BaseService Class Test

#### Test 2.1: Service Instantiation
**Objective**: Verify BaseService can be instantiated correctly

**Steps**:
1. Add temporary test to main.py or create test script:
```python
from bot.services.base import BaseService
from bot.database.database import Database

# Initialize database
db = Database()
await db.initialize()

# Create service instance
service = BaseService(db.async_session)
print("BaseService instantiated successfully")
```

**Expected Results**:
- No errors during instantiation
- Service has access to session_factory

**Pass/Fail**: ___________

#### Test 2.2: Session Management
**Objective**: Test async session context manager

**Steps**:
1. Create test script to use BaseService.get_session():
```python
async with service.get_session() as session:
    # Perform database operation
    result = await session.execute(select(Configuration))
    configs = result.scalars().all()
    print(f"Found {len(configs)} configurations")
```

**Expected Results**:
- Session opens and closes correctly
- Database operations work within session
- Automatic commit/rollback functions

**Pass/Fail**: ___________

#### Test 2.3: Retry Logic
**Objective**: Test execute_with_retry functionality

**Steps**:
1. Create test function that fails first 2 times, succeeds on 3rd:
```python
attempt_count = 0
async def test_function():
    global attempt_count
    attempt_count += 1
    if attempt_count < 3:
        raise Exception(f"Attempt {attempt_count} failed")
    return "Success!"

result = await service.execute_with_retry(test_function)
print(f"Result: {result}, Total attempts: {attempt_count}")
```

**Expected Results**:
- Function retries on failure
- Exponential backoff delays work
- Eventually succeeds on 3rd attempt

**Pass/Fail**: ___________

### 3. Rate Limiter Test

#### Test 3.1: Rate Limiter Instantiation
**Objective**: Verify SimpleRateLimiter can be created and added to bot

**Steps**:
1. Add to main.py TournamentBot.__init__():
```python
from bot.services.rate_limiter import SimpleRateLimiter
# ... in __init__ method:
self.rate_limiter = SimpleRateLimiter()
```
2. Start bot
3. Verify bot.rate_limiter is accessible

**Expected Results**:
- Bot starts without errors
- rate_limiter attribute is available
- No import errors

**Pass/Fail**: ___________

#### Test 3.2: Rate Limit Logic Test
**Objective**: Test rate limiting logic with direct calls

**Steps**:
1. Create test script:
```python
rate_limiter = SimpleRateLimiter()

# Test normal operation (should allow)
result1 = rate_limiter.is_allowed(12345, "test", limit=2, window=60)
result2 = rate_limiter.is_allowed(12345, "test", limit=2, window=60)
result3 = rate_limiter.is_allowed(12345, "test", limit=2, window=60)  # Should be blocked

print(f"Request 1: {result1}")  # Should be True
print(f"Request 2: {result2}")  # Should be True  
print(f"Request 3: {result3}")  # Should be False
```

**Expected Results**:
- First 2 requests allowed (True)
- 3rd request blocked (False)
- Rate limiting math works correctly

**Pass/Fail**: ___________

#### Test 3.3: Rate Limit Decorator Test
**Objective**: Test @rate_limit decorator on actual command

**Steps**:
1. Create temporary test cog:
```python
from bot.services.rate_limiter import rate_limit

class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="testrate")
    @rate_limit("testrate", limit=1, window=30)
    async def test_rate_command(self, ctx):
        await ctx.send("Command executed successfully!")
```
2. Load cog and test in Discord
3. Use command twice quickly
4. Verify rate limit message appears

**Expected Results**:
- First command execution succeeds
- Second immediate command shows rate limit message
- Admin users bypass rate limits

**Pass/Fail**: ___________

### 4. Integration Test

#### Test 4.1: Full System Integration
**Objective**: Verify all components work together

**Steps**:
1. Start bot with all new components
2. Check logs for any startup errors
3. Verify database tables created
4. Test a rate-limited command
5. Check if services are properly initialized

**Expected Results**:
- Bot starts successfully
- All services initialize without errors
- Database operations work
- Rate limiting functions correctly

**Pass/Fail**: ___________

#### Test 4.2: Error Handling Test
**Objective**: Test error handling and rollback

**Steps**:
1. Temporarily cause database error (invalid query)
2. Verify BaseService handles rollback correctly
3. Check that rate limiter handles missing bot instance gracefully
4. Verify proper error logging

**Expected Results**:
- Errors are caught and logged appropriately
- Database rollbacks occur on failures
- System remains stable after errors

**Pass/Fail**: ___________

## Summary

### Overall Test Results
- Database Models: ___/2 tests passed
- BaseService Class: ___/3 tests passed  
- Rate Limiter: ___/3 tests passed
- Integration: ___/2 tests passed

**Total: ___/10 tests passed**

### Issues Found
_(List any issues discovered during testing)_

1. ________________________________
2. ________________________________
3. ________________________________

### Recommendations
_(List any recommendations for improvements)_

1. ________________________________
2. ________________________________
3. ________________________________

### Ready for Next Phase?
Based on test results: **YES** / **NO**

**Tester**: _________________ **Date**: _________