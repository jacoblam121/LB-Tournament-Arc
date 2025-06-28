#!/bin/bash
# Rollback script for Phase 2.1.1 migration
# Generated: 2025-06-28 03:05:22.369005

DB_PATH="tournament.db"
BACKUP_PATH="tournament_backup_phase_2_1_1_20250628_030522.db"

echo "Rolling back Phase 2.1.1 migration..."
sqlite3 "$DB_PATH" <<EOF
PRAGMA foreign_keys = OFF;

-- Remove the role column
CREATE TABLE challenge_participants_new (
    id INTEGER PRIMARY KEY,
    challenge_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    responded_at DATETIME,
    team_id VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(challenge_id) REFERENCES challenges(id),
    FOREIGN KEY(player_id) REFERENCES players(id),
    UNIQUE(challenge_id, player_id)
);

INSERT INTO challenge_participants_new 
SELECT id, challenge_id, player_id, status, responded_at, team_id, created_at
FROM challenge_participants;

DROP TABLE challenge_participants;
ALTER TABLE challenge_participants_new RENAME TO challenge_participants;

-- Recreate indexes
CREATE INDEX idx_challenge_participants_challenge ON challenge_participants(challenge_id);
CREATE INDEX idx_challenge_participants_player ON challenge_participants(player_id);
CREATE INDEX idx_challenge_participants_status ON challenge_participants(status);

PRAGMA foreign_keys = ON;
EOF

echo "✅ Rollback complete"
