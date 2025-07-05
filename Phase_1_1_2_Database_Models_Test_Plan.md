# Phase 1.1.2 Database Models & Migration - Manual Test Plan

## Overview
Test plan for validating the Phase 1.1.2 implementation of Configuration and AuditLog database models, including schema validation, CRUD operations, and data integrity.

## Prerequisites
- Phase 1.1.1 BaseService completed
- Discord bot configured and database initialized
- SQLite browser or database client for direct inspection
- Basic understanding of SQLAlchemy models

## Test Categories

### 1. Database Schema Test

#### Test 1.1: Configuration Table Schema Validation
**Objective**: Verify Configuration table created with correct schema

**Steps**:
1. Start the bot to trigger database initialization
2. Connect to database using SQLite browser or command line
3. Inspect `configurations` table schema:
   ```sql
   .schema configurations
   ```
4. Verify column definitions and constraints

**Expected Results**:
- Table `configurations` exists
- Columns present: `key` (TEXT PRIMARY KEY), `value` (TEXT NOT NULL), `updated_at` (DATETIME)
- Primary key constraint on `key` column
- NOT NULL constraint on `value` column
- `updated_at` has default timestamp functionality

**Pass/Fail**: ___________

#### Test 1.2: AuditLog Table Schema Validation
**Objective**: Verify AuditLog table created with correct schema

**Steps**:
1. Inspect `audit_logs` table schema:
   ```sql
   .schema audit_logs
   ```
2. Verify column definitions and constraints
3. Check that auto-increment works for `id` column

**Expected Results**:
- Table `audit_logs` exists
- Columns present: `id` (INTEGER PRIMARY KEY), `user_id` (BIGINT), `action` (TEXT), `details` (TEXT), `created_at` (DATETIME)
- Auto-increment primary key on `id`
- NOT NULL constraints on required fields
- `created_at` has default timestamp functionality

**Pass/Fail**: ___________

#### Test 1.3: Foreign Key Relationships
**Objective**: Verify no unintended foreign key constraints

**Steps**:
1. Check foreign key constraints:
   ```sql
   PRAGMA foreign_key_list(configurations);
   PRAGMA foreign_key_list(audit_logs);
   ```
2. Verify tables are independent (no foreign keys to other tables)

**Expected Results**:
- No foreign key constraints on either table
- Tables can operate independently
- No cascade delete dependencies

**Pass/Fail**: ___________

### 2. Configuration Model CRUD Operations

#### Test 2.1: Configuration Model Creation
**Objective**: Test creating new Configuration records

**Steps**:
1. Create test script or use bot console:
   ```python
   from bot.database.models import Configuration
   from bot.database.database import Database
   
   db = Database()
   await db.initialize()
   
   async with db.get_session() as session:
       # Create new configuration
       config = Configuration(
           key='test.parameter',
           value='{"number": 42, "text": "hello"}'
       )
       session.add(config)
       await session.commit()
       print("Configuration created successfully")
   ```

**Expected Results**:
- Record creates without errors
- `updated_at` timestamp automatically set
- Primary key constraint prevents duplicate keys
- JSON strings stored correctly in `value` field

**Pass/Fail**: ___________

#### Test 2.2: Configuration Model Reading
**Objective**: Test querying Configuration records

**Steps**:
1. Query the test configuration:
   ```python
   from sqlalchemy import select
   
   async with db.get_session() as session:
       result = await session.execute(
           select(Configuration).where(Configuration.key == 'test.parameter')
       )
       config = result.scalar_one_or_none()
       
       if config:
           print(f"Key: {config.key}")
           print(f"Value: {config.value}")
           print(f"Updated: {config.updated_at}")
       else:
           print("Configuration not found")
   ```

**Expected Results**:
- Query returns correct record
- All fields populated correctly
- `updated_at` shows creation timestamp
- `__repr__` method shows readable output

**Pass/Fail**: ___________

#### Test 2.3: Configuration Model Updates
**Objective**: Test updating existing Configuration records

**Steps**:
1. Update the test configuration:
   ```python
   async with db.get_session() as session:
       result = await session.execute(
           select(Configuration).where(Configuration.key == 'test.parameter')
       )
       config = result.scalar_one_or_none()
       
       if config:
           old_updated = config.updated_at
           config.value = '{"number": 100, "text": "updated"}'
           await session.commit()
           
           # Re-query to check update
           await session.refresh(config)
           print(f"Old timestamp: {old_updated}")
           print(f"New timestamp: {config.updated_at}")
   ```

**Expected Results**:
- Update succeeds without errors
- `updated_at` timestamp changes automatically
- New `value` persisted correctly
- Old timestamp different from new timestamp

**Pass/Fail**: ___________

#### Test 2.4: Configuration Model Deletion
**Objective**: Test deleting Configuration records

**Steps**:
1. Delete the test configuration:
   ```python
   async with db.get_session() as session:
       result = await session.execute(
           select(Configuration).where(Configuration.key == 'test.parameter')
       )
       config = result.scalar_one_or_none()
       
       if config:
           await session.delete(config)
           await session.commit()
           print("Configuration deleted")
       
       # Verify deletion
       result = await session.execute(
           select(Configuration).where(Configuration.key == 'test.parameter')
       )
       deleted_config = result.scalar_one_or_none()
       print(f"After deletion: {deleted_config}")
   ```

**Expected Results**:
- Deletion succeeds without errors
- Record no longer exists in database
- No orphaned data or foreign key issues
- Query returns None after deletion

**Pass/Fail**: ___________

### 3. AuditLog Model Operations

#### Test 3.1: AuditLog Model Creation
**Objective**: Test creating new AuditLog records

**Steps**:
1. Create test audit log entry:
   ```python
   from bot.database.models import AuditLog
   import json
   
   async with db.get_session() as session:
       audit = AuditLog(
           user_id=123456789,
           action='test_action',
           details=json.dumps({
               'test': 'data',
               'number': 42,
               'change': 'created test record'
           })
       )
       session.add(audit)
       await session.commit()
       
       print(f"Audit log created with ID: {audit.id}")
   ```

**Expected Results**:
- Record creates successfully
- Auto-increment `id` assigned
- `created_at` timestamp automatically set
- `user_id` stored as BIGINT (Discord ID compatible)
- Complex JSON data stored in `details`

**Pass/Fail**: ___________

#### Test 3.2: AuditLog Model Querying
**Objective**: Test querying AuditLog records

**Steps**:
1. Query audit logs:
   ```python
   async with db.get_session() as session:
       # Query by user_id
       result = await session.execute(
           select(AuditLog).where(AuditLog.user_id == 123456789)
       )
       user_logs = result.scalars().all()
       
       # Query by action
       result = await session.execute(
           select(AuditLog).where(AuditLog.action == 'test_action')
       )
       action_logs = result.scalars().all()
       
       # Query recent logs
       result = await session.execute(
           select(AuditLog).order_by(AuditLog.created_at.desc()).limit(5)
       )
       recent_logs = result.scalars().all()
       
       print(f"User logs: {len(user_logs)}")
       print(f"Action logs: {len(action_logs)}")
       print(f"Recent logs: {len(recent_logs)}")
   ```

**Expected Results**:
- Queries by `user_id` work correctly
- Queries by `action` work correctly  
- Ordering by `created_at` works correctly
- All query patterns return expected results

**Pass/Fail**: ___________

#### Test 3.3: AuditLog JSON Data Handling
**Objective**: Test complex JSON storage and retrieval in details field

**Steps**:
1. Create audit log with complex JSON:
   ```python
   complex_data = {
       'old_value': {'config': 'old', 'numbers': [1, 2, 3]},
       'new_value': {'config': 'new', 'numbers': [4, 5, 6]},
       'metadata': {
           'timestamp': '2024-01-01T00:00:00Z',
           'source': 'api',
           'nested': {'deep': {'value': True}}
       }
   }
   
   async with db.get_session() as session:
       audit = AuditLog(
           user_id=987654321,
           action='complex_test',
           details=json.dumps(complex_data)
       )
       session.add(audit)
       await session.commit()
       
       # Retrieve and parse
       result = await session.execute(
           select(AuditLog).where(AuditLog.action == 'complex_test')
       )
       retrieved = result.scalar_one()
       parsed_details = json.loads(retrieved.details)
       
       print(f"Original: {complex_data}")
       print(f"Retrieved: {parsed_details}")
       print(f"Match: {complex_data == parsed_details}")
   ```

**Expected Results**:
- Complex JSON data stores without corruption
- Retrieved data matches original exactly
- Nested objects and arrays preserved
- No data loss during JSON serialization/deserialization

**Pass/Fail**: ___________

### 4. Data Integrity & Constraints Test

#### Test 4.1: Primary Key Constraints
**Objective**: Test primary key uniqueness constraints

**Steps**:
1. Attempt to create duplicate Configuration key:
   ```python
   async with db.get_session() as session:
       try:
           config1 = Configuration(key='duplicate.test', value='{"first": true}')
           session.add(config1)
           await session.commit()
           
           config2 = Configuration(key='duplicate.test', value='{"second": true}')
           session.add(config2)
           await session.commit()
           
           print("ERROR: Duplicate key allowed!")
       except Exception as e:
           print(f"Constraint working: {type(e).__name__}")
           await session.rollback()
   ```

**Expected Results**:
- Duplicate key insertion fails
- Appropriate database constraint error raised
- Session rollback works correctly
- First record remains intact

**Pass/Fail**: ___________

#### Test 4.2: NOT NULL Constraints  
**Objective**: Test NOT NULL constraints on required fields

**Steps**:
1. Attempt to create Configuration with NULL value:
   ```python
   async with db.get_session() as session:
       try:
           config = Configuration(key='null.test', value=None)
           session.add(config)
           await session.commit()
           print("ERROR: NULL value allowed!")
       except Exception as e:
           print(f"NOT NULL constraint working: {type(e).__name__}")
           await session.rollback()
   ```
2. Test AuditLog required fields similarly

**Expected Results**:
- NULL values rejected for NOT NULL columns
- Appropriate constraint errors raised
- Database integrity maintained

**Pass/Fail**: ___________

#### Test 4.3: Data Type Validation
**Objective**: Test data type constraints and validation

**Steps**:
1. Test Configuration key length limits:
   ```python
   async with db.get_session() as session:
       try:
           # Test very long key (over 255 characters)
           long_key = 'x' * 300
           config = Configuration(key=long_key, value='{"test": true}')
           session.add(config)
           await session.commit()
           print("Long key behavior:")
       except Exception as e:
           print(f"Key length limit: {type(e).__name__}")
           await session.rollback()
   ```

2. Test AuditLog user_id with large Discord ID:
   ```python
   async with db.get_session() as session:
       audit = AuditLog(
           user_id=999999999999999999,  # Large Discord ID
           action='bigint_test',
           details='{"test": "large_id"}'
       )
       session.add(audit)
       await session.commit()
       print(f"Large user_id stored: {audit.user_id}")
   ```

**Expected Results**:
- Key length constraints enforced appropriately
- BIGINT handles large Discord IDs correctly
- Data type validation works as expected

**Pass/Fail**: ___________

### 5. Performance & Scalability Test

#### Test 5.1: Bulk Operations Performance
**Objective**: Test performance with multiple records

**Steps**:
1. Create multiple Configuration records:
   ```python
   import time
   
   start_time = time.time()
   
   async with db.get_session() as session:
       for i in range(100):
           config = Configuration(
               key=f'perf.test.{i}',
               value=f'{{"index": {i}, "data": "test_data_{i}"}}'
           )
           session.add(config)
       await session.commit()
   
   end_time = time.time()
   print(f"Created 100 configurations in {end_time - start_time:.2f} seconds")
   ```

2. Query performance test:
   ```python
   start_time = time.time()
   
   async with db.get_session() as session:
       result = await session.execute(select(Configuration))
       all_configs = result.scalars().all()
       
   end_time = time.time()
   print(f"Queried {len(all_configs)} configurations in {end_time - start_time:.2f} seconds")
   ```

**Expected Results**:
- Bulk creation completes in reasonable time (<5 seconds)
- Query operations remain fast (<1 second)
- Memory usage reasonable
- No performance degradation with moderate record counts

**Pass/Fail**: ___________

#### Test 5.2: Concurrent Access Test
**Objective**: Test concurrent database operations

**Steps**:
1. Create test for concurrent writes:
   ```python
   import asyncio
   
   async def create_config(index):
       db_instance = Database()
       await db_instance.initialize()
       async with db_instance.get_session() as session:
           config = Configuration(
               key=f'concurrent.test.{index}',
               value=f'{{"thread": {index}}}'
           )
           session.add(config)
           await session.commit()
           return f"Created config {index}"
   
   # Run concurrent operations
   tasks = [create_config(i) for i in range(10)]
   results = await asyncio.gather(*tasks, return_exceptions=True)
   
   print(f"Concurrent operations completed: {len(results)}")
   for i, result in enumerate(results):
       if isinstance(result, Exception):
           print(f"Task {i} failed: {result}")
       else:
           print(f"Task {i}: {result}")
   ```

**Expected Results**:
- Concurrent operations complete successfully
- No database corruption or deadlocks
- All records created correctly
- No race conditions in record creation

**Pass/Fail**: ___________

### 6. Error Handling & Recovery Test

#### Test 6.1: Database Connection Error Handling
**Objective**: Test behavior when database is unavailable

**Steps**:
1. Temporarily break database connection (rename database file)
2. Attempt to create Configuration record
3. Test error handling and recovery
4. Restore database connection

**Expected Results**:
- Appropriate error raised when database unavailable
- No unhandled exceptions crash the application
- Recovery works when database restored
- Graceful degradation of functionality

**Pass/Fail**: ___________

#### Test 6.2: Transaction Rollback Test
**Objective**: Test transaction rollback on errors

**Steps**:
1. Create test with intentional error:
   ```python
   async with db.get_session() as session:
       try:
           # Create valid record
           config1 = Configuration(key='rollback.test1', value='{"valid": true}')
           session.add(config1)
           
           # Create invalid record (duplicate key or constraint violation)
           config2 = Configuration(key='rollback.test1', value='{"duplicate": true}')
           session.add(config2)
           
           await session.commit()
       except Exception as e:
           print(f"Error caught: {type(e).__name__}")
           await session.rollback()
           
       # Verify rollback - should find no records
       result = await session.execute(
           select(Configuration).where(Configuration.key.like('rollback.test%'))
       )
       rollback_configs = result.scalars().all()
       print(f"Records after rollback: {len(rollback_configs)}")
   ```

**Expected Results**:
- Transaction rolls back completely on error
- No partial commits occur
- Database remains in consistent state
- All changes in failed transaction are undone

**Pass/Fail**: ___________

## Summary

### Overall Test Results
- Database Schema: ___/3 tests passed
- Configuration Model CRUD: ___/4 tests passed  
- AuditLog Model Operations: ___/3 tests passed
- Data Integrity & Constraints: ___/3 tests passed
- Performance & Scalability: ___/2 tests passed
- Error Handling & Recovery: ___/2 tests passed

**Total: ___/17 tests passed**

### Critical Issues Found
_(List any critical issues that prevent production deployment)_

1. ________________________________
2. ________________________________
3. ________________________________

### Schema Issues Found
_(List any database schema problems)_

1. ________________________________
2. ________________________________
3. ________________________________

### Performance Issues Found
_(List any performance concerns)_

1. ________________________________
2. ________________________________
3. ________________________________

### Recommendations
_(List recommendations for improvements)_

1. ________________________________
2. ________________________________
3. ________________________________

### Ready for Phase 1.1.3?
Based on test results: **YES** / **NO**

**Required for next phase:**
- [ ] Configuration table schema correct
- [ ] AuditLog table schema correct
- [ ] CRUD operations working
- [ ] Data integrity constraints enforced
- [ ] Performance acceptable
- [ ] Error handling robust

**Tester**: _________________ **Date**: _________

## Notes
_(Additional testing notes and observations)_

________________________________________________________
________________________________________________________
________________________________________________________