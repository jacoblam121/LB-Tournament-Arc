# 🚀 Phase 2A1 Migration Execution Guide

## ⚡ Quick Summary

The **Game→Event migration** has been corrected after critical code review findings. Follow this exact sequence to safely migrate your tournament bot.

## 🚨 CRITICAL FIXES APPLIED

- ✅ **Migration script now performs actual SQL operations** (not just analysis)
- ✅ **Proper 3-step migration process** with backup and rollback
- ✅ **Schema changes applied in correct order** (migration before model updates)
- ✅ **Comprehensive test suite** for each migration stage
- ✅ **Emergency rollback capability** with automatic backup

---

## 📋 Step-by-Step Execution

### **Step 1: Pre-Migration Testing**
```bash
# Test current state (should pass)
python test_migration_corrected.py pre
```
**Expected Result:** All tests pass, confirms game_id structure exists

### **Step 2: Run Database Migration**
```bash
# Perform the actual migration (creates backup automatically)
python migration_game_to_event_fixed.py
```
**What this does:**
- Creates automatic database backup
- Adds `event_id` column to challenges table
- Migrates all data from `game_id` to `event_id`
- Validates data integrity
- Creates emergency rollback script

### **Step 3: Post-Migration Testing**
```bash
# Test migration success (should pass)
python test_migration_corrected.py post-migration
```
**Expected Result:** All tests pass, confirms both `game_id` and `event_id` exist

### **Step 4: Apply Model Updates**
```bash
# Update code to use event_id (creates backup automatically)
python phase2_model_updates.py
```
**What this does:**
- Updates Challenge model to use `event_id`
- Updates database operations
- Fixes test references
- Creates code backup

### **Step 5: Final Testing**
```bash
# Test final functionality (should pass)
python test_migration_corrected.py post-update
```
**Expected Result:** All tests pass, confirms event-based challenges work

### **Step 6: Verify Original Functionality**
```bash
# Run original test suite to ensure nothing broke
python tests/test_foundation.py
python manual_test.py
```

---

## 🔄 Migration Process Details

### **Safe 3-Step Migration:**
1. **Add Column**: `ALTER TABLE challenges ADD COLUMN event_id INTEGER`
2. **Migrate Data**: `UPDATE challenges SET event_id = ? WHERE game_id = ?`
3. **Validate**: Ensure all `event_id` references are valid

### **Automatic Backups Created:**
- `backup_pre_migration_[timestamp]_tournament.db` - Database backup
- `backup_pre_phase2_[timestamp]/` - Code backups
- `emergency_rollback_[timestamp].sh` - Emergency recovery script

### **Game→Event Mapping Logic:**
- Exact name matches first
- Partial name matches second  
- Creates new Events in "Legacy" cluster for unmapped Games
- Preserves all existing challenge data

---

## 🚨 Emergency Recovery

If anything goes wrong:

### **Database Recovery:**
```bash
# Run the generated rollback script
./emergency_rollback_[timestamp].sh
```

### **Code Recovery:**
```bash
# Restore from code backup
cp backup_pre_phase2_[timestamp]/bot_database_models.py bot/database/models.py
cp backup_pre_phase2_[timestamp]/bot_database_database.py bot/database/database.py
cp backup_pre_phase2_[timestamp]/manual_test.py manual_test.py
```

---

## ✅ Success Criteria

After completion, you should have:

- ✅ All challenges use `event_id` instead of `game_id`
- ✅ Challenge model updated to use Event relationships
- ✅ Database operations use event-based parameters
- ✅ All existing functionality preserved
- ✅ No data loss (verified by tests)
- ✅ Ready for Phase 2B (N-player challenges)

---

## 📊 Expected Test Results

### Pre-Migration (`pre`):
```
✅ PASS - Games exist (Found X games)
✅ PASS - Events exist (Found Y events) 
✅ PASS - Challenges have game_id column
✅ PASS - Challenges DON'T have event_id column
✅ PASS - Pre-migration challenge creation
✅ PASS - Pre-migration Game relationship
```

### Post-Migration (`post-migration`):
```
✅ PASS - Challenges still have game_id column
✅ PASS - Challenges now have event_id column
✅ PASS - All challenges have event_id (0 NULL values)
✅ PASS - Event references are valid (X/X valid)
```

### Post-Update (`post-update`):
```
✅ PASS - Challenge creation with event_id
✅ PASS - Challenge-Event relationship
✅ PASS - Challenge workflow completion
✅ PASS - Elo calculations
```

---

## 🎯 What's Next After Success

1. **Phase 2B**: Implement Match/MatchParticipant separation
2. **Phase 2C**: Add multi-player scoring strategies
3. **Phase 2D**: Build FFA and Team challenge support

---

## 🔧 Troubleshooting

### "Column already exists" error:
- Migration is idempotent - safe to re-run
- Check `post-migration` tests to verify state

### "No matching Event found" warnings:
- Normal - script creates Events for unmapped Games
- Check final mapping in success report

### Test failures:
- **STOP immediately** - don't proceed to next step
- Use rollback scripts to restore
- Report specific test failure for analysis

---

Ready to begin? Start with **Step 1** above! 🚀