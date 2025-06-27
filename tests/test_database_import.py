#!/usr/bin/env python3
"""
Test script for database import functionality from CSV.

This script tests the database.py import_clusters_and_events_from_csv() method
to ensure it works correctly as a fallback when populate_from_csv.py is not available.
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.database.database import Database


async def test_import():
    """Test the database import functionality"""
    print("Testing database import from CSV...")
    
    db = Database()
    try:
        await db.initialize()
        print("✅ Database initialized")
        
        async with db.get_session() as session:
            await db.import_clusters_and_events_from_csv(session, clear_existing=True)
        
        print("✅ CSV import completed")
        
        # Verify the import worked
        clusters = await db.get_all_clusters(active_only=False)
        events = await db.get_all_events(active_only=False)
        
        print(f"✅ Import verification:")
        print(f"   - Clusters created: {len(clusters)}")
        print(f"   - Events created: {len(events)}")
        
        # Show some sample data
        if clusters:
            print(f"   - Sample clusters: {', '.join([f'{c.number}. {c.name}' for c in clusters[:3]])}")
        
        if events:
            print(f"   - Sample events: {', '.join([f'{e.name} ({e.scoring_type})' for e in events[:3]])}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise
    finally:
        await db.close()
        print("✅ Database connection closed")


if __name__ == "__main__":
    print("="*60)
    print("DATABASE IMPORT TEST")
    print("="*60)
    
    try:
        asyncio.run(test_import())
        print("\n" + "="*60)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*60)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)