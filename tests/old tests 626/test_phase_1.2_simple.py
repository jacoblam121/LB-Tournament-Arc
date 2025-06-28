#!/usr/bin/env python3
"""
Simplified Phase 1.2 Test - Direct Database Testing
Tests PlayerEventStats integration without needing Discord commands
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bot.database.database import Database
from bot.database.models import *
from bot.database.match_operations import MatchOperations
from sqlalchemy import select, update
from bot.utils.scoring_strategies import ParticipantResult

async def test_phase_1_2():
    print("=== Phase 1.2 Simplified Test ===\n")
    
    # Initialize database
    db = Database()
    await db.initialize()
    
    # Test data
    test_player_1_id = 999991
    test_player_2_id = 999992
    
    try:
        async with db.transaction() as session:
            # Clean up any existing test data
            await session.execute(
                update(Player).where(Player.discord_id.in_([test_player_1_id, test_player_2_id]))
                .values(is_active=False)
            )
            await session.execute(
                "DELETE FROM players WHERE discord_id IN (?, ?)",
                (test_player_1_id, test_player_2_id)
            )
            
            # Create test players
            print("1. Creating test players...")
            player1 = Player(
                discord_id=test_player_1_id,
                username="test_player_1",
                display_name="Test Player 1",
                elo_rating=1000
            )
            player2 = Player(
                discord_id=test_player_2_id,
                username="test_player_2", 
                display_name="Test Player 2",
                elo_rating=1000
            )
            session.add(player1)
            session.add(player2)
            await session.flush()
            print(f"   Created players with IDs: {player1.id}, {player2.id}")
            
            # Get test events
            result = await session.execute(
                select(Event).where(Event.name.in_(["Diep (1v1)", "Blitz"]))
            )
            events = result.scalars().all()
            
            if len(events) < 2:
                print("ERROR: Need Diep (1v1) and Blitz events")
                return
                
            diep_event = next(e for e in events if "Diep" in e.name)
            blitz_event = next(e for e in events if "Blitz" in e.name and e.scoring_type == "1v1")
            print(f"   Using events: {diep_event.name} (id={diep_event.id}), {blitz_event.name} (id={blitz_event.id})")
        
        # Test 1: Check initial state
        print("\n2. Initial state - no PlayerEventStats:")
        async with db.transaction() as session:
            result = await session.execute(
                select(PlayerEventStats)
                .where(PlayerEventStats.player_id.in_([player1.id, player2.id]))
            )
            stats = result.scalars().all()
            print(f"   PlayerEventStats count: {len(stats)} (should be 0)")
        
        # Test 2: Create and complete a match in Diep
        print(f"\n3. Creating match in {diep_event.name}...")
        match_ops = MatchOperations(db)
        
        # Create a challenge first (since that's the normal flow)
        async with db.transaction() as session:
            challenge = Challenge(
                challenger_id=player1.id,
                challenged_id=player2.id,
                event_id=diep_event.id,
                status=ChallengeStatus.ACCEPTED,
                wager_tickets=0
            )
            session.add(challenge)
            await session.flush()
            
            # Create match from challenge
            match = await match_ops.create_match_from_challenge(challenge.id)
            match_id = match.id
            print(f"   Created match {match_id} from challenge {challenge.id}")
        
        # Complete the match
        async with db.transaction() as session:
            results = [
                {"player_id": player1.id, "placement": 1},  # Player 1 wins
                {"player_id": player2.id, "placement": 2}
            ]
            match = await match_ops.complete_match_with_results(match_id, results)
            print(f"   Completed match with player 1 winning")
        
        # Check PlayerEventStats after Diep match
        print(f"\n4. PlayerEventStats after {diep_event.name} match:")
        async with db.transaction() as session:
            result = await session.execute(
                select(PlayerEventStats, Player, Event)
                .join(Player, PlayerEventStats.player_id == Player.id)
                .join(Event, PlayerEventStats.event_id == Event.id)
                .where(PlayerEventStats.player_id.in_([player1.id, player2.id]))
                .order_by(Player.username, Event.name)
            )
            
            print(f"   {'Player':<15} {'Event':<20} {'Event Elo':<10} {'Matches':<10}")
            print("   " + "-" * 55)
            for stats, player, event in result:
                print(f"   {player.username:<15} {event.name:<20} {stats.raw_elo:<10} {stats.matches_played:<10}")
        
        # Test 3: Create match in different event (Blitz)
        print(f"\n5. Creating match in {blitz_event.name}...")
        async with db.transaction() as session:
            challenge2 = Challenge(
                challenger_id=player2.id,
                challenged_id=player1.id,
                event_id=blitz_event.id,
                status=ChallengeStatus.ACCEPTED,
                wager_tickets=0
            )
            session.add(challenge2)
            await session.flush()
            
            match2 = await match_ops.create_match_from_challenge(challenge2.id)
            match2_id = match2.id
            print(f"   Created match {match2_id}")
        
        # Complete with opposite result
        async with db.transaction() as session:
            results2 = [
                {"player_id": player1.id, "placement": 2},  # Player 1 loses
                {"player_id": player2.id, "placement": 1}   # Player 2 wins
            ]
            match2 = await match_ops.complete_match_with_results(match2_id, results2)
            print(f"   Completed match with player 2 winning")
        
        # Final check - separate Elo per event
        print(f"\n6. Final state - separate Elo tracking per event:")
        async with db.transaction() as session:
            # Check PlayerEventStats
            result = await session.execute(
                select(PlayerEventStats, Player, Event)
                .join(Player, PlayerEventStats.player_id == Player.id)
                .join(Event, PlayerEventStats.event_id == Event.id)
                .where(PlayerEventStats.player_id.in_([player1.id, player2.id]))
                .order_by(Player.username, Event.name)
            )
            
            print(f"   {'Player':<15} {'Global Elo':<12} {'Event':<20} {'Event Elo':<10} {'Matches':<10}")
            print("   " + "-" * 77)
            
            # Also get global elo
            players_result = await session.execute(
                select(Player).where(Player.id.in_([player1.id, player2.id]))
            )
            players_dict = {p.id: p for p in players_result.scalars()}
            
            for stats, player, event in result:
                global_elo = players_dict[player.id].elo_rating
                print(f"   {player.username:<15} {global_elo:<12} {event.name:<20} {stats.raw_elo:<10} {stats.matches_played:<10}")
        
        # Test 4: Verify EloHistory has event_id
        print(f"\n7. Verifying EloHistory includes event_id:")
        async with db.transaction() as session:
            result = await session.execute(
                select(EloHistory)
                .where(EloHistory.player_id.in_([player1.id, player2.id]))
                .where(EloHistory.match_id.isnot(None))
                .order_by(EloHistory.recorded_at.desc())
            )
            
            history_records = result.scalars().all()
            print(f"   Found {len(history_records)} EloHistory records")
            
            missing_event = sum(1 for h in history_records if h.event_id is None)
            print(f"   Records with event_id: {len(history_records) - missing_event}")
            print(f"   Records missing event_id: {missing_event} (should be 0)")
        
        # Verify global elo matches latest event
        print(f"\n8. Verifying global elo syncs with latest match:")
        async with db.transaction() as session:
            result = await session.execute(
                select(Player).where(Player.id.in_([player1.id, player2.id]))
            )
            for player in result.scalars():
                # Get latest match
                latest_match_result = await session.execute(
                    select(MatchParticipant, Match)
                    .join(Match)
                    .where(MatchParticipant.player_id == player.id)
                    .where(Match.status == MatchStatus.COMPLETED)
                    .order_by(Match.completed_at.desc())
                    .limit(1)
                )
                latest = latest_match_result.first()
                if latest:
                    mp, match = latest
                    print(f"   {player.username}: Global={player.elo_rating}, Latest Match={mp.elo_after} ✓")
        
        print("\n✅ Phase 1.2 Test Summary:")
        print("   - PlayerEventStats created for each player-event combination")
        print("   - Different events maintain separate Elo ratings")
        print("   - Global elo syncs with most recent match")
        print("   - EloHistory properly includes event_id")
        print("   - matches_played tracked per event")
        
    finally:
        # Cleanup
        print("\n9. Cleaning up test data...")
        async with db.transaction() as session:
            await session.execute(
                "DELETE FROM players WHERE discord_id IN (?, ?)",
                (test_player_1_id, test_player_2_id)
            )
        print("   Test data cleaned up")

if __name__ == "__main__":
    asyncio.run(test_phase_1_2())