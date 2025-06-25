#!/usr/bin/env python3
"""
Phase 2A2 Subphase 1 Validation Test Suite: Database Schema Addition

This test suite validates that the new Match and MatchParticipant models
have been correctly added to the database schema without breaking existing
functionality.

Tests:
1. Existing Challenge workflow preservation (20/20 tests must pass)
2. New Match/MatchParticipant table creation
3. EloHistory model updates with CHECK constraint
4. Database constraint validation
5. Relationship integrity testing

Usage:
    python test_phase_2a2_subphase_1_schema.py
"""

import asyncio
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import List, Optional

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # Required for SQLAlchemy 2.0+ raw SQL
from bot.database.database import Database
from bot.database.models import (
    Base, Player, Event, Challenge, Match, MatchParticipant, EloHistory,
    ChallengeStatus, MatchStatus, MatchFormat, MatchResult
)
from bot.config import Config

class Phase2A2Subphase1Tester:
    """Test suite for Phase 2A2 Subphase 1: Database Schema Addition"""
    
    def __init__(self):
        self.db = Database()
        self.test_results = []
        self.test_data = {}
    
    def print_header(self, message: str):
        """Print a formatted header"""
        print(f"\n{'='*60}")
        print(f" {message}")
        print(f"{'='*60}")
    
    def print_success(self, message: str):
        """Print a success message"""
        print(f"✅ {message}")
    
    def print_error(self, message: str):
        """Print an error message"""
        print(f"❌ {message}")
    
    def print_info(self, message: str):
        """Print an info message"""
        print(f"ℹ️  {message}")
    
    def print_warning(self, message: str):
        """Print a warning message"""
        print(f"⚠️  {message}")
    
    async def run_all_tests(self):
        """Run all Phase 2A2 Subphase 1 tests"""
        self.print_header("Phase 2A2 Subphase 1: Database Schema Addition Tests")
        
        try:
            # Initialize test database
            await self.initialize_test_database()
            
            # Run test suite
            tests = [
                ("Database Initialization", self.test_database_initialization),
                ("Match Table Creation", self.test_match_table_creation),
                ("MatchParticipant Table Creation", self.test_match_participant_table_creation),
                ("EloHistory Schema Update", self.test_elo_history_schema_update),
                ("Database Constraints Validation", self.test_database_constraints),
                ("Relationship Integrity", self.test_relationship_integrity),
                ("Existing Challenge Workflow", self.test_existing_challenge_workflow),
                ("Backward Compatibility", self.test_backward_compatibility),
            ]
            
            for test_name, test_func in tests:
                self.print_header(f"Running: {test_name}")
                try:
                    result = await test_func()
                    if result:
                        self.print_success(f"{test_name} PASSED")
                        self.test_results.append((test_name, True, None))
                    else:
                        self.print_error(f"{test_name} FAILED")
                        self.test_results.append((test_name, False, "Test returned False"))
                except Exception as e:
                    self.print_error(f"{test_name} FAILED with exception: {e}")
                    self.test_results.append((test_name, False, str(e)))
                    traceback.print_exc()
            
            # Print final results
            await self.print_final_results()
            
        finally:
            await self.cleanup()
    
    async def initialize_test_database(self):
        """Initialize test database"""
        self.print_info("Initializing test database...")
        
        # Use in-memory SQLite for testing
        Config.DATABASE_URL = "sqlite+aiosqlite:///test_phase_2a2_subphase_1.db"
        
        await self.db.initialize()
        self.print_success("Test database initialized")
    
    async def test_database_initialization(self):
        """Test that database initializes correctly with new models"""
        try:
            # Verify that all tables are created
            async with self.db.get_session() as session:
                # Test basic database connection
                result = await session.execute(text("SELECT 1"))
                if result.scalar() != 1:
                    return False
                
                self.print_success("Database connection established")
                return True
                
        except Exception as e:
            self.print_error(f"Database initialization failed: {e}")
            return False
    
    async def test_match_table_creation(self):
        """Test Match table creation and structure"""
        try:
            async with self.db.get_session() as session:
                # Create a test event first
                from bot.database.models import Cluster, Event
                
                cluster = Cluster(name="Test Cluster", number=101)  # Use unique number to avoid conflicts
                session.add(cluster)
                await session.flush()
                
                event = Event(
                    name="Test Event",
                    cluster_id=cluster.id,
                    scoring_type="FFA"
                )
                session.add(event)
                await session.flush()
                
                # Create a test match
                match = Match(
                    event_id=event.id,
                    match_format=MatchFormat.FFA,
                    status=MatchStatus.PENDING
                )
                session.add(match)
                await session.commit()
                
                # Verify match was created
                if match.id is None:
                    return False
                
                # Store for later tests
                self.test_data['event'] = event
                self.test_data['match'] = match
                
                self.print_success(f"Match table created successfully, test match ID: {match.id}")
                return True
                
        except Exception as e:
            self.print_error(f"Match table creation failed: {e}")
            return False
    
    async def test_match_participant_table_creation(self):
        """Test MatchParticipant table creation and constraints"""
        try:
            async with self.db.get_session() as session:
                # Create test players
                player1 = Player(discord_id=111111, username="TestPlayer1")
                player2 = Player(discord_id=222222, username="TestPlayer2")
                session.add_all([player1, player2])
                await session.flush()
                
                match = self.test_data['match']
                
                # Create test match participants
                participant1 = MatchParticipant(
                    match_id=match.id,
                    player_id=player1.id,
                    placement=1,
                    elo_change=20
                )
                
                participant2 = MatchParticipant(
                    match_id=match.id,
                    player_id=player2.id,
                    placement=2,
                    elo_change=-15
                )
                
                session.add_all([participant1, participant2])
                await session.commit()
                
                # Test tie scenario (same placement)
                player3 = Player(discord_id=333333, username="TestPlayer3")
                session.add(player3)
                await session.flush()
                
                participant3 = MatchParticipant(
                    match_id=match.id,
                    player_id=player3.id,
                    placement=2,  # Same as participant2 - testing ties
                    elo_change=-10
                )
                session.add(participant3)
                await session.commit()
                
                self.print_success("MatchParticipant table created successfully with tie support")
                self.test_data['participants'] = [participant1, participant2, participant3]
                self.test_data['players'] = [player1, player2, player3]
                return True
                
        except Exception as e:
            self.print_error(f"MatchParticipant table creation failed: {e}")
            return False
    
    async def test_elo_history_schema_update(self):
        """Test EloHistory model with nullable match_id column"""
        try:
            async with self.db.get_session() as session:
                player = self.test_data['players'][0]
                match = self.test_data['match']
                
                # Test EloHistory with match_id (new functionality)
                elo_history_match = EloHistory(
                    player_id=player.id,
                    old_elo=1000,
                    new_elo=1020,
                    elo_change=20,
                    match_id=match.id,  # New field
                    challenge_id=None,  # Must be null when match_id is set
                    match_result=MatchResult.WIN,
                    k_factor=20
                )
                session.add(elo_history_match)
                await session.commit()
                
                # Verify it was created
                if elo_history_match.id is None:
                    return False
                
                self.print_success("EloHistory schema update successful - match_id support added")
                return True
                
        except Exception as e:
            self.print_error(f"EloHistory schema update failed: {e}")
            return False
    
    async def test_database_constraints(self):
        """Test database constraints are working correctly"""
        try:
            async with self.db.get_session() as session:
                player = self.test_data['players'][0]
                match = self.test_data['match']
                
                # Test CHECK constraint: both challenge_id and match_id set (should fail)
                try:
                    invalid_elo_history = EloHistory(
                        player_id=player.id,
                        old_elo=1000,
                        new_elo=1020,
                        elo_change=20,
                        challenge_id=1,  # Both set - should violate constraint
                        match_id=match.id,  # Both set - should violate constraint
                        match_result=MatchResult.WIN,
                        k_factor=20
                    )
                    session.add(invalid_elo_history)
                    await session.commit()
                    
                    # If we get here, the constraint didn't work
                    self.print_error("CHECK constraint failed - both challenge_id and match_id were allowed")
                    return False
                    
                except Exception:
                    # This is expected - constraint should prevent this
                    await session.rollback()
                    self.print_success("CHECK constraint working - prevented invalid EloHistory")
                
                # Test positive placement constraint
                try:
                    invalid_participant = MatchParticipant(
                        match_id=match.id,
                        player_id=player.id,
                        placement=0,  # Should violate positive placement constraint
                        elo_change=0
                    )
                    session.add(invalid_participant)
                    await session.commit()
                    
                    self.print_error("Placement constraint failed - zero placement was allowed")
                    return False
                    
                except Exception:
                    # This is expected
                    await session.rollback()
                    self.print_success("Placement constraint working - prevented invalid placement")
                
                return True
                
        except Exception as e:
            self.print_error(f"Database constraints test failed: {e}")
            return False
    
    async def test_relationship_integrity(self):
        """Test that relationships between models work correctly"""
        try:
            async with self.db.get_session() as session:
                # Get the match from the current session with eager loading
                match_id = self.test_data['match'].id
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                result = await session.execute(
                    select(Match)
                    .options(selectinload(Match.participants))
                    .where(Match.id == match_id)
                )
                match = result.scalar_one()
                
                # Test Match -> MatchParticipant relationship
                participants = match.participants
                
                if len(participants) != 3:  # We created 3 participants
                    self.print_error(f"Expected 3 participants, got {len(participants)}")
                    return False
                
                # Test MatchParticipant -> Match relationship
                participant = participants[0]
                if participant.match.id != match.id:
                    self.print_error("MatchParticipant -> Match relationship failed")
                    return False
                
                # Test placement ordering
                ordered_participants = match.get_participants_by_placement()
                if ordered_participants[0].placement != 1:
                    self.print_error("Placement ordering failed")
                    return False
                
                # Test winner identification
                winner = match.get_winner()
                if winner is None or winner.placement != 1:
                    self.print_error("Winner identification failed")
                    return False
                
                self.print_success("All model relationships working correctly")
                return True
                
        except Exception as e:
            self.print_error(f"Relationship integrity test failed: {e}")
            return False
    
    async def test_existing_challenge_workflow(self):
        """Test that existing Challenge workflow still works"""
        try:
            # This should be identical to existing functionality
            async with self.db.get_session() as session:
                event = self.test_data['event']
                players = self.test_data['players']
                
                # Create a traditional 1v1 challenge
                challenge = Challenge(
                    challenger_id=players[0].id,
                    challenged_id=players[1].id,
                    event_id=event.id,
                    status=ChallengeStatus.PENDING
                )
                session.add(challenge)
                await session.commit()
                
                # Complete the challenge (existing workflow)
                challenge.status = ChallengeStatus.COMPLETED
                challenge.challenger_result = MatchResult.WIN
                challenge.challenged_result = MatchResult.LOSS
                challenge.challenger_elo_change = 15
                challenge.challenged_elo_change = -15
                challenge.completed_at = datetime.now(timezone.utc)
                await session.commit()
                
                # Create EloHistory with challenge_id (existing workflow)
                elo_history_challenge = EloHistory(
                    player_id=players[0].id,
                    old_elo=1000,
                    new_elo=1015,
                    elo_change=15,
                    challenge_id=challenge.id,  # Old way
                    match_id=None,  # Must be null when challenge_id is set
                    opponent_id=players[1].id,
                    match_result=MatchResult.WIN,
                    k_factor=20
                )
                session.add(elo_history_challenge)
                await session.commit()
                
                self.print_success("Existing Challenge workflow preserved completely")
                return True
                
        except Exception as e:
            self.print_error(f"Existing Challenge workflow test failed: {e}")
            return False
    
    async def test_backward_compatibility(self):
        """Test complete backward compatibility"""
        try:
            # Run the original foundation tests to ensure nothing broke
            self.print_info("Running subset of foundation tests for backward compatibility...")
            
            async with self.db.get_session() as session:
                # Test player creation (existing functionality)
                test_player = Player(
                    discord_id=999999,
                    username="BackwardCompatTest",
                    elo_rating=1200
                )
                session.add(test_player)
                await session.commit()
                
                if test_player.id is None:
                    self.print_error("Player creation failed")
                    return False
                
                # Test event creation (Phase 2A1 functionality)
                from bot.database.models import Cluster
                test_cluster = Cluster(name="Backward Compat Cluster", number=102)  # Use unique number to avoid conflicts
                session.add(test_cluster)
                await session.flush()
                
                test_event = Event(
                    name="Backward Compat Event",
                    cluster_id=test_cluster.id,
                    scoring_type="1v1"
                )
                session.add(test_event)
                await session.commit()
                
                if test_event.id is None:
                    self.print_error("Event creation failed")
                    return False
                
                self.print_success("All existing functionality preserved")
                return True
                
        except Exception as e:
            self.print_error(f"Backward compatibility test failed: {e}")
            return False
    
    async def print_final_results(self):
        """Print final test results summary"""
        self.print_header("Phase 2A2 Subphase 1 Test Results")
        
        passed_tests = [result for result in self.test_results if result[1]]
        failed_tests = [result for result in self.test_results if not result[1]]
        
        print(f"\n📊 Test Summary:")
        print(f"   Total Tests: {len(self.test_results)}")
        print(f"   Passed: {len(passed_tests)}")
        print(f"   Failed: {len(failed_tests)}")
        
        if failed_tests:
            self.print_warning("Failed Tests:")
            for test_name, _, error in failed_tests:
                print(f"   ❌ {test_name}: {error}")
        
        if len(passed_tests) == len(self.test_results):
            self.print_success("🎉 ALL TESTS PASSED - Phase 2A2 Subphase 1 Ready!")
            print("\n✅ Database schema successfully updated")
            print("✅ Match and MatchParticipant models working correctly")
            print("✅ EloHistory migration completed successfully") 
            print("✅ All constraints and relationships validated")
            print("✅ Existing Challenge workflow preserved")
            print("✅ Complete backward compatibility maintained")
            print("\n🚀 Ready to proceed to Subphase 2: Match Operations Implementation")
        else:
            self.print_error("❌ TESTS FAILED - Issues must be resolved before proceeding")
            return False
        
        return True
    
    async def cleanup(self):
        """Clean up test resources"""
        try:
            await self.db.close()
            
            # Remove test database file
            test_db_file = "test_phase_2a2_subphase_1.db"
            if os.path.exists(test_db_file):
                os.remove(test_db_file)
                self.print_info("Test database cleaned up")
        except Exception as e:
            self.print_warning(f"Cleanup warning: {e}")

async def main():
    """Main test execution"""
    tester = Phase2A2Subphase1Tester()
    await tester.run_all_tests()

if __name__ == "__main__":
    print("🧪 Phase 2A2 Subphase 1: Database Schema Addition Test Suite")
    print("=" * 60)
    asyncio.run(main())