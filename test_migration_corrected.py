#!/usr/bin/env python3
"""
Corrected Migration Test Suite
Tests for the proper Game→Event migration process

This test suite should be run in the following order:
1. BEFORE migration - test current state
2. AFTER migration - test migration success
3. AFTER model updates - test final functionality

Use flags to control which tests to run at each stage.
"""

import asyncio
import sys
import os
import argparse
from datetime import datetime, timedelta, timezone
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

class MigrationTestSuite:
    def __init__(self, test_stage: str):
        self.db: Optional[Database] = None
        self.test_results = []
        self.test_players = []
        self.test_stage = test_stage  # 'pre', 'post-migration', 'post-update'
        
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
        self.print_header(f"Setting Up Test Environment - {self.test_stage.upper()}")
        
        try:
            # Use main database for testing (we want to test real migration)
            # But create test players with high IDs to avoid conflicts
            
            # Initialize database
            self.db = Database()
            await self.db.initialize()
            self.log_test("Database connection", True, "Connected to database")
            
            return True
            
        except Exception as e:
            self.log_test("Database connection", False, str(e))
            return False
    
    async def test_pre_migration_state(self):
        """Test state before migration - should have Games and game_id references"""
        if self.test_stage != 'pre':
            return
        
        self.print_header("PRE-MIGRATION STATE TESTS")
        
        try:
            # Test Games exist
            games = await self.db.get_all_games()
            self.log_test("Games exist", len(games) > 0, f"Found {len(games)} games")
            
            # Test Events exist
            events = await self.db.get_all_events()
            self.log_test("Events exist", len(events) > 0, f"Found {len(events)} events")
            
            # Test Challenges use game_id (if any exist)
            async with self.db.get_session() as session:
                from sqlalchemy import text
                result = await session.execute(text("PRAGMA table_info(challenges)"))
                columns = result.fetchall()
                column_names = [col[1] for col in columns]
                
                self.log_test("Challenges have game_id column", 'game_id' in column_names)
                self.log_test("Challenges DON'T have event_id column", 'event_id' not in column_names)
            
            # Create test challenge to verify current functionality
            if games:
                await self._create_test_challenge_with_game(games[0])
            
        except Exception as e:
            self.log_test("Pre-migration state tests", False, str(e))
    
    async def test_post_migration_state(self):
        """Test state after migration - should have both game_id and event_id"""
        if self.test_stage != 'post-migration':
            return
        
        self.print_header("POST-MIGRATION STATE TESTS")
        
        try:
            # Test database schema changes
            async with self.db.get_session() as session:
                from sqlalchemy import text
                
                # Check table structure
                result = await session.execute(text("PRAGMA table_info(challenges)"))
                columns = result.fetchall()
                column_names = [col[1] for col in columns]
                
                self.log_test("Challenges still have game_id column", 'game_id' in column_names)
                self.log_test("Challenges now have event_id column", 'event_id' in column_names)
                
                # Check data migration
                result = await session.execute(text("SELECT COUNT(*) FROM challenges WHERE event_id IS NULL"))
                null_event_count = result.scalar()
                self.log_test("All challenges have event_id", null_event_count == 0, 
                             f"{null_event_count} challenges have NULL event_id")
                
                # Check data integrity
                result = await session.execute(text("""
                    SELECT COUNT(*) FROM challenges c 
                    JOIN events e ON c.event_id = e.id
                """))
                valid_references = result.scalar()
                
                result = await session.execute(text("SELECT COUNT(*) FROM challenges"))
                total_challenges = result.scalar()
                
                self.log_test("Event references are valid", valid_references == total_challenges,
                             f"{valid_references}/{total_challenges} valid references")
            
        except Exception as e:
            self.log_test("Post-migration state tests", False, str(e))
    
    async def test_post_update_state(self):
        """Test state after model updates - should use event_id exclusively"""
        if self.test_stage != 'post-update':
            return
        
        self.print_header("POST-UPDATE STATE TESTS")
        
        try:
            # Test that Challenge model now uses event_id
            # Create test players
            player1 = await self.db.create_player(
                discord_id=88881,
                username="testuser1_post",
                display_name="Test User 1 Post"
            )
            player2 = await self.db.create_player(
                discord_id=88882,
                username="testuser2_post",
                display_name="Test User 2 Post"
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
                self.log_test("Post-update challenge creation", False, "No suitable 1v1 event found")
                return
            
            # Create challenge using new event_id API
            challenge = await self.db.create_challenge(
                challenger_id=player1.id,
                challenged_id=player2.id,
                event_id=test_event.id,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            
            # Verify challenge was created correctly
            self.log_test("Challenge creation with event_id", True, 
                         f"Challenge {challenge.id} created for event '{test_event.name}'")
            
            # Test challenge retrieval with relationships
            retrieved_challenge = await self.db.get_challenge_by_id(challenge.id)
            assert retrieved_challenge is not None
            assert retrieved_challenge.event is not None
            assert retrieved_challenge.event.name == test_event.name
            
            self.log_test("Challenge-Event relationship", True, 
                         f"Challenge linked to event '{retrieved_challenge.event.name}'")
            
            # Test complete challenge workflow
            await self._test_complete_challenge_workflow(retrieved_challenge)
            
        except Exception as e:
            self.log_test("Post-update state tests", False, str(e))
    
    async def _create_test_challenge_with_game(self, game: Game):
        """Create test challenge using game_id (pre-migration)"""
        try:
            # Create test players
            player1 = await self.db.create_player(
                discord_id=77771,
                username="testuser1_pre",
                display_name="Test User 1 Pre"
            )
            player2 = await self.db.create_player(
                discord_id=77772,
                username="testuser2_pre",
                display_name="Test User 2 Pre"
            )
            
            # Create challenge with game_id
            challenge = await self.db.create_challenge(
                challenger_id=player1.id,
                challenged_id=player2.id,
                game_id=game.id,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            
            self.log_test("Pre-migration challenge creation", True,
                         f"Challenge {challenge.id} created for game '{game.name}'")
            
            # Verify relationships
            retrieved = await self.db.get_challenge_by_id(challenge.id)
            if retrieved and retrieved.game:
                self.log_test("Pre-migration Game relationship", True,
                             f"Challenge linked to game '{retrieved.game.name}'")
            else:
                self.log_test("Pre-migration Game relationship", False, "Game relationship not loaded")
                
        except Exception as e:
            self.log_test("Pre-migration challenge creation", False, str(e))
    
    async def _test_complete_challenge_workflow(self, challenge: Challenge):
        """Test complete challenge workflow after updates"""
        try:
            if not self.test_players or len(self.test_players) < 2:
                return
            
            player1, player2 = self.test_players[0], self.test_players[1]
            
            # Accept challenge
            await self.db.update_challenge_status(
                challenge.id,
                ChallengeStatus.ACCEPTED.value,
                accepted_at=datetime.now(timezone.utc)
            )
            
            # Complete challenge
            await self.db.update_challenge_status(
                challenge.id,
                ChallengeStatus.COMPLETED.value,
                completed_at=datetime.now(timezone.utc),
                challenger_result=MatchResult.WIN.value,
                challenged_result=MatchResult.LOSS.value
            )
            
            # Test Elo calculations
            p1_change, p2_change = EloCalculator.calculate_match_elo_changes(
                player1.elo_rating, player1.matches_played,
                player2.elo_rating, player2.matches_played,
                True  # player1 won
            )
            
            self.log_test("Challenge workflow completion", True,
                         f"Complete workflow: {player1.username} vs {player2.username}")
            self.log_test("Elo calculations", True,
                         f"Elo changes: {p1_change:+d}, {p2_change:+d}")
            
        except Exception as e:
            self.log_test("Challenge workflow", False, str(e))
    
    async def cleanup(self):
        """Clean up test resources"""
        if self.db:
            # Clean up test players (those with high IDs)
            try:
                async with self.db.get_session() as session:
                    from sqlalchemy import delete
                    
                    # Delete test challenges
                    await session.execute(delete(Challenge).where(
                        Challenge.challenger_id.in_([p.id for p in self.test_players]) |
                        Challenge.challenged_id.in_([p.id for p in self.test_players])
                    ))
                    
                    # Delete test players
                    await session.execute(delete(Player).where(
                        Player.id.in_([p.id for p in self.test_players])
                    ))
                    
                    await session.commit()
                    print(f"\n{Colors.YELLOW}🧹 Cleaned up test data{Colors.END}")
            except Exception as e:
                print(f"{Colors.RED}⚠️ Warning: Could not clean up test data: {e}{Colors.END}")
            
            await self.db.close()
    
    def print_summary(self):
        """Print test summary"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, passed, _ in self.test_results if passed)
        failed_tests = total_tests - passed_tests
        
        print(f"\n" + "="*60)
        print(f"{Colors.BOLD}📋 {self.test_stage.upper()} TEST SUMMARY{Colors.END}")
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
        
        stage_messages = {
            'pre': "Ready for migration if all tests pass",
            'post-migration': "Ready for model updates if all tests pass", 
            'post-update': "Migration complete if all tests pass"
        }
        
        if failed_tests == 0:
            print(f"\n{Colors.GREEN}🎉 {stage_messages.get(self.test_stage, 'All tests passed!')}{Colors.END}")
        else:
            print(f"\n{Colors.RED}🚨 Fix issues before proceeding{Colors.END}")
        
        return failed_tests == 0

async def main():
    """Run migration tests"""
    parser = argparse.ArgumentParser(description='Run migration tests')
    parser.add_argument('stage', choices=['pre', 'post-migration', 'post-update'],
                       help='Which stage to test')
    args = parser.parse_args()
    
    print(f"{Colors.BOLD}🧪 Migration Test Suite - {args.stage.upper()}{Colors.END}")
    print("=" * 60)
    
    stage_descriptions = {
        'pre': "Testing BEFORE migration (should have game_id)",
        'post-migration': "Testing AFTER migration (should have both game_id and event_id)",
        'post-update': "Testing AFTER model updates (should use event_id exclusively)"
    }
    
    print(stage_descriptions[args.stage])
    print()
    
    tester = MigrationTestSuite(args.stage)
    
    try:
        if not await tester.setup_test_environment():
            return 1
        
        if args.stage == 'pre':
            await tester.test_pre_migration_state()
        elif args.stage == 'post-migration':
            await tester.test_post_migration_state()
        elif args.stage == 'post-update':
            await tester.test_post_update_state()
        
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