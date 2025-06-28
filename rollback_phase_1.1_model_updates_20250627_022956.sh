#!/bin/bash
# Rollback script for phase_1.1_model_updates
echo "Rolling back phase_1.1_model_updates migration..."
cp "tournament_backup_phase_1.1_model_updates_20250627_022956.db" "tournament.db"
echo "Rollback complete. Database restored from tournament_backup_phase_1.1_model_updates_20250627_022956.db"
