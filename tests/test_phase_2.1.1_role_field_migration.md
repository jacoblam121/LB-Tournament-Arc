# Phase 2.1.1 Test Suite - Role Field Migration

This test suite validates the addition of the role field to the ChallengeParticipant model and the associated migration.

## Prerequisites

- Ensure you have a backup of your database before testing
- The bot should NOT be running during migration
- Working directory should be `/home/jacob/LB-Tournament-Arc`

## Test 1: Model Updates Verification

**Purpose**: Verify that model changes are correctly implemented

**Steps**:
```bash
# Test that models.py imports without errors
python -c "from bot.database.models import ChallengeRole, ChallengeParticipant; print('✅ Models import successful')"

# Verify ChallengeRole enum values
python -c "
from bot.database.models import ChallengeRole
print(f'Challenger value: {ChallengeRole.CHALLENGER.value}')
print(f'Challenged value: {ChallengeRole.CHALLENGED.value}')
assert ChallengeRole.CHALLENGER.value == 'challenger', 'Challenger value incorrect'
assert ChallengeRole.CHALLENGED.value == 'challenged', 'Challenged value incorrect'
print('✅ ChallengeRole enum values correct')
"

# Verify role field exists in ChallengeParticipant
python -c "
from bot.database.models import ChallengeParticipant
import inspect
fields = [name for name, _ in inspect.getmembers(ChallengeParticipant) if not name.startswith('_')]
assert 'role' in fields, 'Role field not found in ChallengeParticipant'
print('✅ Role field exists in ChallengeParticipant model')
"
```

**Expected Result**: All imports succeed and verifications pass

## Test 2: Pre-Migration Database Check

**Purpose**: Verify database state before migration

**Steps**:
```bash
# Check current challenge_participants schema
sqlite3 tournament.db "PRAGMA table_info(challenge_participants);"

# Count existing challenge participants (if any)
sqlite3 tournament.db "SELECT COUNT(*) as total FROM challenge_participants;"

# Verify role column doesn't exist yet
sqlite3 tournament.db "SELECT role FROM challenge_participants LIMIT 1;" 2>&1 | grep -q "no such column" && echo "✅ Role column doesn't exist (expected)" || echo "❌ Role column already exists"
```

**Expected Result**: 
- Schema shows 7 columns (no role column)
- Error message confirms role column doesn't exist

## Test 3: Run Migration

**Purpose**: Execute the migration script

**Steps**:
```bash
# Run the migration
python migration_phase_2_1_1_add_role_field.py

# Check for backup file creation
ls -la tournament_backup_phase_2_1_1_*.db

# Check for rollback script creation
ls -la rollback_phase_2_1_1_*.sh
```

**Expected Result**:
- Migration completes with "✅ PHASE 2.1.1 MIGRATION COMPLETE"
- Backup file exists with current timestamp
- Rollback script exists and is executable

## Test 4: Post-Migration Verification

**Purpose**: Verify database changes after migration

**Steps**:
```bash
# Check updated schema
sqlite3 tournament.db "PRAGMA table_info(challenge_participants);"

# Verify role column exists and check values
sqlite3 tournament.db "SELECT DISTINCT role FROM challenge_participants;"

# Check role distribution
sqlite3 tournament.db "SELECT role, COUNT(*) as count FROM challenge_participants GROUP BY role;"

# Verify no NULL roles
sqlite3 tournament.db "SELECT COUNT(*) FROM challenge_participants WHERE role IS NULL;"
```

**Expected Result**:
- Schema shows 8 columns (role column added)
- Role values are 'challenger' and 'challenged'
- Each challenge has exactly one 'challenger'
- Zero NULL role values

## Test 5: Bot Startup Test

**Purpose**: Ensure the bot starts correctly with model changes

**Steps**:
```bash
# Test bot startup (let it run for 10 seconds then stop)
timeout 10 python -m bot.main || true

# Check logs for any SQLAlchemy errors
tail -20 logs/tournament_bot_*.log | grep -i "error\|exception" || echo "✅ No errors in logs"
```

**Expected Result**: 
- Bot starts without SQLAlchemy errors
- No model-related exceptions in logs

## Test 6: Migration Idempotency

**Purpose**: Verify migration can be safely run multiple times

**Steps**:
```bash
# Run migration again
python migration_phase_2_1_1_add_role_field.py

# Check output
# Should see: "ℹ️  Migration already applied - role column exists"
```

**Expected Result**: Migration detects it's already applied and exits safely

## Test Summary

Run all tests in order. All 6 tests should pass:

- [ ] Test 1: Model imports and enum values ✅
- [ ] Test 2: Pre-migration database state ✅
- [ ] Test 3: Migration execution ✅
- [ ] Test 4: Post-migration verification ✅
- [ ] Test 5: Bot startup compatibility ✅
- [ ] Test 6: Migration idempotency ✅

## Rollback Procedure (if needed)

If any issues occur, you can rollback:

```bash
# Use the generated rollback script
./rollback_phase_2_1_1_[timestamp].sh

# Or restore from backup
cp tournament_backup_phase_2_1_1_[timestamp].db tournament.db
```

## Next Steps

After all tests pass:
1. The system is ready for Phase 2.2 implementation
2. Update models.py to enforce NOT NULL at application level (after sufficient testing)
3. Implement ChallengeOperations service with role awareness