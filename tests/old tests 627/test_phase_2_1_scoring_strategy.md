# Phase 2.1 Test Plan: Update Scoring Strategy Factory

## Overview
This test plan validates that the scoring strategy factory now uses match.match_format instead of event.scoring_type, laying the groundwork for unified Elo ratings.

## Pre-Implementation Verification

### 1. Check Current Implementation
```bash
# Verify the changes were applied
grep -n "match.match_format" bot/database/match_operations.py
grep -n "_get_scoring_strategy" bot/database/match_operations.py
```
**Expected**: 
- Line 647 should show `scoring_strategy = await self._get_scoring_strategy(match.match_format)`
- Line 785 should show method signature with `match_format: MatchFormat` parameter

### 2. Verify Enum Import
```bash
# Check that MatchFormat is imported
grep -n "MatchFormat" bot/database/match_operations.py | head -5
```
**Expected**: Should see import of MatchFormat from models

## Functional Tests

### 3. Test 1v1 Match Scoring
```python
# Start the bot
python -m bot.main

# In Discord:
/challenge @opponent event_name:"Tekken 8"
# Accept the challenge
# Report result: challenger wins
```
**Expected**: 
- Match should complete successfully
- Elo changes should be calculated using Elo1v1Strategy
- Check logs for: "Successfully completed Match X with 2 participants"

### 4. Test FFA Match Scoring
```python
# In Discord (as admin):
# Create an FFA match manually
/admin-create-match event_name:"Diep (FFA)" players:@player1,@player2,@player3
# Record results with placements
```
**Expected**:
- Match should use EloFfaStrategy
- K-factor should be divided by (N-1) for multi-player scaling
- All participants should receive appropriate Elo changes

### 5. Test Leaderboard Event
```python
# Find a leaderboard event
/list-events

# Create a match for a leaderboard event
# Record results
```
**Expected**:
- Should use PerformancePointsStrategy
- No Elo loss for lower placements
- PP (Performance Points) should be awarded

### 6. Test Team Match
```python
# Create a team match if available
# Record team-based results
```
**Expected**:
- Should use EloFfaStrategy (same as FFA for now)
- Team assignments should be preserved

## Edge Case Tests

### 7. Test Unknown Match Format
```sql
-- This should not happen in normal operation, but test error handling
-- Manually insert a match with invalid format (DO NOT RUN IN PRODUCTION)
```
**Expected**: Should raise MatchValidationError with "Unknown match format"

### 8. Test Backward Compatibility
```python
# Test that existing 1v1 challenges still work
/challenge @opponent event_name:"Street Fighter 6"
```
**Expected**: 
- Challenge → Match bridge should work
- Match format should be set to ONE_V_ONE
- Scoring should use correct strategy

## Database Verification

### 9. Check Match Format Values
```sql
-- Verify match formats are correctly set
SELECT DISTINCT match_format, COUNT(*) 
FROM matches 
GROUP BY match_format;
```
**Expected**: Should see valid MatchFormat enum values (1v1, ffa, team, leaderboard)

### 10. Verify Elo History
```sql
-- Check recent Elo history entries
SELECT eh.*, m.match_format 
FROM elo_history eh
JOIN matches m ON eh.match_id = m.id
WHERE eh.recorded_at > datetime('now', '-1 hour')
ORDER BY eh.recorded_at DESC
LIMIT 5;
```
**Expected**: 
- Elo changes should correspond to the match format
- K-factors should be appropriate for each format

## Performance Tests

### 11. Bulk Match Processing
```python
# Process multiple matches of different formats
# Monitor performance and correctness
```
**Expected**: 
- No performance degradation
- Correct strategy selection for each format

## Integration Tests

### 12. Test with Phase 1.5 UI
```python
# Ensure aggregated view still works
/list-events
# Toggle between grouped/detailed view
```
**Expected**: 
- UI aggregation should be unaffected
- Events should display correctly regardless of match format usage

## Success Criteria
- [ ] All match formats correctly map to their scoring strategies
- [ ] No regression in existing functionality
- [ ] Error handling works for invalid formats
- [ ] Performance remains consistent
- [ ] Backward compatibility maintained

## Known Limitations
- Event.scoring_type is still used for event configuration validation
- This is intentional and correct - events define what formats they support
- Matches determine which specific format was used for that game

## Next Steps
After Phase 2.1 is validated:
- Phase 2.2: Implement Per-Event Elo Infrastructure
- Phase 2.3: Migrate Match Completion Logic
- Phase 2.4: Update Leaderboard & Stats Commands