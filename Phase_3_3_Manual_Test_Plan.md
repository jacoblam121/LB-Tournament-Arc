# Phase 3.3 Z-Score Statistical Conversion Service - Manual Test Plan

## Test Environment Setup

### Prerequisites
- Bot running with Phase 3.3 implementation
- Database with leaderboard events configured
- Redis server running
- Admin access to run `/submit-event-score` commands

### Test Data Requirements
- At least 1 leaderboard event with `score_direction` set (HIGH or LOW)
- Multiple test users available for score submission
- Clear database state before testing

## Test Suite A: Basic Z-Score Calculation

### Test A1: Single Player Score Submission
**Objective**: Verify Z-score calculation works for single player
**Steps**:
1. Submit a score for Player A in a leaderboard event
2. Check database: `SELECT all_time_leaderboard_elo FROM player_event_stats WHERE player_id = A AND event_id = X`
3. **Expected**: Elo should be base_elo (1000) since single player has z-score of 0

### Test A2: Two Player Score Comparison (HIGH direction)
**Objective**: Verify Z-score calculation with 2 players, HIGH score direction
**Steps**:
1. Create/use event with `score_direction = 'HIGH'`
2. Player A submits score: 100
3. Player B submits score: 200
4. Check database for both players' all_time_leaderboard_elo
5. **Expected**: Player B should have higher Elo than Player A

### Test A3: Two Player Score Comparison (LOW direction)
**Objective**: Verify Z-score calculation with 2 players, LOW score direction
**Steps**:
1. Create/use event with `score_direction = 'LOW'`
2. Player A submits score: 100
3. Player B submits score: 50
4. Check database for both players' all_time_leaderboard_elo
5. **Expected**: Player B should have higher Elo than Player A (lower score is better)

### Test A4: Multiple Player Distribution
**Objective**: Verify Z-score distribution with multiple players
**Steps**:
1. Submit scores for 5 players: 100, 200, 300, 400, 500
2. Check all_time_leaderboard_elo for all players
3. **Expected**: 
   - Player with score 300 (mean) should have ~1000 Elo
   - Higher scores should have >1000 Elo, lower scores <1000 Elo
   - Distribution should be symmetric around mean

## Test Suite B: Background Processing & Redis Locking

### Test B1: Redis Lock Functionality
**Objective**: Verify Redis locking prevents duplicate calculations
**Steps**:
1. Submit score for Player A
2. Immediately submit another score for Player A (within 30 seconds)
3. Check Redis for lock key: `elo_calculation_lock:{event_id}`
4. Check bot logs for "throttled - lock exists" message
5. **Expected**: Second calculation should be throttled

### Test B2: Lock Expiration
**Objective**: Verify locks expire after 30 seconds
**Steps**:
1. Submit score for Player A
2. Wait 35 seconds
3. Submit score for Player B in same event
4. Check logs for successful calculation
5. **Expected**: Second calculation should proceed (lock expired)

### Test B3: Background Task Error Handling
**Objective**: Verify behavior when Redis is unavailable
**Steps**:
1. Stop Redis server
2. Submit score for Player A
3. Check bot logs for error messages
4. Check database - score should be saved but Elo not updated
5. **Expected**: Score submission succeeds, Elo calculation fails gracefully

## Test Suite C: Database Compatibility

### Test C1: PostgreSQL Compatibility
**Objective**: Verify service works with PostgreSQL
**Steps**:
1. Configure bot to use PostgreSQL database
2. Submit scores for multiple players
3. Check database queries execute without syntax errors
4. **Expected**: All operations succeed with PostgreSQL

### Test C2: SQLite Compatibility
**Objective**: Verify service works with SQLite
**Steps**:
1. Configure bot to use SQLite database
2. Submit scores for multiple players
3. Check database queries execute without syntax errors
4. **Expected**: All operations succeed with SQLite

## Test Suite D: Performance & Edge Cases

### Test D1: Large Dataset Performance
**Objective**: Verify performance with many players
**Steps**:
1. Submit scores for 50+ players in single event
2. Submit new score to trigger recalculation
3. Monitor calculation time and memory usage
4. **Expected**: Calculation completes within reasonable time (<5 seconds)

### Test D2: Identical Scores Handling
**Objective**: Verify handling of identical scores
**Steps**:
1. Submit identical scores (e.g., 100) for 3 players
2. Check all_time_leaderboard_elo for all players
3. **Expected**: All players should have same Elo (base_elo)

### Test D3: Single Score Edge Case
**Objective**: Verify handling when only one score exists
**Steps**:
1. Submit single score for Player A
2. Check database for standard deviation calculation
3. **Expected**: No division by zero errors, reasonable Elo assigned

## Test Suite E: Integration Testing

### Test E1: Personal Best Updates
**Objective**: Verify Z-score recalculation on personal best
**Steps**:
1. Player A submits score: 100
2. Player B submits score: 200
3. Player A improves to score: 300
4. Check Elos are recalculated for both players
5. **Expected**: Both players' Elos should be updated

### Test E2: Non-Personal Best Submissions
**Objective**: Verify no recalculation on non-personal best
**Steps**:
1. Player A submits score: 200
2. Player A submits lower score: 100
3. Check logs for calculation trigger
4. **Expected**: No background calculation should be triggered

## Test Suite F: Configuration Testing

### Test F1: Custom Base Elo
**Objective**: Verify configurable base Elo
**Steps**:
1. Set `elo.leaderboard_base_elo` to 1500
2. Submit scores for players
3. Check calculated Elos center around 1500
4. **Expected**: Mean player should have ~1500 Elo

### Test F2: Custom Sigma Scaling
**Objective**: Verify configurable sigma scaling
**Steps**:
1. Set `leaderboard_system.elo_per_sigma` to 100
2. Submit scores with known standard deviation
3. Check Elo spread is adjusted accordingly
4. **Expected**: Elo spread should be tighter (100 per σ instead of 200)

## Test Execution Checklist

### Before Testing:
- [ ] Backup database
- [ ] Clear existing leaderboard scores
- [ ] Verify Redis is running
- [ ] Set up test users
- [ ] Configure test event with appropriate score_direction

### During Testing:
- [ ] Record all test results
- [ ] Capture relevant log messages
- [ ] Screenshot any errors
- [ ] Note performance observations

### After Testing:
- [ ] Restore database backup
- [ ] Document any issues found
- [ ] Verify all test cases pass
- [ ] Report results to development team

## Expected Results Summary

**✅ PASS Criteria:**
- All Z-score calculations mathematically correct
- Redis locking prevents race conditions
- Background tasks don't block score submission
- Compatible with both PostgreSQL and SQLite
- Handles edge cases gracefully
- Performance acceptable for expected load

**❌ FAIL Criteria:**
- Database compatibility issues
- Redis connection errors
- Incorrect mathematical calculations
- Performance degradation
- Unhandled exceptions
- Data corruption

## Known Issues to Monitor

1. **Database Compatibility**: Watch for PostgreSQL-specific syntax errors on SQLite
2. **Redis Connection Leaks**: Monitor Redis connection count during testing
3. **Background Task Failures**: Check for silent failures in background calculations
4. **Memory Usage**: Monitor memory consumption with large datasets