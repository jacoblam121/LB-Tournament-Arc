-- Phase 2.4.1 Fix: Populate missing supported_scoring_types for existing events
-- This script fixes the 54 events that have NULL or empty supported_scoring_types

-- First, let's see which events are missing supported_scoring_types
SELECT 'Events missing supported_scoring_types:' as info;
SELECT name, scoring_type, base_event_name 
FROM events 
WHERE is_active = 1 AND (supported_scoring_types IS NULL OR supported_scoring_types = '')
ORDER BY name;

-- Update events that have a scoring_type but missing supported_scoring_types
-- Most events only support their primary scoring type
UPDATE events 
SET supported_scoring_types = scoring_type
WHERE is_active = 1 
  AND (supported_scoring_types IS NULL OR supported_scoring_types = '')
  AND scoring_type IS NOT NULL;

-- Special case: Some common games that we know support multiple modes
-- Based on the patterns we saw with Diep and Bonk
UPDATE events
SET supported_scoring_types = '1v1,FFA,Team'
WHERE is_active = 1 
  AND name IN ('Krunker', 'Brawhalla', 'Arsenal', 'Bedwars', 'Skywars')
  AND (supported_scoring_types IS NULL OR supported_scoring_types = '' OR supported_scoring_types = scoring_type);

-- Update 2v2 games to support Team mode
UPDATE events
SET supported_scoring_types = 'Team'
WHERE is_active = 1 
  AND name = '2v2'
  AND (supported_scoring_types IS NULL OR supported_scoring_types = '');

-- Update games that are clearly 1v1 only
UPDATE events
SET supported_scoring_types = '1v1'
WHERE is_active = 1 
  AND name IN ('1v1', 'Chess')
  AND (supported_scoring_types IS NULL OR supported_scoring_types = '');

-- Update leaderboard/time-based events
UPDATE events
SET supported_scoring_types = 'Leaderboard'
WHERE is_active = 1 
  AND (name LIKE '%run' OR name LIKE '%dash' OR name LIKE '%Sprint')
  AND (supported_scoring_types IS NULL OR supported_scoring_types = '');

-- Final check
SELECT 'After fix - Events still missing supported_scoring_types:' as info;
SELECT COUNT(*) as missing_count
FROM events 
WHERE is_active = 1 AND (supported_scoring_types IS NULL OR supported_scoring_types = '');

-- Show sample of fixed events
SELECT 'Sample of fixed events:' as info;
SELECT name, supported_scoring_types
FROM events 
WHERE is_active = 1 AND supported_scoring_types IS NOT NULL
ORDER BY name
LIMIT 20;