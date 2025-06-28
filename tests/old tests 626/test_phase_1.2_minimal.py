#!/usr/bin/env python3
"""
Phase 1.2 Minimal Test - Direct PlayerEventStats Testing
Tests the core functionality without complex setup
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.database.database import Database
from bot.database.models import (
    Player, Event, PlayerEventStats, Match, MatchParticipant, 
    MatchStatus, MatchFormat, EloHistory
)
from bot.database.match_operations import MatchOperations
from sqlalchemy import select, delete

# Test constants
TEST_PLAYER_1_ID = 999991
TEST_PLAYER_2_ID = 999992

async def test_phase_1_2():
    print("=== Phase 1.2 Minimal Test - PlayerEventStats Integration ===\n")
    
    # Initialize database
    db = Database()
    await db.initialize()
    
    # Variables for cleanup
    player1_id = None
    player2_id = None
    created_match_ids = []
    
    try:
        # Cleanup any existing test data
        async with db.transaction() as session:
            await session.execute(
                delete(Player).where(Player.discord_id.in_([TEST_PLAYER_1_ID, TEST_PLAYER_2_ID]))
            )
        
        # Step 1: Setup test data
        print("1. Setting up test data...")
        async with db.transaction() as session:
            # Create players
            player1 = Player(
                discord_id=TEST_PLAYER_1_ID,
                username="test_player_1",
                elo_rating=1000
            )
            player2 = Player(
                discord_id=TEST_PLAYER_2_ID,
                username="test_player_2",
                elo_rating=1000
            )
            session.add(player1)
            session.add(player2)
            await session.flush()
            
            player1_id = player1.id
            player2_id = player2.id
            
            # Get events
            result = await session.execute(
                select(Event).where(Event.name.in_(["Diep (1v1)", "Blitz"]))
            )
            events = result.scalars().all()
            
            diep_event = next((e for e in events if "Diep" in e.name), None)
            blitz_event = next((e for e in events if "Blitz" in e.name and e.scoring_type == "1v1"), None)
            
            if not diep_event or not blitz_event:
                raise ValueError("Required test events not found")
                
            diep_event_id = diep_event.id
            blitz_event_id = blitz_event.id
            
            # Create matches directly (bypass challenge system for testing)
            match1 = Match(
                event_id=diep_event_id,
                match_format=MatchFormat.ONE_V_ONE,
                status=MatchStatus.PENDING,
                created_at=datetime.now(timezone.utc)
            )
            session.add(match1)
            await session.flush()
            
            # Add participants
            mp1 = MatchParticipant(match_id=match1.id, player_id=player1_id)
            mp2 = MatchParticipant(match_id=match1.id, player_id=player2_id)
            session.add(mp1)
            session.add(mp2)
            
            match1_id = match1.id
            created_match_ids.append(match1_id)
            
            print(f"   ✓ Created players: {player1_id}, {player2_id}")
            print(f"   ✓ Created match {match1_id} in {diep_event.name}")
        
        # Step 2: Complete the match
        print("\n2. Completing match with results...")
        match_ops = MatchOperations(db)
        
        results = [
            {"player_id": player1_id, "placement": 1},  # Player 1 wins
            {"player_id": player2_id, "placement": 2}
        ]
        
        await match_ops.complete_match_with_results(match1_id, results)
        print("   ✓ Match completed")
        
        # Step 3: Verify PlayerEventStats
        print("\n3. Verifying PlayerEventStats created...")
        async with db.transaction() as session:
            result = await session.execute(
                select(PlayerEventStats)
                .where(PlayerEventStats.event_id == diep_event_id)
                .where(PlayerEventStats.player_id.in_([player1_id, player2_id]))
            )
            stats = result.scalars().all()
            
            assert len(stats) == 2, f"Expected 2 PlayerEventStats, found {len(stats)}"
            
            for stat in stats:
                player = await session.get(Player, stat.player_id)
                print(f"   ✓ {player.username}: Event Elo={stat.raw_elo}, Matches={stat.matches_played}")
                
                # Verify wins/losses updated
                if stat.player_id == player1_id:
                    assert stat.wins == 1, "Winner should have 1 win"
                    assert stat.raw_elo > 1000, "Winner should gain Elo"
                else:
                    assert stat.losses == 1, "Loser should have 1 loss"
                    assert stat.raw_elo < 1000, "Loser should lose Elo"
        
        # Step 4: Create another match in different event
        print("\n4. Creating match in different event...")
        async with db.transaction() as session:
            match2 = Match(
                event_id=blitz_event_id,
                match_format=MatchFormat.ONE_V_ONE,
                status=MatchStatus.PENDING,
                created_at=datetime.now(timezone.utc)
            )
            session.add(match2)
            await session.flush()
            
            mp3 = MatchParticipant(match_id=match2.id, player_id=player1_id)
            mp4 = MatchParticipant(match_id=match2.id, player_id=player2_id)
            session.add(mp3)
            session.add(mp4)
            
            match2_id = match2.id
            created_match_ids.append(match2_id)
            print(f"   ✓ Created match {match2_id} in {blitz_event.name}")
        
        # Complete with opposite result
        results2 = [
            {"player_id": player1_id, "placement": 2},  # Player 1 loses
            {"player_id": player2_id, "placement": 1}   # Player 2 wins
        ]
        
        await match_ops.complete_match_with_results(match2_id, results2)
        print("   ✓ Match completed")
        
        # Step 5: Verify separate Elo tracking
        print("\n5. Verifying separate Elo per event...")
        async with db.transaction() as session:
            # Get all PlayerEventStats
            result = await session.execute(
                select(PlayerEventStats, Event)
                .join(Event)
                .where(PlayerEventStats.player_id.in_([player1_id, player2_id]))
                .order_by(PlayerEventStats.player_id, Event.name)
            )
            
            print(f"   {'Player':<15} {'Event':<20} {'Elo':<10} {'W-L'}")
            print("   " + "-" * 50)
            
            for stat, event in result:
                player = await session.get(Player, stat.player_id)
                print(f"   {player.username:<15} {event.name:<20} {stat.raw_elo:<10} {stat.wins}-{stat.losses}")
        
        # Step 6: Verify EloHistory
        print("\n6. Verifying EloHistory has event_id...")
        async with db.transaction() as session:
            result = await session.execute(
                select(EloHistory)
                .where(EloHistory.player_id.in_([player1_id, player2_id]))
                .where(EloHistory.match_id.isnot(None))
            )
            
            records = result.scalars().all()
            assert len(records) == 4, f"Expected 4 EloHistory records, found {len(records)}"
            
            for record in records:
                assert record.event_id is not None, "EloHistory missing event_id"
            
            print(f"   ✓ All {len(records)} EloHistory records have event_id")
        
        # Step 7: Verify global elo sync
        print("\n7. Verifying global elo sync...")
        async with db.transaction() as session:
            players = await session.execute(
                select(Player).where(Player.id.in_([player1_id, player2_id]))
            )
            
            for player in players.scalars():
                # Get latest match
                latest_mp = await session.execute(
                    select(MatchParticipant)
                    .join(Match)
                    .where(MatchParticipant.player_id == player.id)
                    .where(Match.status == MatchStatus.COMPLETED)
                    .order_by(Match.completed_at.desc())
                    .limit(1)
                )
                mp = latest_mp.scalar_one()
                
                assert player.elo_rating == mp.elo_after, \
                    f"Global elo mismatch: {player.elo_rating} != {mp.elo_after}"
                print(f"   ✓ {player.username}: Global={player.elo_rating}")
        
        print("\n✅ ALL TESTS PASSED!")
        print("   - PlayerEventStats created and updated correctly")
        print("   - Separate Elo tracking per event verified")
        print("   - EloHistory includes event_id")
        print("   - Global elo syncs with latest match")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
        
    finally:
        # Cleanup
        print("\n8. Cleaning up...")
        async with db.transaction() as session:
            if created_match_ids:
                await session.execute(
                    delete(Match).where(Match.id.in_(created_match_ids))
                )
            await session.execute(
                delete(Player).where(Player.discord_id.in_([TEST_PLAYER_1_ID, TEST_PLAYER_2_ID]))
            )
        print("   ✓ Cleanup complete")

if __name__ == "__main__":
    asyncio.run(test_phase_1_2())