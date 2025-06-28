#!/bin/bash
# Rollback script for Phase 1.5 UI Aggregation migration
# Generated at: 2025-06-27 01:20:24.928721

echo "🔄 Rolling back Phase 1.5 migration..."

# Restore from backup
cp "tournament_backup_ui_aggregation_phase1_5_20250627_012024.db" tournament.db

echo "✅ Rollback complete! Database restored from backup."
echo "Note: The base_event_name column has been removed."
