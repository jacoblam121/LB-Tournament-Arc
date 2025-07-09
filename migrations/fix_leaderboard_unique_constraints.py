"""
Fix leaderboard_scores unique constraints

This migration fixes the incorrectly created uq_all_time_scores constraint
that was preventing weekly scores from being inserted.
"""

import sqlite3
import sys
import os

# Add parent directory to path to import from bot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def migrate():
    """Fix the unique constraints on leaderboard_scores table"""
    
    # Connect to database
    conn = sqlite3.connect('tournament.db')
    cursor = conn.cursor()
    
    try:
        # Drop the incorrect constraint that's causing issues
        print("Dropping incorrect uq_all_time_scores constraint...")
        cursor.execute("DROP INDEX IF EXISTS uq_all_time_scores")
        
        # Check if the correct constraint already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='uniq_leaderboard_personal_best'
        """)
        
        if not cursor.fetchone():
            # If not, create the correct constraint for all_time scores
            print("Creating correct unique constraint for all_time scores...")
            cursor.execute("""
                CREATE UNIQUE INDEX uniq_leaderboard_personal_best 
                ON leaderboard_scores(player_id, event_id, score_type) 
                WHERE score_type = 'all_time'
            """)
        else:
            print("Correct all_time constraint already exists")
        
        # Verify weekly constraint exists and is correct
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type='index' AND name='uq_weekly_scores'
        """)
        result = cursor.fetchone()
        
        if not result:
            print("Creating weekly scores unique constraint...")
            cursor.execute("""
                CREATE UNIQUE INDEX uq_weekly_scores 
                ON leaderboard_scores(player_id, event_id, score_type, week_number) 
                WHERE week_number IS NOT NULL
            """)
        else:
            print("Weekly scores constraint already exists")
        
        # Commit changes
        conn.commit()
        print("Migration completed successfully!")
        
        # Show current constraints for verification
        print("\nCurrent unique constraints on leaderboard_scores:")
        cursor.execute("""
            SELECT name, sql FROM sqlite_master 
            WHERE type='index' AND tbl_name='leaderboard_scores' AND sql LIKE '%UNIQUE%'
        """)
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]}")
        
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()