#!/bin/bash
# Emergency rollback script for Game→Event migration
# Created: 2025-06-25 00:19:25

echo '🚨 EMERGENCY ROLLBACK: Restoring database backup'

cp 'tournament.db' 'corrupted_$(date +%Y%m%d_%H%M%S)_tournament.db'
cp 'backup_pre_migration_20250625_001925_tournament.db' 'tournament.db'
echo '✅ Database restored from backup'

echo '⚠️  You may need to restart the application'