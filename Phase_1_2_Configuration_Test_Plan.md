# Phase 1.2 Configuration Management System - Manual Test Plan

## Overview
Test plan for validating the Phase 1.2 Configuration Management System implementation including ConfigurationService, admin slash commands, seed data, and bot integration.

## Prerequisites
- Phase 1.1.1 completed and tested successfully
- Discord bot token configured and bot running
- Administrator permissions in test Discord server
- Database initialized with Configuration and AuditLog tables

## Test Categories

### 1. Configuration Service Test

#### Test 1.1: Configuration Service Initialization
**Objective**: Verify ConfigurationService initializes correctly and loads seed data

**Steps**:
1. Start the bot application
2. Check bot logs for "Configuration service initialized" message
3. Verify database has configuration records:
   ```sql
   SELECT COUNT(*) FROM configurations;
   ```
4. Check that configurations table contains ~85+ records

**Expected Results**:
- Bot starts without configuration-related errors
- Configuration service loads successfully
- Database contains 85+ configuration parameters
- Log shows "Loaded X configuration parameters"

**Pass/Fail**: ___________

#### Test 1.2: Configuration Get Operations
**Objective**: Test configuration retrieval by key and category

**Steps**:
1. Use bot console or create test script:
   ```python
   # Test direct service access
   config = bot.config_service.get('elo.starting_elo', 1000)
   print(f"Starting ELO: {config}")
   
   # Test category filtering
   elo_configs = bot.config_service.get_by_category('elo')
   print(f"ELO configs: {elo_configs}")
   
   # Test all configurations
   all_configs = bot.config_service.list_all()
   print(f"Total configs: {len(all_configs)}")
   ```

**Expected Results**:
- `elo.starting_elo` returns 1000
- `get_by_category('elo')` returns 6 parameters
- `list_all()` returns 85+ configurations
- No errors during retrieval operations

**Pass/Fail**: ___________

#### Test 1.3: Configuration Set Operations
**Objective**: Test configuration updates with audit trail

**Steps**:
1. Create test script to modify configuration:
   ```python
   # Test setting new value
   await bot.config_service.set('test.parameter', 999, user_id=12345)
   
   # Verify value updated
   value = bot.config_service.get('test.parameter')
   print(f"Test parameter: {value}")
   
   # Check audit log created
   # Query: SELECT * FROM audit_logs WHERE action = 'config_set' ORDER BY created_at DESC LIMIT 1;
   ```

**Expected Results**:
- Configuration value updates successfully
- New value is retrievable immediately
- Audit log entry created with user_id=12345
- Cache consistency maintained

**Pass/Fail**: ___________

### 2. Admin Slash Commands Test

#### Test 2.1: Config-List Command
**Objective**: Test `/config-list` command functionality

**Steps**:
1. In Discord, use `/config-list` (should work if you have admin permissions)
2. Test category filtering: `/config-list category:elo`
3. Test with invalid category: `/config-list category:nonexistent`
4. Test with non-admin user (if available)

**Expected Results**:
- `/config-list` shows all configurations (may be truncated)
- `/config-list category:elo` shows only ELO parameters
- Invalid category shows "No configuration found" message
- Non-admin user gets permission denied message

**Pass/Fail**: ___________

#### Test 2.2: Config-Get Command
**Objective**: Test `/config-get` command functionality

**Steps**:
1. Use `/config-get key:elo.starting_elo`
2. Use `/config-get key:nonexistent.key`
3. Test with complex configuration: `/config-get key:metagame.cluster_multipliers`
4. Test with non-admin user (if available)

**Expected Results**:
- Valid key returns correct value: `elo.starting_elo: 1000`
- Invalid key shows "Configuration key not found"
- Complex data (arrays/objects) displays correctly
- Non-admin user gets permission denied

**Pass/Fail**: ___________

#### Test 2.3: Config-Set Command
**Objective**: Test `/config-set` command functionality and validation

**Steps**:
1. Test integer update: `/config-set key:test.int value:42`
2. Test string update: `/config-set key:test.string value:"hello world"`
3. Test JSON object: `/config-set key:test.object value:{"foo": "bar"}`
4. Test invalid JSON: `/config-set key:test.invalid value:{invalid json}`
5. Test oversized key (300+ characters)
6. Verify audit trail in database

**Expected Results**:
- Valid updates succeed with confirmation message
- Invalid JSON treated as string value
- Oversized key rejected with error message
- All successful updates create audit log entries
- Values immediately available via `/config-get`

**Pass/Fail**: ___________

#### Test 2.4: Config-Reload Command
**Objective**: Test `/config-reload` command functionality

**Steps**:
1. Manually modify database: 
   ```sql
   UPDATE configurations SET value = '2000' WHERE key = 'elo.starting_elo';
   ```
2. Check current cached value: `/config-get key:elo.starting_elo`
3. Use `/config-reload`
4. Check value again: `/config-get key:elo.starting_elo`

**Expected Results**:
- Before reload: shows old cached value (1000)
- Reload command succeeds with confirmation
- After reload: shows new database value (2000)
- Cache properly refreshed from database

**Pass/Fail**: ___________

#### Test 2.5: Config-Categories Command
**Objective**: Test `/config-categories` command functionality

**Steps**:
1. Use `/config-categories`
2. Verify all expected categories appear:
   - elo, metagame, earning, shop, system
   - leaderboard_system, rate_limits, game_mechanics
3. Check parameter counts are reasonable (elo: 6, shop: 20+, etc.)

**Expected Results**:
- All 8 categories displayed
- Parameter counts match expected values
- Total shows 85+ parameters
- Clean formatting in response

**Pass/Fail**: ___________

### 3. Seed Data Integrity Test

#### Test 3.1: Critical Configuration Parameters
**Objective**: Verify essential configuration parameters exist with correct values

**Steps**:
1. Check core ELO parameters:
   - `/config-get key:elo.starting_elo` (should be 1000)
   - `/config-get key:elo.k_factor_provisional` (should be 40)
   - `/config-get key:elo.k_factor_standard` (should be 20)

2. Check system parameters:
   - `/config-get key:system.vig_percentage` (should be 0.1)
   - `/config-get key:system.match_expiry_hours` (should be 24)

3. Check metagame parameters:
   - `/config-get key:metagame.shard_bonus_pool` (should be 300)
   - `/config-get key:metagame.cluster_multipliers` (should be [4.0, 2.5, 1.5, 1.0])

**Expected Results**:
- All critical parameters exist
- Values match expected configuration
- No duplicate keys present
- Complex data types (arrays, objects) preserved correctly

**Pass/Fail**: ___________

#### Test 3.2: Configuration Data Types
**Objective**: Verify different data types are handled correctly

**Steps**:
1. Test integer values: `/config-get key:earning.participation_reward`
2. Test float values: `/config-get key:system.vig_percentage`
3. Test boolean values: `/config-get key:rate_limits.admin_bypass_enabled`
4. Test arrays: `/config-get key:metagame.cluster_multipliers`
5. Test objects: `/config-get key:shop.bounty_costs`
6. Test null values: `/config-get key:system.owner_discord_id`

**Expected Results**:
- Integers display as numbers (not strings)
- Floats preserve decimal precision
- Booleans show as true/false
- Arrays display with brackets
- Objects show as JSON format
- Null values handled gracefully

**Pass/Fail**: ___________

### 4. Security & Permissions Test

#### Test 4.1: Permission Validation
**Objective**: Test admin command security

**Steps**:
1. Test with server administrator permission
2. Test with bot owner Discord ID (if different from admin)
3. Test with regular user (no admin permissions)
4. Test with user who has some elevated permissions but not administrator

**Expected Results**:
- Administrator users can access all config commands
- Bot owner can access all config commands
- Regular users get "administrator permissions required" message
- Permission checks work for all 5 config commands

**Pass/Fail**: ___________

#### Test 4.2: Input Validation Security
**Objective**: Test input validation and size limits

**Steps**:
1. Test maximum key length (255 characters):
   - Create 255-char key: should succeed
   - Create 256-char key: should fail
2. Test maximum value length (10,000 characters):
   - Create large valid JSON: should succeed
   - Create oversized value: should fail
3. Test special characters in keys and values
4. Test SQL injection attempts in values (should be safe due to ORM)

**Expected Results**:
- Size limits enforced correctly
- Error messages clear and helpful
- No security vulnerabilities in input handling
- Special characters handled safely

**Pass/Fail**: ___________

### 5. Integration & Performance Test

#### Test 5.1: Bot Startup Integration
**Objective**: Verify configuration system integrates with bot lifecycle

**Steps**:
1. Stop bot completely
2. Clear any cached data
3. Start bot and monitor startup sequence
4. Check logs for configuration service initialization
5. Verify all cogs load successfully with config service available
6. Test that other bot functions still work

**Expected Results**:
- Bot starts successfully with configuration system
- No startup errors related to configuration
- Configuration service available to all cogs
- Existing bot functionality unaffected

**Pass/Fail**: ___________

#### Test 5.2: Performance Under Load
**Objective**: Test configuration system performance

**Steps**:
1. Rapidly execute multiple `/config-get` commands (10+ in quick succession)
2. Execute `/config-set` followed immediately by `/config-get` to test cache consistency
3. Use `/config-list` with large category (shop has 20+ parameters)
4. Monitor response times and bot responsiveness

**Expected Results**:
- Read operations (config-get) are fast (<1 second)
- Write operations (config-set) complete within reasonable time
- No timeout errors on Discord interactions
- Bot remains responsive during configuration operations

**Pass/Fail**: ___________

### 6. Error Handling & Recovery Test

#### Test 6.1: Database Error Handling
**Objective**: Test behavior when database issues occur

**Steps**:
1. Temporarily corrupt a configuration value in database:
   ```sql
   UPDATE configurations SET value = 'invalid json{' WHERE key = 'elo.starting_elo';
   ```
2. Use `/config-reload`
3. Use `/config-get key:elo.starting_elo`
4. Check bot logs for error handling
5. Fix the value and test recovery

**Expected Results**:
- Invalid JSON handled gracefully without crashing
- Error logged but system continues functioning
- Other configurations still work
- Recovery works when data fixed

**Pass/Fail**: ___________

#### Test 6.2: Service Unavailability Handling
**Objective**: Test command behavior when config service unavailable

**Steps**:
1. Temporarily modify admin.py to simulate missing config_service:
   ```python
   # Comment out: config_service = getattr(self.bot, 'config_service', None)
   # Add: config_service = None
   ```
2. Test all config commands
3. Verify appropriate error messages
4. Restore service and verify recovery

**Expected Results**:
- All commands show "Configuration service not available" message
- No crashes or unhandled exceptions
- Commands gracefully degrade when service missing
- Recovery works when service restored

**Pass/Fail**: ___________

## Summary

### Overall Test Results
- Configuration Service: ___/3 tests passed
- Admin Slash Commands: ___/5 tests passed  
- Seed Data Integrity: ___/2 tests passed
- Security & Permissions: ___/2 tests passed
- Integration & Performance: ___/2 tests passed
- Error Handling & Recovery: ___/2 tests passed

**Total: ___/16 tests passed**

### Critical Issues Found
_(List any critical issues that must be fixed before deployment)_

1. ________________________________
2. ________________________________
3. ________________________________

### Minor Issues Found
_(List any minor issues for future improvement)_

1. ________________________________
2. ________________________________
3. ________________________________

### Performance Observations
_(Note any performance concerns or observations)_

1. ________________________________
2. ________________________________
3. ________________________________

### Recommendations for Next Phase
_(List any recommendations for Phase 2 implementation)_

1. ________________________________
2. ________________________________
3. ________________________________

### Ready for Next Phase?
Based on test results: **YES** / **NO**

**Required for Phase 2 readiness:**
- [ ] All configuration parameters accessible
- [ ] Admin commands working properly
- [ ] Security measures functional
- [ ] Performance acceptable for production
- [ ] Error handling robust

**Tester**: _________________ **Date**: _________

## Notes
_(Additional testing notes and observations)_

________________________________________________________
________________________________________________________
________________________________________________________