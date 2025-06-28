# Phase 2.1 Challenge Model Fix - Test Suite

## Overview
This test suite verifies that the Challenge model fix resolves the critical model-database mismatch while preserving all essential functionality for the N-player architecture.

## Background
**Issue Fixed**: Challenge model referenced `challenger_id` and `challenged_id` columns that were removed from the database in Phase 1.3, causing runtime errors.

**Solution Applied**: Surgical removal of legacy 2-player fields while preserving N-player architecture via ChallengeParticipant table.

## Test Environment Setup

1. **Ensure database is current**:
   ```bash
   # Verify Phase 1.3 schema is in place
   sqlite3 tournament.db "PRAGMA table_info(challenges);" | wc -l
   # Expected: 17 (17 columns total, no challenger_id/challenged_id)
   ```

2. **Ensure bot code is updated**:
   ```bash
   # Check that model changes are in place
   grep -c "challenger_id" bot/database/models.py
   # Expected: 0 (no references to challenger_id)
   ```

## Test Suite

### Test 1: Model Import and Reflection ✅

**Purpose**: Verify SQLAlchemy can load models without database reflection errors.

**Instructions**:
1. Run Python test:
   ```bash
   python -c "
   import sys
   sys.path.append('bot')
   try:
       from bot.database.models import Challenge, Player, ChallengeParticipant
       print('✅ PASS: All models import successfully')
   except Exception as e:
       print(f'❌ FAIL: Model import error: {e}')
       exit(1)
   "
   ```

**Expected Result**: 
- ✅ `PASS: All models import successfully`
- **No SQLAlchemy reflection errors**

### Test 2: Model Relationship Validation ✅

**Purpose**: Confirm legacy relationships removed and N-player relationships preserved.

**Instructions**:
1. Run relationship validation:
   ```bash
   python -c "
   import sys
   sys.path.append('bot')
   from bot.database.models import Challenge, Player
   
   # Test removed relationships
   tests = [
       ('Challenge.challenger', not hasattr(Challenge, 'challenger'), 'Legacy challenger relationship removed'),
       ('Challenge.challenged', not hasattr(Challenge, 'challenged'), 'Legacy challenged relationship removed'),
       ('Player.sent_challenges', not hasattr(Player, 'sent_challenges'), 'Legacy sent_challenges relationship removed'),
       ('Player.received_challenges', not hasattr(Player, 'received_challenges'), 'Legacy received_challenges relationship removed'),
       ('Challenge.participants', hasattr(Challenge, 'participants'), 'N-player participants relationship preserved'),
       ('Challenge.event', hasattr(Challenge, 'event'), 'Event relationship preserved')
   ]
   
   all_passed = True
   for test_name, condition, description in tests:
       if condition:
           print(f'✅ PASS: {description}')
       else:
           print(f'❌ FAIL: {description}')
           all_passed = False
   
   if all_passed:
       print('✅ ALL RELATIONSHIP TESTS PASSED')
   else:
       exit(1)
   "
   ```

**Expected Results**:
- ✅ `PASS: Legacy challenger relationship removed`
- ✅ `PASS: Legacy challenged relationship removed`  
- ✅ `PASS: Legacy sent_challenges relationship removed`
- ✅ `PASS: Legacy received_challenges relationship removed`
- ✅ `PASS: N-player participants relationship preserved`
- ✅ `PASS: Event relationship preserved`
- ✅ `ALL RELATIONSHIP TESTS PASSED`

### Test 3: Bot Startup Validation ✅

**Purpose**: Verify bot can start without SQLAlchemy errors from model changes.

**Instructions**:
1. Start the bot:
   ```bash
   timeout 30s python -m bot.main 2>&1 | head -20
   ```

2. Look for these success indicators:
   - `Database initialized successfully`
   - `MatchCommandsCog: All operations initialized successfully`
   - Bot shows as online in Discord
   - **No SQLAlchemy AttributeError or reflection errors**

**Expected Results**:
- ✅ Bot starts successfully
- ✅ Database initializes without errors
- ✅ All cogs load successfully
- ✅ No model-related errors in logs

### Test 4: Challenge Model Properties ✅

**Purpose**: Verify Challenge model methods and properties work correctly.

**Instructions**:
1. Test Challenge model instantiation and methods:
   ```bash
   python -c "
   import sys
   sys.path.append('bot')
   from bot.database.models import Challenge, ChallengeStatus
   from datetime import datetime, timedelta
   
   # Test model instantiation
   try:
       challenge = Challenge(
           event_id=1,
           status=ChallengeStatus.PENDING,
           created_at=datetime.utcnow(),
           expires_at=datetime.utcnow() + timedelta(hours=24)
       )
       print('✅ PASS: Challenge model instantiation works')
       
       # Test properties
       print(f'✅ PASS: is_active property: {challenge.is_active}')
       print(f'✅ PASS: is_expired property: {challenge.is_expired}')
       
       # Test __repr__ method
       repr_str = repr(challenge)
       if 'event_id=1' in repr_str and 'status=pending' in repr_str:
           print('✅ PASS: __repr__ method updated correctly')
       else:
           print(f'❌ FAIL: __repr__ method issue: {repr_str}')
           exit(1)
           
   except Exception as e:
       print(f'❌ FAIL: Challenge model error: {e}')
       exit(1)
   "
   ```

**Expected Results**:
- ✅ `PASS: Challenge model instantiation works`
- ✅ `PASS: is_active property: True`
- ✅ `PASS: is_expired property: False`
- ✅ `PASS: __repr__ method updated correctly`

### Test 5: Database Schema Alignment ✅

**Purpose**: Confirm model fields match actual database schema.

**Instructions**:
1. Compare model fields to database:
   ```bash
   python -c "
   import sys
   sys.path.append('bot')
   from bot.database.models import Challenge
   import sqlite3
   
   # Get model columns
   model_columns = set(c.name for c in Challenge.__table__.columns)
   
   # Get database columns
   conn = sqlite3.connect('tournament.db')
   cursor = conn.execute('PRAGMA table_info(challenges);')
   db_columns = set(row[1] for row in cursor.fetchall())
   conn.close()
   
   print(f'Model columns ({len(model_columns)}): {sorted(model_columns)}')
   print(f'Database columns ({len(db_columns)}): {sorted(db_columns)}')
   
   # Check alignment
   missing_in_model = db_columns - model_columns
   missing_in_db = model_columns - db_columns
   
   if missing_in_model:
       print(f'❌ FAIL: Columns in DB but not model: {missing_in_model}')
       exit(1)
   if missing_in_db:
       print(f'❌ FAIL: Columns in model but not DB: {missing_in_db}')
       exit(1)
       
   print('✅ PASS: Model and database schemas perfectly aligned')
   "
   ```

**Expected Results**:
- ✅ Model and database both have exactly **17 columns**
- ✅ `PASS: Model and database schemas perfectly aligned`
- ✅ No missing columns in either direction

## Test Results Documentation

### Test Execution Summary
- **Test 1 - Model Import**: ⬜ PASS / ⬜ FAIL
- **Test 2 - Relationships**: ⬜ PASS / ⬜ FAIL  
- **Test 3 - Bot Startup**: ⬜ PASS / ⬜ FAIL
- **Test 4 - Model Properties**: ⬜ PASS / ⬜ FAIL
- **Test 5 - Schema Alignment**: ⬜ PASS / ⬜ FAIL

### Overall Status
- **Total Tests**: 5
- **Tests Passed**: ___/5
- **Tests Failed**: ___/5
- **Phase 2.1 Model Fix Status**: ⬜ READY FOR NEXT PHASE / ⬜ NEEDS FIXES

## Troubleshooting

### Common Issues

**Issue**: `AttributeError: 'Challenge' object has no attribute 'challenger_id'`
- **Cause**: Old code still referencing removed fields
- **Fix**: Search codebase for `challenger_id` references and update

**Issue**: `sqlalchemy.exc.OperationalError: no such column: challenges.challenger_id`
- **Cause**: Database and model mismatch
- **Fix**: Verify Phase 1.3 migration completed successfully

**Issue**: Bot startup fails with relationship errors
- **Cause**: Cached SQLAlchemy metadata
- **Fix**: Restart Python interpreter and retry

### Success Criteria

All tests must pass to proceed to **Phase 2.2: Create ChallengeOperations Service**.

---

**Test Suite Created By**: Claude Code Assistant  
**Date**: December 27, 2025  
**Phase**: 2.1 Challenge Model Fix  
**Next Phase**: 2.2 ChallengeOperations Service Creation