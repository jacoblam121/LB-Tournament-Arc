#!/bin/bash

echo "=== Phase 1.2 Test 1: Event-Specific Elo Tracking ==="
echo ""
echo "This script provides SQL commands to verify event-specific Elo tracking."
echo "Run these commands in SQLite to check the results after using Discord commands."
echo ""

echo "1. To check initial state (should show no PlayerEventStats):"
echo "sqlite3 tournament.db"
echo ""
cat << 'EOF'
SELECT p.discord_id, p.username, p.elo_rating as global_elo, 
       e.name as event_name, pes.raw_elo as event_elo, pes.matches_played
FROM players p
LEFT JOIN player_event_stats pes ON p.id = pes.player_id  
LEFT JOIN events e ON pes.event_id = e.id
WHERE p.username LIKE '%test%' OR p.discord_id > 999000
ORDER BY p.discord_id, e.name;
EOF

echo ""
echo "2. After creating matches in different events, check event-specific stats:"
echo ""
cat << 'EOF'
SELECT p.discord_id, p.username, p.elo_rating as global_elo,
       e.name as event_name, pes.raw_elo as event_elo, pes.matches_played
FROM players p  
JOIN player_event_stats pes ON p.id = pes.player_id
JOIN events e ON pes.event_id = e.id
WHERE p.username LIKE '%test%' OR p.discord_id > 999000
ORDER BY p.discord_id, e.name;
EOF

echo ""
echo "3. To verify EloHistory includes event_id:"
echo ""
cat << 'EOF'
SELECT eh.id, p.username, e.name as event_name, 
       eh.old_elo, eh.new_elo, eh.elo_change, eh.k_factor,
       datetime(eh.recorded_at) as recorded_at
FROM elo_history eh
JOIN players p ON eh.player_id = p.id
JOIN events e ON eh.event_id = e.id
WHERE eh.match_id IS NOT NULL
ORDER BY eh.recorded_at DESC
LIMIT 10;
EOF

echo ""
echo "4. To check for any matches without event context in EloHistory:"
echo ""
cat << 'EOF'
SELECT COUNT(*) as missing_event_context
FROM elo_history eh
WHERE eh.match_id IS NOT NULL AND eh.event_id IS NULL
AND eh.recorded_at > datetime('now', '-1 hour');
EOF

echo ""
echo "5. To see matches and their event context:"
echo ""
cat << 'EOF'  
SELECT m.id as match_id, e.name as event_name, m.match_format,
       m.status, datetime(m.completed_at) as completed_at,
       COUNT(mp.id) as participants
FROM matches m
JOIN events e ON m.event_id = e.id
LEFT JOIN match_participants mp ON m.id = mp.match_id
WHERE m.completed_at > datetime('now', '-1 hour')
GROUP BY m.id
ORDER BY m.completed_at DESC
LIMIT 10;
EOF

echo ""
echo "6. To verify global elo matches latest event elo:"
echo ""
cat << 'EOF'
WITH recent_matches AS (
    SELECT mp.player_id, m.event_id, mp.elo_after,
           ROW_NUMBER() OVER (PARTITION BY mp.player_id ORDER BY m.completed_at DESC) as rn
    FROM match_participants mp
    JOIN matches m ON mp.match_id = m.id
    WHERE m.status = 'completed'
)
SELECT p.username, p.elo_rating as global_elo, 
       e.name as last_event, rm.elo_after as last_match_elo,
       CASE WHEN p.elo_rating = rm.elo_after THEN 'SYNCED' ELSE 'MISMATCH' END as status
FROM players p
JOIN recent_matches rm ON p.id = rm.player_id
JOIN events e ON rm.event_id = e.id
WHERE rm.rn = 1 
AND (p.username LIKE '%test%' OR p.discord_id > 999000)
ORDER BY p.username;
EOF

echo ""
echo "=== Discord Commands to Test ==="
echo ""
echo "1. Create test players if needed (use real Discord users)"
echo "2. Create and complete a match in Diep (1v1):"
echo "   /match create event:\"Diep (1v1)\" format:1v1 participants:@player1 @player2"
echo "   /match complete match_id:[ID] results:player1=1 player2=2"
echo ""
echo "3. Create and complete a match in Blitz:"
echo "   /match create event:Blitz format:1v1 participants:@player1 @player2" 
echo "   /match complete match_id:[ID] results:player1=2 player2=1"
echo ""
echo "4. Run the SQL queries above to verify:"
echo "   - PlayerEventStats created for each event"
echo "   - Different Elo ratings per event"
echo "   - Global elo synced with latest match"
echo "   - EloHistory includes event_id"