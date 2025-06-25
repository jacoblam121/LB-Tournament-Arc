# Manual Testing Guide

## 🧪 Comprehensive Manual Test Suite

This interactive test suite verifies all Phase 1 foundation components of the Tournament Bot.

### Quick Start

```bash
# Run the test suite
./run_manual_tests.sh

# Or run directly with Python
source venv/bin/activate
python3 manual_test.py
```

### Features

#### 🎯 **Interactive Menu System**
- Choose individual tests or run all tests
- Configurable test options
- Real-time results with colored output
- Comprehensive test summaries

#### 🔧 **Configurable Options**
- **Use Test Database**: Creates isolated test DB (`manual_test_tournament.db`)
- **Cleanup After Test**: Automatically removes test data when done
- **Verbose Output**: Shows detailed information during tests
- **Simulate Discord Data**: Uses test Discord IDs for safe testing

#### 📋 **Available Tests**

1. **Configuration System**
   - Validates all config attributes
   - Tests environment variable loading
   - Verifies validation logic

2. **Elo Calculations**
   - Tests expected score calculations
   - Validates K-factor selection (provisional vs standard)
   - Simulates various match scenarios
   - Verifies tier system (Beginner → Grandmaster)

3. **Database Operations**
   - Tests game loading and retrieval
   - Player creation and lookup
   - Leaderboard generation
   - CRUD operations validation

4. **Challenge System**
   - Challenge creation and retrieval
   - Status updates (pending → accepted → completed)
   - Active challenge queries
   - Foreign key relationships

5. **Match Simulation**
   - End-to-end match workflow
   - Elo change calculations and recording
   - Challenge completion
   - Result validation

6. **Player Statistics**
   - Comprehensive player stats retrieval
   - Recent match history
   - Elo history tracking
   - Calculated fields validation

7. **Data Integrity**
   - Foreign key relationship verification
   - Data consistency checks
   - Match count validation
   - Win rate calculation accuracy

### Test Results

The test suite provides detailed feedback:

- ✅ **Success**: Test passed with expected results
- ❌ **Error**: Test failed with specific error details
- ⚠️ **Warning**: Non-critical issues detected
- ℹ️ **Info**: Additional context and details

### Example Output

```
════════════════════════════════════════════════════════════
                    Testing Elo Calculation System
════════════════════════════════════════════════════════════
ℹ️  Testing: Equal ratings, Player 1 wins
  P1: 1000 (Novice) -> 1020 (+20)
  P2: 1000 (Novice) -> 990 (-10)
  Expected P1 score: 0.500 | K-factors: 40, 20
✅ Elo changes correct for P1 win

ℹ️  Testing tier system:
  800 Elo: 🌱 Beginner
  1200 Elo: 🌟 Novice
  1400 Elo: 🔥 Intermediate
  1600 Elo: ⭐ Advanced
  1800 Elo: 🏆 Expert
  2000 Elo: 💎 Master
  2200 Elo: 👑 Grandmaster
✅ Elo calculation tests completed
```

### Safety Features

- **Isolated Testing**: Uses separate test database by default
- **Automatic Cleanup**: Removes test data after completion
- **No Production Impact**: Never touches production data
- **Rollback Support**: Database transactions ensure consistency

### Test Data

The suite creates realistic test data:
- 3 test players with unique Discord IDs
- Sample challenges between players
- Simulated match results with Elo changes
- Complete match history and statistics

### Troubleshooting

**Import Errors:**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Install missing dependencies
pip install -r requirements.txt
```

**Database Errors:**
- Test uses isolated database (`manual_test_tournament.db`)
- Automatically cleaned up unless configured otherwise
- No impact on production database

**Permission Errors:**
```bash
# Make scripts executable
chmod +x manual_test.py
chmod +x run_manual_tests.sh
```

### Configuration Tips

1. **First Time**: Use all default settings
2. **Debugging**: Enable verbose output
3. **Development**: Keep test database for inspection
4. **Production Verification**: Run full test suite before deployment

### Integration with Foundation Tests

This manual test suite complements the automated foundation tests:
- **Automated Tests**: Unit tests for individual components
- **Manual Tests**: Integration tests with realistic scenarios
- **Combined Coverage**: Comprehensive validation of all systems

Run both test suites for complete verification:

```bash
# Automated foundation tests
python tests/test_foundation.py

# Manual integration tests
python manual_test.py
```

### Success Criteria

✅ **Foundation Ready for Phase 2 when:**
- All automated tests pass (13/13)
- All manual tests pass (7/7)
- No critical issues in code review
- Database operations working correctly
- Elo calculations accurate
- Player registration functional