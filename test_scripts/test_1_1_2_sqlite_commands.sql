-- Phase 1.1.2 Database Models Testing - SQLite Commands
-- Run these commands in sqlite3 terminal to test database schema and operations

-- ===== DATABASE SCHEMA TESTS =====

-- Test 1.1: Configuration Table Schema Validation
.schema configurations

-- Expected output should show:
-- CREATE TABLE configurations (
--     key VARCHAR(255) NOT NULL, 
--     value TEXT NOT NULL, 
--     updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP), 
--     PRIMARY KEY (key)
-- );

-- Test 1.2: AuditLog Table Schema Validation  
.schema audit_logs

-- Expected output should show:
-- CREATE TABLE audit_logs (
--     id INTEGER NOT NULL, 
--     user_id BIGINT NOT NULL, 
--     action VARCHAR(50) NOT NULL, 
--     details TEXT, 
--     created_at DATETIME DEFAULT (CURRENT_TIMESTAMP), 
--     PRIMARY KEY (id)
-- );

-- Test 1.3: Foreign Key Relationships
PRAGMA foreign_key_list(configurations);
PRAGMA foreign_key_list(audit_logs);

-- Expected: No foreign key constraints (empty results)

-- ===== CONFIGURATION MODEL CRUD TESTS =====

-- Test 2.1: Configuration Model Creation
INSERT INTO configurations (key, value) VALUES ('test.parameter', '{"number": 42, "text": "hello"}');
SELECT * FROM configurations WHERE key = 'test.parameter';

-- Test 2.2: Configuration Model Reading
SELECT key, value, updated_at FROM configurations WHERE key = 'test.parameter';

-- Test 2.3: Configuration Model Updates
UPDATE configurations SET value = '{"number": 100, "text": "updated"}' WHERE key = 'test.parameter';
SELECT key, value, updated_at FROM configurations WHERE key = 'test.parameter';

-- Test 2.4: Configuration Model Deletion
DELETE FROM configurations WHERE key = 'test.parameter';
SELECT * FROM configurations WHERE key = 'test.parameter';

-- ===== AUDITLOG MODEL TESTS =====

-- Test 3.1: AuditLog Model Creation
INSERT INTO audit_logs (user_id, action, details) VALUES 
(123456789, 'test_action', '{"test": "data", "number": 42, "change": "created test record"}');
SELECT * FROM audit_logs WHERE action = 'test_action';

-- Test 3.2: AuditLog Model Querying
-- Query by user_id
SELECT * FROM audit_logs WHERE user_id = 123456789;

-- Query by action
SELECT * FROM audit_logs WHERE action = 'test_action';

-- Query recent logs
SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 5;

-- Test 3.3: AuditLog JSON Data Handling
INSERT INTO audit_logs (user_id, action, details) VALUES 
(987654321, 'complex_test', '{"old_value": {"config": "old", "numbers": [1, 2, 3]}, "new_value": {"config": "new", "numbers": [4, 5, 6]}, "metadata": {"timestamp": "2024-01-01T00:00:00Z", "source": "api", "nested": {"deep": {"value": true}}}}');
SELECT details FROM audit_logs WHERE action = 'complex_test';

-- ===== DATA INTEGRITY TESTS =====

-- Test 4.1: Primary Key Constraints
-- This should succeed:
INSERT INTO configurations (key, value) VALUES ('duplicate.test', '{"first": true}');

-- This should fail with constraint error:
INSERT INTO configurations (key, value) VALUES ('duplicate.test', '{"second": true}');

-- Clean up
DELETE FROM configurations WHERE key = 'duplicate.test';

-- Test 4.2: NOT NULL Constraints
-- This should fail:
INSERT INTO configurations (key, value) VALUES ('null.test', NULL);

-- Test 4.3: Data Type Validation
-- Test very long key (this may succeed or fail depending on SQLite settings)
INSERT INTO configurations (key, value) VALUES ('x123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345', '{"test": true}');

-- Test large Discord ID in AuditLog
INSERT INTO audit_logs (user_id, action, details) VALUES 
(999999999999999999, 'bigint_test', '{"test": "large_id"}');
SELECT user_id FROM audit_logs WHERE action = 'bigint_test';

-- ===== PERFORMANCE TESTS =====

-- Test 5.1: Bulk Operations Performance
-- Create 100 test configurations
INSERT INTO configurations (key, value) VALUES 
('perf.test.1', '{"index": 1, "data": "test_data_1"}'),
('perf.test.2', '{"index": 2, "data": "test_data_2"}'),
('perf.test.3', '{"index": 3, "data": "test_data_3"}'),
('perf.test.4', '{"index": 4, "data": "test_data_4"}'),
('perf.test.5', '{"index": 5, "data": "test_data_5"}');
-- Continue pattern or use script for full 100...

-- Query all configurations
SELECT COUNT(*) FROM configurations;
SELECT * FROM configurations LIMIT 10;

-- ===== CLEANUP =====

-- Clean up test data
DELETE FROM configurations WHERE key LIKE 'test.%';
DELETE FROM configurations WHERE key LIKE 'perf.test.%';
DELETE FROM configurations WHERE key LIKE 'duplicate.%';
DELETE FROM configurations WHERE key LIKE 'null.%';
DELETE FROM audit_logs WHERE action IN ('test_action', 'complex_test', 'bigint_test');

-- Verify cleanup
SELECT COUNT(*) FROM configurations;
SELECT COUNT(*) FROM audit_logs;