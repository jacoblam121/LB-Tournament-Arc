#!/usr/bin/env python3
"""
Add database index for Player.final_score to optimize ranking queries.

This script adds a performance index for the ranking fix implemented in Phase 2.2.
The index improves performance of ORDER BY Player.final_score DESC queries used
in both ProfileService and LeaderboardService.

Usage:
    python add_ranking_index.py
"""

import asyncio
import sqlite3
import os
from bot.database.database import Database

async def add_ranking_index():
    """Add index on Player.final_score for ranking query optimization."""
    
    db_path = "tournament.db"
    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} not found")
        return False
    
    try:
        # Use direct SQLite connection for index creation
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if index already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_players_final_score_desc'
        """)
        
        if cursor.fetchone():
            print("✅ Index idx_players_final_score_desc already exists")
            conn.close()
            return True
        
        # Create index for ranking queries (final_score DESC)
        print("🔄 Creating index on Player.final_score for ranking optimization...")
        cursor.execute("""
            CREATE INDEX idx_players_final_score_desc 
            ON players(final_score DESC) 
            WHERE is_active = 1
        """)
        
        conn.commit()
        conn.close()
        
        print("✅ Successfully created index idx_players_final_score_desc")
        print("📊 This index will optimize ranking queries in ProfileService and LeaderboardService")
        return True
        
    except Exception as e:
        print(f"❌ Error creating index: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(add_ranking_index())
    if success:
        print("\n🎯 Index creation complete! Ranking queries should now be faster.")
    else:
        print("\n⚠️  Index creation failed. Manual index creation may be needed.")