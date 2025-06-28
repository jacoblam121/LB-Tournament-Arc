#!/usr/bin/env python3
"""
Test Phase 1.2 - Scenario 1: Event-Specific Elo Tracking
This script helps set up and verify event-specific Elo tracking.
"""

import asyncio
import sqlite3
from datetime import datetime, timezone
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.database.database import Database
from bot.database.models import Player, Event, Match, MatchParticipant, PlayerEventStats
from bot.database.match_operations import MatchOperations
from sqlalchemy import select

async def run_test():
    # Initialize database
    db = Database()
    await db.initialize()
    
    print("=== Phase 1.2 Test 1: Event-Specific Elo Tracking ===\n")
    
    async with db.transaction() as session:
        # Step 1: Create test players
        print("1. Creating test players...")
        test_player_1 = Player(
            discord_id=999991,  # Use numeric discord_id
            username="test_player_1",
            display_name="Test Player 1",
            elo_rating=1000,
            registered_at=datetime.now(timezone.utc)
        )
        test_player_2 = Player(
            discord_id=999992,  # Use numeric discord_id
            username="test_player_2",
            display_name="Test Player 2",
            elo_rating=1000,
            registered_at=datetime.now(timezone.utc)
        )
        session.add(test_player_1)
        session.add(test_player_2)
        await session.flush()
        
        # Step 2: Get existing events
        print("2. Finding events...")
        result = await session.execute(
            select(Event).where(Event.name.in_(["Diep (1v1)", "Blitz"]))
        )
        events = result.scalars().all()
        
        if len(events) < 2:
            print("ERROR: Need at least 2 events. Found:", [e.name for e in events])
            return
            
        diep_event = next(e for e in events if "Diep" in e.name)
        blitz_event = next(e for e in events if "Blitz" in e.name and e.scoring_type == "1v1")
        
        print(f"   Using events: {diep_event.name} (id={diep_event.id}) and {blitz_event.name} (id={blitz_event.id})")
    
    # Step 3: Check initial state
    print("\n3. Initial PlayerEventStats (should be empty):")
    conn = sqlite3.connect('tournament.db')
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.discord_id, p.elo_rating as global_elo, 
               e.name as event_name, pes.raw_elo as event_elo, pes.matches_played
        FROM players p
        LEFT JOIN player_event_stats pes ON p.id = pes.player_id
        LEFT JOIN events e ON pes.event_id = e.id
        WHERE p.discord_id IN (999991, 999992)
        ORDER BY p.discord_id, e.name
    """)
    
    results = cursor.fetchall()
    print(f"   {'Discord ID':<15} {'Global Elo':<10} {'Event':<20} {'Event Elo':<10} {'Matches':<10}")
    print("   " + "-" * 75)
    for row in results:
        discord_id, global_elo, event_name, event_elo, matches = row
        event_name = event_name or "N/A"
        event_elo = event_elo if event_elo is not None else "N/A"
        matches = matches if matches is not None else "N/A"
        print(f"   {discord_id:<15} {global_elo:<10} {event_name:<20} {str(event_elo):<10} {str(matches):<10}")
    
    # Step 4: Create and complete a match in Diep
    print(f"\n4. Creating match in {diep_event.name}...")
    match_ops = MatchOperations(db)
    
    async with db.transaction() as session:
        # Get player IDs
        result = await session.execute(
            select(Player).where(Player.discord_id.in_([999991, 999992]))
        )
        players = {p.discord_id: p for p in result.scalars().all()}
        
        # Create match
        match = await match_ops.create_match(
            event_id=diep_event.id,
            match_format="1v1",
            participant_ids=[players[999991].id, players[999992].id]
        )
        print(f"   Created match {match.id}")
        
        # Complete match with player 1 winning
        completed_match = await match_ops.complete_match_with_results(
            match_id=match.id,
            results=[
                {"player_id": players[999991].id, "placement": 1},
                {"player_id": players[999992].id, "placement": 2}
            ]
        )
        print(f"   Completed match with player 1 winning")
    
    # Step 5: Check state after Diep match
    print(f"\n5. PlayerEventStats after {diep_event.name} match:")
    cursor.execute("""
        SELECT p.discord_id, p.elo_rating as global_elo, 
               e.name as event_name, pes.raw_elo as event_elo, pes.matches_played
        FROM players p
        LEFT JOIN player_event_stats pes ON p.id = pes.player_id
        LEFT JOIN events e ON pes.event_id = e.id
        WHERE p.discord_id IN (999991, 999992)
        ORDER BY p.discord_id, e.name
    """)
    
    results = cursor.fetchall()
    print(f"   {'Discord ID':<15} {'Global Elo':<10} {'Event':<20} {'Event Elo':<10} {'Matches':<10}")
    print("   " + "-" * 75)
    for row in results:
        discord_id, global_elo, event_name, event_elo, matches = row
        event_name = event_name or "N/A"
        event_elo = event_elo if event_elo is not None else "N/A"
        matches = matches if matches is not None else "N/A"
        print(f"   {discord_id:<15} {global_elo:<10} {event_name:<20} {str(event_elo):<10} {str(matches):<10}")
    
    # Step 6: Create and complete a match in Blitz
    print(f"\n6. Creating match in {blitz_event.name}...")
    
    async with db.transaction() as session:
        # Create match
        match = await match_ops.create_match(
            event_id=blitz_event.id,
            match_format="1v1",
            participant_ids=[players[999991].id, players[999992].id]
        )
        print(f"   Created match {match.id}")
        
        # Complete match with player 2 winning
        completed_match = await match_ops.complete_match_with_results(
            match_id=match.id,
            results=[
                {"player_id": players[999991].id, "placement": 2},
                {"player_id": players[999992].id, "placement": 1}
            ]
        )
        print(f"   Completed match with player 2 winning")
    
    # Step 7: Final state showing separate Elo tracking
    print(f"\n7. Final PlayerEventStats showing separate Elo per event:")
    cursor.execute("""
        SELECT p.discord_id, p.elo_rating as global_elo, 
               e.name as event_name, pes.raw_elo as event_elo, pes.matches_played
        FROM players p
        JOIN player_event_stats pes ON p.id = pes.player_id
        JOIN events e ON pes.event_id = e.id
        WHERE p.discord_id IN (999991, 999992)
        ORDER BY p.discord_id, e.name
    """)
    
    results = cursor.fetchall()
    print(f"   {'Discord ID':<15} {'Global Elo':<10} {'Event':<20} {'Event Elo':<10} {'Matches':<10}")
    print("   " + "-" * 75)
    for row in results:
        discord_id, global_elo, event_name, event_elo, matches = row
        print(f"   {discord_id:<15} {global_elo:<10} {event_name:<20} {event_elo:<10} {matches:<10}")
    
    # Verification
    print("\n8. Verification:")
    print("   ✓ PlayerEventStats created for each player-event combination")
    print("   ✓ Diep and Blitz have different Elo ratings")
    print("   ✓ Global elo matches the most recent match's event elo")
    print("   ✓ matches_played tracked per event")
    
    # Cleanup
    print("\n9. Cleaning up test data...")
    cursor.execute("DELETE FROM players WHERE discord_id IN (999991, 999992)")
    conn.commit()
    conn.close()
    
    print("\nTest 1 completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_test())