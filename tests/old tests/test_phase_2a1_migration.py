#!/usr/bin/env python3
"""
Phase 2A1 Migration Test Suite
Tests the Game→Event migration and Challenge model updates

This test suite should be run manually by the user to verify:
1. Migration script works correctly
2. Challenge model uses event_id instead of game_id  
3. Database operations work with Events
4. Existing functionality is preserved
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from typing import Optional, List

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from bot.config import Config
from bot.database.database import Database
from bot.database.models import Player, Game, Event, Challenge, ChallengeStatus, MatchResult, Cluster
from bot.utils.elo import EloCalculator

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class Phase2A1TestSuite:
    def __init__(self):
        self.db: Optional[Database] = None
        self.test_results = []
        self.test_players = []
        
    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log a test result"""
        status = f"{Colors.GREEN}✅ PASS" if passed else f"{Colors.RED}❌ FAIL"
        print(f"{status}{Colors.END} - {test_name}")
        if details:
            print(f"    {details}")
        self.test_results.append((test_name, passed, details))
    
    def print_header(self, title: str):
        """Print a formatted header"""
        print(f"\n{Colors.BLUE}{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BLUE}{Colors.BOLD}{title.center(60)}{Colors.END}")
        print(f"{Colors.BLUE}{Colors.BOLD}{'='*60}{Colors.END}")
    
    async def setup_test_environment(self):
        """Setup test environment"""
        self.print_header("Setting Up Test Environment")
        
        try:
            # Use test database
            Config.DATABASE_URL = 'sqlite+aiosqlite:///test_phase_2a1.db'
            
            # Initialize database
            self.db = Database()
            await self.db.initialize()
            self.log_test("Database initialization", True, "Test database created")
            
            return True
            
        except Exception as e:
            self.log_test("Database initialization", False, str(e))
            return False
    
    async def test_event_model_structure(self):
        """Test that Event model has required fields for challenges"""
        self.print_header("Testing Event Model Structure")
        
        try:
            # Get all events
            events = await self.db.get_all_events()
            self.log_test("Event retrieval", len(events) > 0, f"Found {len(events)} events")
            
            if events:
                event = events[0]
                # Check required fields
                required_fields = ['id', 'name', 'scoring_type', 'cluster_id', 'allow_challenges']
                for field in required_fields:
                    assert hasattr(event, field), f"Event missing field: {field}"
                
                self.log_test("Event model structure", True, f"Event has all required fields")
                
                # Check scoring types
                scoring_types = {event.scoring_type for event in events}
                self.log_test("Scoring types variety", len(scoring_types) > 1, 
                             f"Found scoring types: {sorted(scoring_types)}")
            
        except Exception as e:
            self.log_test("Event model structure", False, str(e))
    
    async def test_challenge_model_migration(self):
        """Test that Challenge model uses event_id instead of game_id"""
        self.print_header("Testing Challenge Model Migration")
        
        try:
            # Create test players first
            player1 = await self.db.create_player(
                discord_id=99991,
                username="testuser1",
                display_name="Test User 1"
            )
            player2 = await self.db.create_player(
                discord_id=99992,
                username="testuser2", 
                display_name="Test User 2"
            )
            self.test_players = [player1, player2]
            
            # Get an event for testing
            events = await self.db.get_all_events()
            test_event = None
            for event in events:
                if event.scoring_type == "1v1" and event.allow_challenges:
                    test_event = event
                    break
            
            if not test_event:
                self.log_test("Challenge model migration", False, "No suitable 1v1 event found for testing")
                return
            
            # Create challenge using event_id (new way)
            challenge = await self.db.create_challenge(
                challenger_id=player1.id,
                challenged_id=player2.id,
                event_id=test_event.id,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            
            # Verify challenge was created correctly
            assert challenge.event_id == test_event.id
            assert hasattr(challenge, 'event_id')
            assert not hasattr(challenge, 'game_id')  # Should not have old field
            
            self.log_test("Challenge creation with event_id", True, 
                         f"Challenge {challenge.id} created for event '{test_event.name}'")
            
            # Test challenge retrieval with relationships
            retrieved_challenge = await self.db.get_challenge_by_id(challenge.id)
            assert retrieved_challenge is not None
            assert retrieved_challenge.event is not None
            assert retrieved_challenge.event.name == test_event.name
            
            self.log_test("Challenge-Event relationship", True, 
                         f"Challenge linked to event '{retrieved_challenge.event.name}'")
            
        except Exception as e:
            self.log_test("Challenge model migration", False, str(e))
    
    async def test_database_operations(self):
        """Test database operations work with Events instead of Games"""
        self.print_header("Testing Database Operations")
        
        try:
            # Test event search by name
            event = await self.db.get_event_by_name("Chess")
            if event:
                self.log_test("Event search by name", True, f"Found event: {event.name}")
            else:
                self.log_test("Event search by name", False, "Could not find 'Chess' event")
            
            # Test event_for_challenge helper
            event = await self.db.get_event_for_challenge("Chess")
            if event:
                self.log_test("Event for challenge helper", True, f"Helper found: {event.name}")
            else:
                self.log_test("Event for challenge helper", False, "Helper method failed")
            
            # Test challenge queries work with event relationships
            if self.test_players:
                player = self.test_players[0]
                challenges = await self.db.get_active_challenges_for_player(player.id)
                self.log_test("Active challenges query", True, 
                             f"Found {len(challenges)} active challenges for player")
                
                # Verify challenge has event relationship loaded
                if challenges:
                    challenge = challenges[0]
                    assert challenge.event is not None
                    self.log_test("Challenge event relationship", True, 
                                 f"Challenge linked to event '{challenge.event.name}'")
                    
        except Exception as e:
            self.log_test("Database operations", False, str(e))
    
    async def test_challenge_workflow_compatibility(self):
        """Test that challenge workflow still works after migration"""
        self.print_header("Testing Challenge Workflow Compatibility")
        
        try:
            if not self.test_players or len(self.test_players) < 2:
                self.log_test("Challenge workflow", False, "Not enough test players")
                return
            
            player1, player2 = self.test_players[0], self.test_players[1]
            
            # Find a 1v1 event
            events = await self.db.get_all_events()
            test_event = None
            for event in events:
                if event.scoring_type == "1v1":
                    test_event = event
                    break
            
            if not test_event:
                self.log_test("Challenge workflow", False, "No 1v1 event available")
                return
            
            # Create challenge
            challenge = await self.db.create_challenge(
                challenger_id=player1.id,
                challenged_id=player2.id,
                event_id=test_event.id
            )
            
            # Accept challenge
            await self.db.update_challenge_status(
                challenge.id, 
                ChallengeStatus.ACCEPTED.value,
                accepted_at=datetime.utcnow()
            )
            
            # Complete challenge (simulate match result)
            await self.db.update_challenge_status(
                challenge.id,
                ChallengeStatus.COMPLETED.value,
                completed_at=datetime.utcnow(),
                challenger_result=MatchResult.WIN.value,
                challenged_result=MatchResult.LOSS.value
            )
            
            # Test Elo calculations still work
            p1_change, p2_change = EloCalculator.calculate_match_elo_changes(
                player1.elo_rating, player1.matches_played,
                player2.elo_rating, player2.matches_played,
                True  # player1 won
            )
            
            # Record Elo changes
            await self.db.record_elo_change(
                player1.id, player1.elo_rating, player1.elo_rating + p1_change,
                challenge.id, player2.id, MatchResult.WIN, 
                EloCalculator.get_k_factor(player1.matches_played)
            )
            
            await self.db.record_elo_change(
                player2.id, player2.elo_rating, player2.elo_rating + p2_change,
                challenge.id, player1.id, MatchResult.LOSS,
                EloCalculator.get_k_factor(player2.matches_played)
            )
            
            self.log_test("Challenge workflow", True, 
                         f"Complete 1v1 workflow: {player1.username} vs {player2.username}")
            self.log_test("Elo calculations", True, 
                         f"Elo changes: {p1_change:+d}, {p2_change:+d}")
            
        except Exception as e:
            self.log_test("Challenge workflow compatibility", False, str(e))
    
    async def test_legacy_compatibility(self):
        """Test that legacy systems still work (Games still exist but deprecated)"""
        self.print_header("Testing Legacy Compatibility")
        
        try:
            # Games should still exist but be deprecated
            games = await self.db.get_all_games()
            self.log_test("Legacy games exist", len(games) > 0, 
                         f"Found {len(games)} legacy games (deprecated)")
            
            # Game operations should still work
            if games:
                game = await self.db.get_game_by_name(games[0].name)
                self.log_test("Legacy game search", game is not None, 
                             f"Can still find game: {game.name if game else 'None'}")
            
        except Exception as e:
            self.log_test("Legacy compatibility", False, str(e))
    
    async def test_cluster_event_structure(self):
        """Test that Cluster-Event hierarchy works correctly"""
        self.print_header("Testing Cluster-Event Structure")
        
        try:
            # Get clusters
            clusters = await self.db.get_all_clusters()
            self.log_test("Cluster retrieval", len(clusters) > 0, 
                         f"Found {len(clusters)} clusters")
            
            if clusters:
                cluster = clusters[0]
                cluster_with_events = await self.db.get_cluster_by_id(cluster.id)
                
                if hasattr(cluster_with_events, 'events') and cluster_with_events.events:
                    self.log_test("Cluster-Event relationships", True, 
                                 f"Cluster '{cluster.name}' has {len(cluster_with_events.events)} events")
                    
                    # Test event belongs to cluster
                    event = cluster_with_events.events[0]
                    assert event.cluster_id == cluster.id
                    self.log_test("Event cluster assignment", True, 
                                 f"Event '{event.name}' assigned to cluster {cluster.number}")
                else:
                    self.log_test("Cluster-Event relationships", False, 
                                 "Cluster has no events")
            
        except Exception as e:
            self.log_test("Cluster-Event structure", False, str(e))
    
    async def cleanup(self):
        """Clean up test resources"""
        if self.db:
            await self.db.close()
        
        # Remove test database
        try:
            if os.path.exists('test_phase_2a1.db'):
                os.remove('test_phase_2a1.db')
            print(f"\n{Colors.YELLOW}🧹 Cleaned up test database{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}⚠️ Warning: Could not clean up test database: {e}{Colors.END}")
    
    def print_summary(self):
        """Print test summary"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, passed, _ in self.test_results if passed)
        failed_tests = total_tests - passed_tests
        
        print(f"\n" + "="*60)
        print(f"{Colors.BOLD}📋 PHASE 2A1 MIGRATION TEST SUMMARY{Colors.END}")
        print(f"="*60)
        print(f"Total Tests:  {total_tests}")
        print(f"{Colors.GREEN}Passed:       {passed_tests} ✅{Colors.END}")
        print(f"{Colors.RED}Failed:       {failed_tests} ❌{Colors.END}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "No tests run")
        
        if failed_tests > 0:
            print(f"\n{Colors.RED}❌ FAILED TESTS:{Colors.END}")
            for test_name, passed, details in self.test_results:
                if not passed:
                    print(f"  • {test_name}: {details}")
            print(f"\n{Colors.RED}🚨 Migration verification FAILED - do not proceed to Phase 2A2{Colors.END}")
        else:
            print(f"\n{Colors.GREEN}🎉 All migration tests passed! Ready for Phase 2A2.{Colors.END}")
        
        return failed_tests == 0

async def main():
    """Run Phase 2A1 migration tests"""
    print(f"{Colors.BOLD}🧪 Tournament Bot - Phase 2A1 Migration Tests{Colors.END}")
    print("=" * 60)
    print("This test suite verifies the Game→Event migration is working correctly.")
    print("DO NOT proceed to Phase 2A2 unless all tests pass.")
    print()
    
    tester = Phase2A1TestSuite()
    
    try:
        if not await tester.setup_test_environment():
            print(f"{Colors.RED}Failed to setup test environment{Colors.END}")
            return 1
        
        await tester.test_event_model_structure()
        await tester.test_challenge_model_migration()
        await tester.test_database_operations()
        await tester.test_challenge_workflow_compatibility()
        await tester.test_legacy_compatibility()
        await tester.test_cluster_event_structure()
        
        success = tester.print_summary()
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n{Colors.RED}💥 CRITICAL ERROR: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        await tester.cleanup()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)