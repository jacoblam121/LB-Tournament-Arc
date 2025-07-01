-- Phase 2.4.3: Challenge Management Commands - Database Indexes
-- These indexes optimize the role-based queries for challenge management

-- Composite index for efficient role-based challenge lookups
-- This significantly speeds up queries filtering by player_id and role
CREATE INDEX IF NOT EXISTS idx_challenge_participant_lookup 
ON challenge_participants(player_id, role, status);

-- Index for challenge status queries with time-based sorting
-- Optimizes queries that filter by status and sort by created_at
CREATE INDEX IF NOT EXISTS idx_challenge_status 
ON challenges(status, created_at);

-- Optional: Partial indexes for even better performance on specific queries
-- These are more efficient for the most common query patterns

-- For outgoing challenges (challenger's pending challenges)
CREATE INDEX IF NOT EXISTS idx_cp_pending_challenger
ON challenge_participants(player_id, challenge_id)
WHERE role = 'challenger' AND status = 'pending';

-- For incoming challenges (challenged player's pending invitations)  
CREATE INDEX IF NOT EXISTS idx_cp_pending_challenged
ON challenge_participants(player_id, challenge_id)
WHERE role = 'challenged' AND status = 'pending';

-- Add updated_at column to challenges table for better auditing
-- This helps track when challenge statuses change
ALTER TABLE challenges 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Create trigger to auto-update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_challenges_updated_at 
BEFORE UPDATE ON challenges 
FOR EACH ROW 
EXECUTE FUNCTION update_updated_at_column();