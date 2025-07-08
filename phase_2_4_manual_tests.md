# Phase 2.4: EloHierarchyCalculator Integration - Manual Test Suite

## Overview
This test suite verifies the EloHierarchyCalculator integration, caching behavior, and performance improvements.

## Prerequisites
1. Bot running with Phase 2.4 changes applied
2. Database migration completed (`python -m migrations.add_phase_2_4_indexes`)
3. At least 2 test players with match history
4. Admin access to run sync commands

## Test Cases

### 1. Basic Profile Command with Hierarchy Calculation
**Purpose**: Verify hierarchy calculator is used and returns correct values

**Steps**:
1. Run `/profile` command for a player with match history
2. Check bot logs for "Using EloHierarchyCalculator for player X"
3. Verify overall ELO values are displayed correctly

**Expected Results**:
- Profile displays with correct overall_raw_elo and overall_scoring_elo
- Debug log shows hierarchy calculator usage
- No errors in console

### 2. Cache Hit Behavior
**Purpose**: Verify caching works properly

**Steps**:
1. Run `/profile` for Player A
2. Check logs for "Cache miss for player X, calculating fresh"
3. Immediately run `/profile` for Player A again
4. Check logs for "Cache hit for player X"

**Expected Results**:
- First call: Cache miss, calculation performed
- Second call: Cache hit, no calculation
- Response time should be faster on second call

### 3. Cache Invalidation After Match
**Purpose**: Verify cache clears after match completion

**Steps**:
1. Run `/profile` for Player A (populate cache)
2. Have Player A complete a match
3. Check logs for "Invalidated cache for player X"
4. Run `/profile` for Player A again
5. Check logs for cache miss

**Expected Results**:
- Cache invalidated after match completion
- Next profile call triggers fresh calculation
- Updated ELO values reflect recent match

### 4. Error Handling
**Purpose**: Verify graceful handling of calculation errors

**Steps**:
1. Temporarily break database connection (if possible in test env)
2. Run `/profile` for any player
3. Check error logs

**Expected Results**:
- Error logged: "Failed to calculate hierarchy for player X"
- Default values returned (1000 for all ELO types)
- Command doesn't crash, shows profile with defaults

### 5. Configuration Testing
**Purpose**: Verify configuration values are respected

**Steps**:
1. Check config for `system.cache_ttl_hierarchy` (default 900s)
2. Check config for `system.cache_size_hierarchy` (default 1000)
3. If possible, modify values and restart bot
4. Verify new values are used

**Expected Results**:
- Cache respects configured TTL
- Cache size limit enforced

### 6. Performance Index Verification
**Purpose**: Verify database indexes are working

**Steps**:
1. Run database query to check indexes:
   ```sql
   SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';
   ```
2. Verify these indexes exist:
   - idx_elo_history_player_recorded
   - idx_elo_history_players
   - idx_player_event_stats_event
   - idx_player_event_stats_player_elo
   - idx_event_cluster

**Expected Results**:
- All Phase 2.4 indexes present
- Query performance improved for hierarchy calculations

### 7. Fallback Mechanism
**Purpose**: Verify fallback to local calculation works

**Steps**:
1. Temporarily modify code to set `self.elo_hierarchy_service = None` in ProfileService
2. Run `/profile` command
3. Check logs for "Using local calculation for player X"

**Expected Results**:
- Profile still works using fallback calculation
- Debug log shows local calculation usage
- Values match expected results

### 8. Multi-Player Cache Test
**Purpose**: Verify cache handles multiple players correctly

**Steps**:
1. Run `/profile` for Players A, B, C in sequence
2. Run `/profile` for Player A again (should hit cache)
3. Run `/profile` for Player B again (should hit cache)
4. Complete match between A and B
5. Run `/profile` for both A and B

**Expected Results**:
- Each player's data cached independently
- Cache hits for repeated queries
- Only A and B's caches invalidated after match
- Player C's cache remains valid

## Performance Benchmarks

### Before Phase 2.4
- Profile command response time: ___ ms
- Hierarchy calculation time: ___ ms

### After Phase 2.4
- Profile command response time (cache miss): ___ ms
- Profile command response time (cache hit): ___ ms
- Hierarchy calculation time: ___ ms

## Troubleshooting

### Common Issues

1. **"Failed to calculate hierarchy" errors**
   - Check database connection
   - Verify PlayerEventStats table has data
   - Check for NULL values in elo columns

2. **Cache not invalidating**
   - Verify ProfileService is initialized in MatchCommandsCog
   - Check _update_participant_streaks is called after match
   - Look for invalidation log messages

3. **Wrong ELO values displayed**
   - Verify database values in Player table
   - Check if hierarchy calculator returns expected values
   - Compare with ProfileService._calculate_overall_elo results

## Notes
- Cache TTL is 15 minutes by default
- Cache size limit is 1000 entries
- Indexes significantly improve query performance with large datasets