#!/usr/bin/env python3
"""
Phase 1.2 Test - Fixed Version
Tests PlayerEventStats integration with proper assertions and cleanup
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.database.database import Database
from bot.database.models import (
    Player, Event, PlayerEventStats, Challenge, ChallengeStatus,
    Match, MatchParticipant, MatchStatus, EloHistory
)
from bot.database.match_operations import MatchOperations
from sqlalchemy import select, delete

# Test constants
TEST_PLAYER_1_ID = 999991
TEST_PLAYER_2_ID = 999992

async def test_phase_1_2():
    print("=== Phase 1.2 Test - PlayerEventStats Integration ===\n")
    
    # Initialize database
    db = Database()
    await db.initialize()
    
    # Variables to store created IDs for cleanup
    player1_id = None
    player2_id = None
    diep_event_id = None
    blitz_event_id = None
    created_challenge_ids = []
    created_match_ids = []
    
    try:
        # Initial cleanup
        async with db.transaction() as session:
            await session.execute(
                delete(Player).where(Player.discord_id.in_([TEST_PLAYER_1_ID, TEST_PLAYER_2_ID]))
            )
            
        # Step 1: Create test players
        print("1. Creating test players...")
        async with db.transaction() as session:
            player1 = Player(
                discord_id=TEST_PLAYER_1_ID,
                username="test_player_1",
                display_name="Test Player 1",
                elo_rating=1000
            )
            player2 = Player(
                discord_id=TEST_PLAYER_2_ID,
                username="test_player_2", 
                display_name="Test Player 2",
                elo_rating=1000
            )
            session.add(player1)
            session.add(player2)
            await session.flush()
            
            # Store IDs for later use
            player1_id = player1.id
            player2_id = player2.id
            print(f"   ✓ Created players with IDs: {player1_id}, {player2_id}")
            
            # Get test events
            result = await session.execute(
                select(Event).where(Event.name.in_(["Diep (1v1)", "Blitz"]))
            )
            events = result.scalars().all()
            
            # Safe event lookup
            diep_event = next((e for e in events if "Diep" in e.name), None)
            blitz_event = next((e for e in events if "Blitz" in e.name and e.scoring_type == "1v1"), None)
            
            if not diep_event or not blitz_event:
                raise ValueError("Required test events 'Diep (1v1)' and 'Blitz' not found in database")
                
            diep_event_id = diep_event.id
            blitz_event_id = blitz_event.id
            print(f"   ✓ Using events: {diep_event.name} (id={diep_event_id}), {blitz_event.name} (id={blitz_event_id})")
        
        # Step 2: Verify initial state
        print("\n2. Verifying initial state...")
        async with db.transaction() as session:
            result = await session.execute(
                select(PlayerEventStats)
                .where(PlayerEventStats.player_id.in_([player1_id, player2_id]))
            )
            stats = result.scalars().all()
            assert len(stats) == 0, f"Expected 0 PlayerEventStats, found {len(stats)}"
            print(f"   ✓ PlayerEventStats count: 0 (correct)")
        
        # Step 3: Create and complete match in Diep
        print(f"\n3. Creating match in Diep (1v1)...")
        match_ops = MatchOperations(db)
        
        # Create challenge first
        async with db.transaction() as session:
            challenge = Challenge(
                challenger_id=player1_id,
                challenged_id=player2_id,
                event_id=diep_event_id,
                status=ChallengeStatus.ACCEPTED,
                ticket_wager=0
            )
            session.add(challenge)
            await session.flush()
            challenge_id = challenge.id
            created_challenge_ids.append(challenge_id)
        
        # Create match from challenge in separate transaction
        match = await match_ops.create_match_from_challenge(challenge_id)
        match_id = match.id
        created_match_ids.append(match_id)
        print(f"   ✓ Created match {match_id}")
        
        # Complete the match
        async with db.transaction() as session:
            results = [
                {"player_id": player1_id, "placement": 1},  # Player 1 wins
                {"player_id": player2_id, "placement": 2}
            ]
            match = await match_ops.complete_match_with_results(match_id, results)
            print(f"   ✓ Completed match with player 1 winning")
        
        # Verify PlayerEventStats created
        print(f"\n4. Verifying PlayerEventStats after first match...")
        async with db.transaction() as session:
            result = await session.execute(
                select(PlayerEventStats)
                .where(PlayerEventStats.player_id.in_([player1_id, player2_id]))
                .where(PlayerEventStats.event_id == diep_event_id)
            )
            diep_stats = result.scalars().all()
            
            assert len(diep_stats) == 2, f"Expected 2 PlayerEventStats for Diep, found {len(diep_stats)}"
            
            # Check winner has higher Elo
            p1_stats = next(s for s in diep_stats if s.player_id == player1_id)
            p2_stats = next(s for s in diep_stats if s.player_id == player2_id)
            
            assert p1_stats.raw_elo > 1000, "Winner should have Elo > 1000"
            assert p2_stats.raw_elo < 1000, "Loser should have Elo < 1000"
            assert p1_stats.matches_played == 1, "Should have 1 match played"
            assert p2_stats.matches_played == 1, "Should have 1 match played"
            
            print(f"   ✓ Player 1 Diep Elo: {p1_stats.raw_elo} (wins: {p1_stats.wins})")
            print(f"   ✓ Player 2 Diep Elo: {p2_stats.raw_elo} (losses: {p2_stats.losses})")
        
        # Step 4: Create match in different event (Blitz)
        print(f"\n5. Creating match in Blitz...")
        # Create second challenge
        async with db.transaction() as session:
            challenge2 = Challenge(
                challenger_id=player2_id,
                challenged_id=player1_id,
                event_id=blitz_event_id,
                status=ChallengeStatus.ACCEPTED,
                ticket_wager=0
            )
            session.add(challenge2)
            await session.flush()
            challenge2_id = challenge2.id
            created_challenge_ids.append(challenge2_id)
        
        # Create match from challenge
        match2 = await match_ops.create_match_from_challenge(challenge2_id)
        match2_id = match2.id
        created_match_ids.append(match2_id)
        print(f"   ✓ Created match {match2_id}")
        
        # Complete with opposite result
        async with db.transaction() as session:
            results2 = [
                {"player_id": player1_id, "placement": 2},  # Player 1 loses
                {"player_id": player2_id, "placement": 1}   # Player 2 wins
            ]
            match2 = await match_ops.complete_match_with_results(match2_id, results2)
            print(f"   ✓ Completed match with player 2 winning")
        
        # Step 5: Verify separate Elo tracking
        print(f"\n6. Verifying separate Elo tracking per event...")
        async with db.transaction() as session:
            # Check all PlayerEventStats
            result = await session.execute(
                select(PlayerEventStats, Event)
                .join(Event)
                .where(PlayerEventStats.player_id.in_([player1_id, player2_id]))
                .order_by(PlayerEventStats.player_id, Event.name)
            )
            
            all_stats = result.all()
            assert len(all_stats) == 4, f"Expected 4 total PlayerEventStats (2 players × 2 events), found {len(all_stats)}"
            
            # Verify different Elos per event
            for player_id in [player1_id, player2_id]:
                player_stats = [(s, e) for s, e in all_stats if s.player_id == player_id]
                diep_stat = next((s for s, e in player_stats if e.id == diep_event_id), None)
                blitz_stat = next((s for s, e in player_stats if e.id == blitz_event_id), None)
                
                assert diep_stat and blitz_stat, f"Missing stats for player {player_id}"
                assert diep_stat.raw_elo != blitz_stat.raw_elo, "Elos should differ between events"
                
                print(f"   ✓ Player {player_id}: Diep={diep_stat.raw_elo}, Blitz={blitz_stat.raw_elo}")
        
        # Step 6: Verify EloHistory has event_id
        print(f"\n7. Verifying EloHistory includes event_id...")
        async with db.transaction() as session:
            result = await session.execute(
                select(EloHistory)
                .where(EloHistory.player_id.in_([player1_id, player2_id]))
                .where(EloHistory.match_id.isnot(None))
            )
            
            history_records = result.scalars().all()
            assert len(history_records) == 4, f"Expected 4 EloHistory records, found {len(history_records)}"
            
            missing_event = [h for h in history_records if h.event_id is None]
            assert len(missing_event) == 0, f"Found {len(missing_event)} EloHistory records without event_id"
            print(f"   ✓ All {len(history_records)} EloHistory records have event_id")
        
        # Step 7: Verify global elo sync
        print(f"\n8. Verifying global elo matches latest match...")
        async with db.transaction() as session:
            result = await session.execute(
                select(Player).where(Player.id.in_([player1_id, player2_id]))
            )
            
            for player in result.scalars():
                # Get latest match participant record
                latest_result = await session.execute(
                    select(MatchParticipant)
                    .join(Match)
                    .where(MatchParticipant.player_id == player.id)
                    .where(Match.status == MatchStatus.COMPLETED)
                    .order_by(Match.completed_at.desc())
                    .limit(1)
                )
                latest_mp = latest_result.scalar_one()
                
                assert player.elo_rating == latest_mp.elo_after, \
                    f"Global elo {player.elo_rating} doesn't match latest match elo {latest_mp.elo_after}"
                print(f"   ✓ {player.username}: Global={player.elo_rating} matches latest match")
        
        print("\n✅ ALL TESTS PASSED!")
        print("   - PlayerEventStats created per event")
        print("   - Separate Elo tracking verified")
        print("   - Global elo syncs correctly")
        print("   - EloHistory includes event_id")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
        
    finally:
        # Comprehensive cleanup
        print("\n9. Cleaning up test data...")
        async with db.transaction() as session:
            # Delete in reverse order of creation to respect foreign keys
            if created_match_ids:
                await session.execute(
                    delete(Match).where(Match.id.in_(created_match_ids))
                )
            if created_challenge_ids:
                await session.execute(
                    delete(Challenge).where(Challenge.id.in_(created_challenge_ids))
                )
            # Player deletion should cascade to other tables
            await session.execute(
                delete(Player).where(Player.discord_id.in_([TEST_PLAYER_1_ID, TEST_PLAYER_2_ID]))
            )
        print("   ✓ Test data cleaned up")

if __name__ == "__main__":
    asyncio.run(test_phase_1_2())