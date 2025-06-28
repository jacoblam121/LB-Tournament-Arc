# Phase 1.2 Implementation Summary

## What We Implemented

### 1. Modified ParticipantResult (scoring_strategies.py)
- Added `event_id` field to pass event context through scoring calculations

### 2. Updated Match Completion Flow (match_operations.py)
- Fetches PlayerEventStats for each participant before scoring
- Uses event-specific elo/matches for K-factor calculations  
- Updates PlayerEventStats after match completion
- Maintains global elo sync for backward compatibility
- Ensures EloHistory includes event_id

### 3. Key Changes
```python
# Before: Used global elo
current_elo=participant.player.elo_rating

# After: Uses event-specific elo
event_stats = await self.db.get_or_create_player_event_stats(...)
current_elo=event_stats.raw_elo
```

## How to Test

1. **Create matches in different events via Discord:**
   ```
   /challenge @opponent event:"Diep (1v1)"
   /challenge @opponent event:"Blitz"
   ```

2. **Complete the matches and record results**

3. **Run verification queries:**
   ```bash
   sqlite3 tournament.db < verify_phase_1.2.sql
   ```

4. **Check that:**
   - PlayerEventStats are created for each player-event combination
   - Different events have different Elo ratings
   - EloHistory records include event_id
   - Global elo matches the most recent match

## What This Achieves

- **Per-event Elo tracking**: Players can have different skill ratings in different game modes
- **Proper K-factor**: Provisional status (K=40) is per-event, not global
- **Backward compatibility**: Global elo still updated for existing features
- **Complete audit trail**: EloHistory tracks which event each rating change belongs to

## Next Steps

Phase 2.2: Challenge Workflows (as per planA.md)
- Unified acceptance system using ChallengeParticipant
- Route /ffa internals through new model
- 24-hour expiration with proper cleanup