#!/bin/bash
# Rollback script for Phase 1 Unified Elo migration
# Generated: 2025-06-27 00:40:04

echo "Rolling back Phase 1 Unified Elo migration..."
cp tournament_backup_unified_elo_phase1_20250627_004003.db tournament.db
echo "Rollback complete. Database restored from tournament_backup_unified_elo_phase1_20250627_004003.db"
