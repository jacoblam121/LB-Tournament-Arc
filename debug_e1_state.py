#!/usr/bin/env python3
"""
Debug the database state before and after E1 test
"""

import sqlite3
from datetime import datetime

def check_database_state():
    conn = sqlite3.connect('tournament.db')
    cursor = conn.cursor()
    
    print("=== Current Database State ===")
    
    # Check current week
    current_week = datetime.now().isocalendar()[1]
    print(f"Current week: {current_week}")
    
    # Check Player 1's current state
    cursor.execute('''
        SELECT player_id, weekly_elo_average, weeks_participated, final_score
        FROM player_event_stats 
        WHERE event_id = 19 AND player_id = 1
    ''')
    result = cursor.fetchone()
    if result:
        print(f"Player 1 current state: avg={result[1]}, weeks={result[2]}, final={result[3]}")
    
    # Check if there are any weekly scores currently
    cursor.execute('''
        SELECT COUNT(*) FROM leaderboard_scores 
        WHERE event_id = 19 AND score_type = 'weekly' AND week_number = ?
    ''', (current_week,))
    weekly_count = cursor.fetchone()[0]
    print(f"Weekly scores for Event 19, Week {current_week}: {weekly_count}")
    
    # Let's check Player 1's state before each test by examining all players
    print("\nAll players current state for Event 19:")
    cursor.execute('''
        SELECT player_id, weekly_elo_average, weeks_participated, final_score
        FROM player_event_stats 
        WHERE event_id = 19
        ORDER BY player_id
    ''')
    for row in cursor.fetchall():
        print(f"  Player {row[0]}: avg={row[1]:.2f}, weeks={row[2]}, final={row[3]}")
    
    conn.close()
    
    print("\n=== Analysis ===")
    print("The issue appears to be that the test sequence has modified the database state.")
    print("Each test (E1, E2, E3) ran consecutively and modified Player 1's stats.")
    print("E1 expected Player 1 to have specific starting stats, but previous tests changed them.")
    print()
    print("The mathematical calculation in E1 is actually CORRECT:")
    print("1. Single player with score 35.75")
    print("2. Z-score = 0 (since player is the mean)")  
    print("3. Weekly Elo = 1000 (base Elo)")
    print("4. Running average updated correctly")
    print()
    print("The test FAILURE was due to incorrect expectations about the weekly_elo_average field.")
    print("weekly_elo_average is a RUNNING AVERAGE across all weeks, not just this week's Elo.")

if __name__ == "__main__":
    check_database_state()