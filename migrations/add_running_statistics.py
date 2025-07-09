"""
Migration script to add running statistics fields to Event table for Phase 3.2
"""

import sqlite3
import os

def run_migration():
    """Add running statistics fields to Event table."""
    
    # Get database path from environment or use default
    db_path = os.getenv('DATABASE_PATH', 'tournament.db')
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add running statistics fields to events table
        print("Adding running statistics fields to events table...")
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(events)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'score_count' not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN score_count INTEGER DEFAULT 0 NOT NULL")
            print("Added score_count column")
        
        if 'score_mean' not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN score_mean REAL DEFAULT 0.0 NOT NULL")
            print("Added score_mean column")
        
        if 'score_m2' not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN score_m2 REAL DEFAULT 0.0 NOT NULL")
            print("Added score_m2 column")
        
        # Add unique constraint for leaderboard scores if it doesn't exist
        print("Adding unique constraint for leaderboard scores...")
        
        # Check if the unique index already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='uniq_leaderboard_personal_best'
        """)
        
        if not cursor.fetchone():
            cursor.execute("""
                CREATE UNIQUE INDEX uniq_leaderboard_personal_best 
                ON leaderboard_scores(player_id, event_id, score_type) 
                WHERE score_type = 'all_time'
            """)
            print("Added unique constraint for personal best scores")
        
        conn.commit()
        print("Migration completed successfully!")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()