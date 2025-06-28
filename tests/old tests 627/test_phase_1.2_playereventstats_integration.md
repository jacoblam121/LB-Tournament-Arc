# Phase 1.2: PlayerEventStats Integration Test Suite

This test suite validates the integration of PlayerEventStats into the match completion flow, ensuring that event-specific Elo ratings are properly tracked while maintaining backward compatibility with global Elo.

## Prerequisites

1. Ensure Phase 1.1 migration has been completed successfully
2. Bot should be running with the updated code
3. Database should have at least two events created
4. Have at least 4 test Discord users available

## Test 1: Event-Specific Elo Tracking

**Objective**: Verify that matches update PlayerEventStats with event-specific Elo ratings

**Setup**:
1. Create two events: "Diep" and "Arras"
2. Create 2 test players

**Test Steps**:
1. Record initial state:
   ```sql
   -- Check initial PlayerEventStats
   SELECT p.discord_id, p.elo_rating as global_elo, 
          e.name as event_name, pes.raw_elo as event_elo, pes.matches_played
   FROM players p
   LEFT JOIN player_event_stats pes ON p.id = pes.player_id
   LEFT JOIN events e ON pes.event_id = e.id
   WHERE p.discord_id IN ('test_player_1', 'test_player_2')
   ORDER BY p.discord_id, e.name;
   ```

2. Create and complete a match in "Diep":
   ```
   /match create event:Diep format:1v1 participants:@player1 @player2
   /match complete match_id:[ID] results:player1=1 player2=2
   ```

3. Verify event-specific Elo updated:
   ```sql
   -- Check PlayerEventStats after Diep match
   SELECT p.discord_id, p.elo_rating as global_elo, 
          e.name as event_name, pes.raw_elo as event_elo, pes.matches_played
   FROM players p
   LEFT JOIN player_event_stats pes ON p.id = pes.player_id
   LEFT JOIN events e ON pes.event_id = e.id
   WHERE p.discord_id IN ('test_player_1', 'test_player_2')
   ORDER BY p.discord_id, e.name;
   ```

4. Create and complete a match in "Arras":
   ```
   /match create event:Arras format:1v1 participants:@player1 @player2
   /match complete match_id:[ID] results:player1=2 player2=1
   ```

5. Verify separate Elo tracking:
   ```sql
   -- Check both events have different Elo ratings
   SELECT p.discord_id, e.name as event_name, 
          pes.raw_elo as event_elo, pes.matches_played
   FROM players p
   JOIN player_event_stats pes ON p.id = pes.player_id
   JOIN events e ON pes.event_id = e.id
   WHERE p.discord_id IN ('test_player_1', 'test_player_2')
   ORDER BY p.discord_id, e.name;
   ```

**Expected Results**:
- PlayerEventStats should be created for each player-event combination
- Diep and Arras should have different Elo ratings
- Global elo should match the most recent match's event elo
- matches_played should be tracked per event

## Test 2: K-Factor Based on Event Matches

**Objective**: Verify that K-factor is calculated based on event-specific matches played, not global

**Setup**:
1. Use a player with 10+ global matches but 0 matches in a specific event

**Test Steps**:
1. Check initial state:
   ```sql
   -- Player with many global matches but new to event
   SELECT p.discord_id, p.matches_played as global_matches,
          e.name as event_name, pes.matches_played as event_matches
   FROM players p
   LEFT JOIN player_event_stats pes ON p.id = pes.player_id
   LEFT JOIN events e ON pes.event_id = e.id
   WHERE p.discord_id = 'experienced_player';
   ```

2. Create match in new event:
   ```
   /match create event:NewEvent format:1v1 participants:@experienced @newbie
   /match complete match_id:[ID] results:experienced=1 newbie=2
   ```

3. Check Elo history for K-factor:
   ```sql
   -- Should show K=40 (provisional) not K=20
   SELECT eh.player_id, eh.event_id, eh.elo_change, eh.k_factor,
          p.discord_id, e.name as event_name
   FROM elo_history eh
   JOIN players p ON eh.player_id = p.id
   JOIN events e ON eh.event_id = e.id
   WHERE p.discord_id = 'experienced_player'
   ORDER BY eh.recorded_at DESC
   LIMIT 1;
   ```

**Expected Results**:
- K-factor should be 40 (provisional) for first matches in new event
- Even if player has 10+ global matches

## Test 3: EloHistory Event Context

**Objective**: Verify that EloHistory records include event_id for audit trail

**Test Steps**:
1. Complete a match and check EloHistory:
   ```sql
   -- All EloHistory records should have event_id
   SELECT eh.id, eh.player_id, eh.event_id, eh.old_elo, eh.new_elo, 
          eh.elo_change, eh.match_id, e.name as event_name
   FROM elo_history eh
   JOIN events e ON eh.event_id = e.id
   WHERE eh.match_id IS NOT NULL
   ORDER BY eh.recorded_at DESC
   LIMIT 5;
   ```

2. Verify no NULL event_ids:
   ```sql
   -- Should return 0 rows
   SELECT COUNT(*) as null_event_count
   FROM elo_history
   WHERE match_id IS NOT NULL AND event_id IS NULL;
   ```

**Expected Results**:
- All match-based EloHistory records should have event_id populated
- No NULL event_ids for new records

## Test 4: FFA with Event-Specific Elo

**Objective**: Verify FFA matches use event-specific Elo for calculations

**Setup**:
1. Create 4 players with different Elo ratings in different events

**Test Steps**:
1. Setup initial state:
   ```sql
   -- Check starting Elos across events
   SELECT p.discord_id, e.name as event_name, pes.raw_elo
   FROM players p
   JOIN player_event_stats pes ON p.id = pes.player_id
   JOIN events e ON pes.event_id = e.id
   WHERE p.discord_id IN ('ffa1', 'ffa2', 'ffa3', 'ffa4')
   ORDER BY e.name, pes.raw_elo DESC;
   ```

2. Create FFA match:
   ```
   /match create event:Diep format:ffa participants:@ffa1 @ffa2 @ffa3 @ffa4
   /match complete match_id:[ID] results:ffa1=1 ffa2=2 ffa3=3 ffa4=4
   ```

3. Verify calculations used event-specific Elo:
   ```sql
   -- Check Elo changes are based on event-specific ratings
   SELECT p.discord_id, eh.old_elo, eh.new_elo, eh.elo_change
   FROM elo_history eh
   JOIN players p ON eh.player_id = p.id
   WHERE eh.match_id = [MATCH_ID]
   ORDER BY eh.elo_change DESC;
   ```

**Expected Results**:
- Elo changes should be calculated based on event-specific ratings
- Higher rated players (in that event) should lose more when placing poorly

## Test 5: Backward Compatibility

**Objective**: Verify global Elo stays in sync with event Elo

**Test Steps**:
1. Complete a match and verify sync:
   ```sql
   -- Global elo should match the event elo of the last match
   SELECT p.discord_id, p.elo_rating as global_elo,
          e.name as last_event, pes.raw_elo as event_elo,
          m.completed_at
   FROM players p
   JOIN match_participants mp ON p.id = mp.player_id
   JOIN matches m ON mp.match_id = m.id
   JOIN events e ON m.event_id = e.id
   JOIN player_event_stats pes ON p.id = pes.player_id AND e.id = pes.event_id
   WHERE m.status = 'completed'
   ORDER BY m.completed_at DESC
   LIMIT 4;
   ```

**Expected Results**:
- Player.elo_rating should equal PlayerEventStats.raw_elo for the most recent match's event
- Global matches_played should increment with each match

## Test 6: Multi-Event Leaderboards

**Objective**: Verify that leaderboards can be filtered by event

**Test Steps**:
1. Create matches in multiple events
2. Query event-specific leaderboards:
   ```sql
   -- Diep leaderboard
   SELECT p.discord_id, pes.raw_elo, pes.matches_played, pes.wins, pes.losses
   FROM player_event_stats pes
   JOIN players p ON pes.player_id = p.id
   JOIN events e ON pes.event_id = e.id
   WHERE e.name = 'Diep'
   ORDER BY pes.raw_elo DESC;
   
   -- Arras leaderboard  
   SELECT p.discord_id, pes.raw_elo, pes.matches_played, pes.wins, pes.losses
   FROM player_event_stats pes
   JOIN players p ON pes.player_id = p.id
   JOIN events e ON pes.event_id = e.id
   WHERE e.name = 'Arras'
   ORDER BY pes.raw_elo DESC;
   ```

**Expected Results**:
- Each event should have its own leaderboard
- Players can have different rankings in different events

## Validation Queries

Run these queries to validate the overall system state:

```sql
-- 1. Check for any matches without event_id in EloHistory
SELECT COUNT(*) as missing_event_context
FROM elo_history eh
WHERE eh.match_id IS NOT NULL AND eh.event_id IS NULL
AND eh.recorded_at > (SELECT MAX(completed_at) FROM matches WHERE completed_at < datetime('now', '-1 hour'));

-- 2. Verify PlayerEventStats are being created
SELECT e.name as event_name, COUNT(DISTINCT pes.player_id) as players_in_event
FROM events e
LEFT JOIN player_event_stats pes ON e.id = pes.event_id
GROUP BY e.id, e.name;

-- 3. Check for sync issues between global and event Elo
WITH recent_matches AS (
    SELECT mp.player_id, m.event_id, mp.elo_after,
           ROW_NUMBER() OVER (PARTITION BY mp.player_id ORDER BY m.completed_at DESC) as rn
    FROM match_participants mp
    JOIN matches m ON mp.match_id = m.id
    WHERE m.status = 'completed'
)
SELECT p.discord_id, p.elo_rating as global_elo, rm.elo_after as last_match_elo,
       ABS(p.elo_rating - rm.elo_after) as difference
FROM players p
JOIN recent_matches rm ON p.id = rm.player_id
WHERE rm.rn = 1 AND ABS(p.elo_rating - rm.elo_after) > 0;
```

## Notes

- Phase 1.2 maintains full backward compatibility
- Global Elo is kept in sync for tools that still rely on it
- Event-specific stats enable better matchmaking within game modes
- Historical data can be migrated if needed (see optional migration script)