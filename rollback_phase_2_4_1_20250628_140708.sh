#!/bin/bash
# Rollback script for Phase 2.4.1 migration
# Generated: 2025-06-28 14:07:08.413942
# Backup: tournament_backup_phase_2_4_1_20250628_140708.db

DB_PATH="tournament.db"
BACKUP_PATH="tournament_backup_phase_2_4_1_20250628_140708.db"

echo "🔄 Rolling back Phase 2.4.1 unified Elo migration..."

# Safety check
if [ ! -f "$BACKUP_PATH" ]; then
    echo "❌ Backup file not found: $BACKUP_PATH"
    exit 1
fi

sqlite3 "$DB_PATH" <<EOF
PRAGMA foreign_keys = OFF;

-- Restore events table from backup
DROP TABLE IF EXISTS events;
CREATE TABLE events AS SELECT * FROM events_legacy_2_4_1;

-- Restore player_event_stats table from backup  
DROP TABLE IF EXISTS player_event_stats;
CREATE TABLE player_event_stats AS SELECT * FROM player_event_stats_legacy_2_4_1;

-- Remove scoring_type column from matches (if it exists)
-- Note: This requires table recreation in SQLite
CREATE TABLE matches_new AS 
SELECT id, event_id, match_format, status, created_by, started_at, completed_at,
       admin_notes, created_at, updated_at
FROM matches;

DROP TABLE matches;
ALTER TABLE matches_new RENAME TO matches;

-- Recreate indexes (add your specific indexes here)
CREATE INDEX IF NOT EXISTS idx_events_cluster ON events(cluster_id);
CREATE INDEX IF NOT EXISTS idx_events_base_name ON events(base_event_name);
CREATE INDEX IF NOT EXISTS idx_player_event_stats_player ON player_event_stats(player_id);
CREATE INDEX IF NOT EXISTS idx_player_event_stats_event ON player_event_stats(event_id);

-- Clean up legacy tables
DROP TABLE IF EXISTS events_legacy_2_4_1;
DROP TABLE IF EXISTS player_event_stats_legacy_2_4_1;

PRAGMA foreign_keys = ON;
EOF

echo "✅ Rollback complete"
echo "⚠️  Note: You may need to repopulate from CSV to get clean event structure"
