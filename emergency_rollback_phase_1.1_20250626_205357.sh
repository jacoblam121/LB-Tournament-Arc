#!/bin/bash
# Emergency rollback for Phase 1.1 migration
cp tournament_backup_phase_1.1_20250626_205357.db tournament.db
echo 'Database rolled back to pre-migration state'
