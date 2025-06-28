#!/bin/bash
# Rollback script for Phase 1 Unified Elo migration
# Generated: 2025-06-27 00:41:30

echo "Rolling back Phase 1 Unified Elo migration..."
cp tournament_backup_unified_elo_phase1_20250627_004130.db tournament.db
echo "Rollback complete. Database restored from tournament_backup_unified_elo_phase1_20250627_004130.db"
