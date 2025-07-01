#!/usr/bin/env python3
"""
Phase 2 Model Updates - Apply AFTER migration is complete
Updates Challenge model and database operations to use event_id instead of game_id

CRITICAL: Only run this AFTER migration_game_to_event_fixed.py has completed successfully
"""

import os
import shutil
from datetime import datetime

def backup_files():
    """Create backups of files before modification"""
    files_to_backup = [
        "bot/database/models.py",
        "bot/database/database.py",
        "manual_test.py"
    ]
    
    backup_dir = f"backup_pre_phase2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    os.makedirs(backup_dir, exist_ok=True)
    
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            backup_path = os.path.join(backup_dir, file_path.replace('/', '_'))
            shutil.copy2(file_path, backup_path)
            print(f"✅ Backed up {file_path} → {backup_path}")
    
    print(f"📁 Backup directory: {backup_dir}")
    return backup_dir

def update_challenge_model():
    """Update Challenge model to use event_id"""
    print("🔧 Updating Challenge model...")
    
    models_file = "bot/database/models.py"
    
    # Read current content
    with open(models_file, 'r') as f:
        content = f.read()
    
    # Replace game_id with event_id
    content = content.replace(
        'game_id = Column(Integer, ForeignKey(\'games.id\'), nullable=False)',
        'event_id = Column(Integer, ForeignKey(\'events.id\'), nullable=False)'
    )
    
    # Update relationship
    content = content.replace(
        'game = relationship("Game", back_populates="challenges")',
        'event = relationship("Event")'
    )
    
    # Update Game model relationships
    content = content.replace(
        'challenges = relationship("Challenge", back_populates="game")',
        '# challenges = relationship("Challenge", back_populates="game")  # Deprecated'
    )
    
    # Write updated content
    with open(models_file, 'w') as f:
        f.write(content)
    
    print("✅ Updated Challenge model")

def update_database_operations():
    """Update database operations to use event_id"""
    print("🔧 Updating database operations...")
    
    database_file = "bot/database/database.py"
    
    # Read current content
    with open(database_file, 'r') as f:
        content = f.read()
    
    # Replace parameter name
    content = content.replace(
        'game_id: int, **kwargs) -> Challenge:',
        'event_id: int, **kwargs) -> Challenge:'
    )
    
    # Replace in Challenge creation
    content = content.replace(
        'game_id=game_id,',
        'event_id=event_id,'
    )
    
    # Replace selectinload
    content = content.replace(
        'selectinload(Challenge.game)',
        'selectinload(Challenge.event)'
    )
    
    # Write updated content
    with open(database_file, 'w') as f:
        f.write(content)
    
    print("✅ Updated database operations")

def update_manual_test():
    """Update manual test to use challenge.event instead of challenge.game"""
    print("🔧 Updating manual test...")
    
    test_file = "manual_test.py"
    
    # Read current content
    with open(test_file, 'r') as f:
        content = f.read()
    
    # Replace challenge.game references
    content = content.replace(
        'challenge.challenger and challenge.challenged and challenge.game:',
        'challenge.challenger and challenge.challenged and challenge.event:'
    )
    
    content = content.replace(
        'self.print_info(f"  Game: {challenge.game.name}")',
        'self.print_info(f"  Event: {challenge.event.name}")'
    )
    
    # Write updated content
    with open(test_file, 'w') as f:
        f.write(content)
    
    print("✅ Updated manual test")

def main():
    """Apply Phase 2 model updates"""
    print("🚀 Phase 2 Model Updates")
    print("=" * 50)
    print("This script updates the models to use event_id after migration.")
    print("ONLY run this AFTER the migration script has completed successfully.")
    print()
    
    response = input("Has the migration completed successfully? (y/N): ")
    if response.lower() != 'y':
        print("❌ Run migration_game_to_event_fixed.py first!")
        return 1
    
    try:
        # Create backups
        backup_dir = backup_files()
        
        # Apply updates
        update_challenge_model()
        update_database_operations()
        update_manual_test()
        
        print()
        print("=" * 50)
        print("✅ Phase 2 model updates completed successfully!")
        print("=" * 50)
        print("Next steps:")
        print("1. Run test_phase_2a1_migration.py to verify changes")
        print("2. Test existing functionality")
        print("3. If issues occur, restore from backup:", backup_dir)
        
        return 0
        
    except Exception as e:
        print(f"❌ Update failed: {e}")
        print(f"Restore from backup: {backup_dir}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)