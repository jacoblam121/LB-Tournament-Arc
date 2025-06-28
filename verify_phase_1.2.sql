-- Phase 1.2 Verification Queries
-- Run these after completing a match to verify PlayerEventStats integration

-- 1. Check PlayerEventStats are created for match participants
SELECT 
    p.username,
    e.name as event_name,
    pes.raw_elo as event_elo,
    pes.matches_played,
    pes.wins,
    pes.losses,
    p.elo_rating as global_elo
FROM player_event_stats pes
JOIN players p ON pes.player_id = p.id
JOIN events e ON pes.event_id = e.id
WHERE pes.created_at > datetime('now', '-1 hour')
ORDER BY p.username, e.name;

-- 2. Verify EloHistory includes event_id
SELECT 
    p.username,
    e.name as event_name,
    eh.old_elo,
    eh.new_elo,
    eh.elo_change,
    eh.k_factor,
    CASE WHEN eh.event_id IS NULL THEN 'MISSING' ELSE 'OK' END as event_id_status
FROM elo_history eh
JOIN players p ON eh.player_id = p.id
LEFT JOIN events e ON eh.event_id = e.id
WHERE eh.match_id IS NOT NULL
AND eh.recorded_at > datetime('now', '-1 hour')
ORDER BY eh.recorded_at DESC;

-- 3. Check that different events have different Elo ratings
SELECT 
    p.username,
    COUNT(DISTINCT e.id) as num_events,
    COUNT(DISTINCT pes.raw_elo) as unique_elos,
    GROUP_CONCAT(e.name || ':' || pes.raw_elo, ', ') as event_elos
FROM player_event_stats pes
JOIN players p ON pes.player_id = p.id
JOIN events e ON pes.event_id = e.id
GROUP BY p.id
HAVING COUNT(DISTINCT e.id) > 1;

-- 4. Verify global elo matches most recent match
WITH recent_matches AS (
    SELECT 
        mp.player_id,
        mp.elo_after,
        m.completed_at,
        ROW_NUMBER() OVER (PARTITION BY mp.player_id ORDER BY m.completed_at DESC) as rn
    FROM match_participants mp
    JOIN matches m ON mp.match_id = m.id
    WHERE m.status = 'completed'
)
SELECT 
    p.username,
    p.elo_rating as global_elo,
    rm.elo_after as last_match_elo,
    CASE 
        WHEN p.elo_rating = rm.elo_after THEN '✓ SYNCED'
        ELSE '✗ MISMATCH'
    END as sync_status
FROM players p
JOIN recent_matches rm ON p.id = rm.player_id
WHERE rm.rn = 1
ORDER BY p.username;