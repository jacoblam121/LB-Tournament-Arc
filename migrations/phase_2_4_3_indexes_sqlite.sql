-- Phase 2.4.3: Challenge Management Commands - SQLite Database Indexes
-- These indexes optimize the role-based queries for challenge management

-- Composite index for efficient role-based challenge lookups
-- This significantly speeds up queries filtering by player_id and role
CREATE INDEX IF NOT EXISTS idx_challenge_participant_lookup 
ON challenge_participants(player_id, role, status);

-- Index for challenge status queries with time-based sorting
-- Optimizes queries that filter by status and sort by created_at
CREATE INDEX IF NOT EXISTS idx_challenge_status 
ON challenges(status, created_at);

-- For outgoing challenges (challenger's pending challenges)
CREATE INDEX IF NOT EXISTS idx_cp_pending_challenger
ON challenge_participants(player_id, challenge_id)
WHERE role = 'challenger' AND status = 'pending';

-- For incoming challenges (challenged player's pending invitations)  
CREATE INDEX IF NOT EXISTS idx_cp_pending_challenged
ON challenge_participants(player_id, challenge_id)
WHERE role = 'challenged' AND status = 'pending';

-- Add updated_at column to challenges table for better auditing
-- Note: SQLite doesn't support triggers for auto-update like PostgreSQL
-- The ORM will handle this with onupdate=func.now()
ALTER TABLE challenges 
ADD COLUMN updated_at TIMESTAMP;