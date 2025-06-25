#!/usr/bin/env python3
"""
Tournament Bot - Comprehensive Manual Test Suite
Interactive testing script for verifying all foundation components
"""

import asyncio
import sys
import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from bot.config import Config
from bot.database.database import Database
from bot.database.models import Player, Game, Challenge, ChallengeStatus, MatchResult
from bot.utils.elo import EloCalculator

class Colors:
    """Terminal colors for better output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class ManualTestSuite:
    def __init__(self):
        self.db: Optional[Database] = None
        self.test_data = {}
        self.config = {
            'use_test_db': True,
            'cleanup_after_test': True,
            'verbose_output': True,
            'simulate_discord_data': True
        }
        
    def print_header(self, title: str):
        """Print a formatted header"""
        print(f"\n{Colors.HEADER}{'='*60}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{title.center(60)}{Colors.END}")
        print(f"{Colors.HEADER}{'='*60}{Colors.END}")
        
    def print_success(self, message: str):
        """Print success message"""
        print(f"{Colors.GREEN}✅ {message}{Colors.END}")
        
    def print_error(self, message: str):
        """Print error message"""
        print(f"{Colors.RED}❌ {message}{Colors.END}")
        
    def print_info(self, message: str):
        """Print info message"""
        print(f"{Colors.BLUE}ℹ️  {message}{Colors.END}")
        
    def print_warning(self, message: str):
        """Print warning message"""
        print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")
        
    async def setup_test_environment(self):
        """Setup test environment"""
        self.print_header("Setting Up Test Environment")
        
        try:
            # Configure test database
            if self.config['use_test_db']:
                Config.DATABASE_URL = 'sqlite+aiosqlite:///manual_test_tournament.db'
                self.print_info("Using test database: manual_test_tournament.db")
            
            # Initialize database
            self.db = Database()
            await self.db.initialize()
            self.print_success("Database initialized successfully")
            
            # Verify games were loaded
            games = await self.db.get_all_games()
            self.print_success(f"Loaded {len(games)} default games")
            
            return True
            
        except Exception as e:
            self.print_error(f"Failed to setup test environment: {e}")
            return False
    
    async def test_configuration(self):
        """Test configuration system"""
        self.print_header("Testing Configuration System")
        
        try:
            # Test config attributes
            required_attrs = [
                'STARTING_ELO', 'K_FACTOR_STANDARD', 'K_FACTOR_PROVISIONAL',
                'PROVISIONAL_MATCH_COUNT', 'CHALLENGE_EXPIRY_HOURS'
            ]
            
            for attr in required_attrs:
                value = getattr(Config, attr, None)
                if value is not None:
                    self.print_success(f"{attr}: {value}")
                else:
                    self.print_error(f"Missing config attribute: {attr}")
                    
            # Test validation (should not raise with test values)
            Config.DISCORD_TOKEN = "test_token"
            Config.DISCORD_GUILD_ID = 12345
            Config.OWNER_DISCORD_ID = 67890
            
            try:
                Config.validate()
                self.print_success("Configuration validation passed")
            except ValueError as e:
                self.print_error(f"Configuration validation failed: {e}")
                
            return True
            
        except Exception as e:
            self.print_error(f"Configuration test failed: {e}")
            return False
    
    async def test_elo_calculations(self):
        """Test Elo calculation system"""
        self.print_header("Testing Elo Calculation System")
        
        try:
            test_cases = [
                {
                    'name': 'Equal ratings, Player 1 wins',
                    'p1_rating': 1000, 'p1_matches': 0,
                    'p2_rating': 1000, 'p2_matches': 10,
                    'p1_wins': True
                },
                {
                    'name': 'Higher rated player wins',
                    'p1_rating': 1200, 'p1_matches': 15,
                    'p2_rating': 1000, 'p2_matches': 8,
                    'p1_wins': True
                },
                {
                    'name': 'Lower rated player upsets',
                    'p1_rating': 900, 'p1_matches': 3,
                    'p2_rating': 1300, 'p2_matches': 20,
                    'p1_wins': True
                },
                {
                    'name': 'Draw between different ratings',
                    'p1_rating': 1100, 'p1_matches': 12,
                    'p2_rating': 1050, 'p2_matches': 18,
                    'p1_wins': False, 'is_draw': True
                }
            ]
            
            for case in test_cases:
                self.print_info(f"Testing: {case['name']}")
                
                # Calculate expected scores
                expected_p1 = EloCalculator.calculate_expected_score(
                    case['p1_rating'], case['p2_rating']
                )
                
                # Get K-factors
                k1 = EloCalculator.get_k_factor(case['p1_matches'])
                k2 = EloCalculator.get_k_factor(case['p2_matches'])
                
                # Calculate Elo changes
                is_draw = case.get('is_draw', False)
                p1_change, p2_change = EloCalculator.calculate_match_elo_changes(
                    case['p1_rating'], case['p1_matches'],
                    case['p2_rating'], case['p2_matches'],
                    case['p1_wins'], is_draw
                )
                
                # Display results
                print(f"  P1: {case['p1_rating']} -> {case['p1_rating'] + p1_change} ({EloCalculator.format_elo_change(p1_change)})")
                print(f"  P2: {case['p2_rating']} -> {case['p2_rating'] + p2_change} ({EloCalculator.format_elo_change(p2_change)})")
                print(f"  Expected P1 score: {expected_p1:.3f} | K-factors: {k1}, {k2}")
                
                # Validate results
                if is_draw:
                    # Both players should have small changes
                    if abs(p1_change) > 25 or abs(p2_change) > 25:
                        self.print_warning("Large Elo changes for a draw")
                elif case['p1_wins']:
                    if p1_change <= 0 or p2_change >= 0:
                        self.print_error("Invalid Elo changes for P1 win")
                    else:
                        self.print_success("Elo changes correct for P1 win")
                else:
                    if p1_change >= 0 or p2_change <= 0:
                        self.print_error("Invalid Elo changes for P2 win")
                    else:
                        self.print_success("Elo changes correct for P2 win")
                
                print()
            
            # Test win probability calculation
            self.print_info("Testing win probability calculation:")
            prob_tests = [(1200, 1000), (1000, 1200), (1000, 1000), (1500, 1000)]
            for rating1, rating2 in prob_tests:
                prob = EloCalculator.calculate_win_probability(rating1, rating2)
                print(f"  {rating1} vs {rating2}: {prob:.1f}% win chance")
            
            self.print_success("Elo calculation tests completed")
            return True
            
        except Exception as e:
            self.print_error(f"Elo calculation test failed: {e}")
            return False
    
    async def test_database_operations(self):
        """Test database CRUD operations"""
        self.print_header("Testing Database Operations")
        
        try:
            # Test game operations
            self.print_info("Testing game operations...")
            games = await self.db.get_all_games()
            if len(games) > 0:
                self.print_success(f"Retrieved {len(games)} games")
                
                # Test specific game lookup
                test_game = await self.db.get_game_by_name("Dragon Ball FighterZ")
                if test_game:
                    self.print_success(f"Found game: {test_game.name}")
                else:
                    self.print_error("Could not find Dragon Ball FighterZ")
            else:
                self.print_error("No games found in database")
            
            # Test player creation
            self.print_info("Testing player operations...")
            test_players = [
                {'discord_id': 100001, 'username': 'TestPlayer1', 'display_name': 'Test Player 1'},
                {'discord_id': 100002, 'username': 'TestPlayer2', 'display_name': 'Test Player 2'},
                {'discord_id': 100003, 'username': 'TestPlayer3', 'display_name': 'Test Player 3'},
            ]
            
            created_players = []
            for player_data in test_players:
                # Check if player already exists
                existing = await self.db.get_player_by_discord_id(player_data['discord_id'])
                if existing:
                    self.print_info(f"Player {player_data['username']} already exists")
                    created_players.append(existing)
                else:
                    player = await self.db.create_player(**player_data)
                    created_players.append(player)
                    self.print_success(f"Created player: {player.username} (ID: {player.id})")
            
            self.test_data['players'] = created_players
            self.test_data['games'] = games
            
            # Test event operations
            self.print_info("Testing event operations...")
            events = await self.db.get_all_events()
            if len(events) > 0:
                self.print_success(f"Retrieved {len(events)} events")
                
                # Test specific event lookup
                test_event = None
                for event in events:
                    if event.scoring_type == "1v1":
                        test_event = event
                        break
                
                if test_event:
                    self.print_success(f"Found 1v1 event: {test_event.name}")
                else:
                    self.print_warning("No 1v1 events found")
            else:
                self.print_error("No events found in database")
            
            self.test_data['events'] = events
            
            # Test leaderboard
            leaderboard = await self.db.get_leaderboard(5)
            self.print_success(f"Retrieved leaderboard with {len(leaderboard)} players")
            
            return True
            
        except Exception as e:
            self.print_error(f"Database operations test failed: {e}")
            return False
    
    async def test_challenge_system(self):
        """Test challenge creation and management"""
        self.print_header("Testing Challenge System")
        
        try:
            if 'players' not in self.test_data:
                self.print_error("Missing test data for challenge tests")
                return False
            
            players = self.test_data['players']
            
            if len(players) < 2:
                self.print_error("Insufficient test data for challenge tests")
                return False
            
            # Get events for testing different challenge types
            events = await self.db.get_all_events()
            if not events:
                self.print_error("No events found for challenge testing")
                return False
            
            # Find events by scoring type for comprehensive testing
            test_events = {}
            for event in events:
                if event.scoring_type not in test_events and event.allow_challenges:
                    test_events[event.scoring_type] = event
            
            if not test_events:
                self.print_error("No challengeable events found")
                return False
            
            self.print_info(f"Found {len(test_events)} challenge types to test: {', '.join(test_events.keys())}")
            
            # Test each available challenge type
            challenger = players[0]
            challenged = players[1]
            created_challenges = []
            
            for scoring_type, event in test_events.items():
                self.print_info(f"Creating {scoring_type} challenge: {challenger.username} vs {challenged.username} in {event.name}")
                
                challenge = await self.db.create_challenge(
                    challenger_id=challenger.id,
                    challenged_id=challenged.id,
                    event_id=event.id,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                    ticket_wager=0
                )
                
                created_challenges.append(challenge)
                self.print_success(f"Created {scoring_type} challenge ID: {challenge.id}")
            
            # Store the first challenge for later testing
            self.test_data['challenge'] = created_challenges[0]
            self.test_data['all_challenges'] = created_challenges
            
            # Test challenge retrieval and relationships for each challenge type
            for i, challenge in enumerate(created_challenges):
                retrieved_challenge = await self.db.get_challenge_by_id(challenge.id)
                if retrieved_challenge:
                    scoring_type = retrieved_challenge.event.scoring_type
                    self.print_success(f"{scoring_type} challenge retrieved successfully")
                    self.print_info(f"  Challenge: {retrieved_challenge.challenger.username} vs {retrieved_challenge.challenged.username}")
                    self.print_info(f"  Event: {retrieved_challenge.event.name} ({scoring_type})")
                else:
                    self.print_error(f"Failed to retrieve challenge {challenge.id}")
            
            # Test challenge status update on first challenge
            first_challenge = created_challenges[0]
            await self.db.update_challenge_status(
                first_challenge.id, 
                ChallengeStatus.ACCEPTED,
                accepted_at=datetime.now(timezone.utc)
            )
            self.print_success("Challenge status updated to ACCEPTED")
            
            # Test active challenges query
            active_challenges = await self.db.get_active_challenges_for_player(challenger.id)
            self.print_success(f"Found {len(active_challenges)} active challenges for {challenger.username}")
            
            return True
            
        except Exception as e:
            self.print_error(f"Challenge system test failed: {e}")
            return False
    
    async def test_match_simulation(self):
        """Simulate a complete match with Elo updates"""
        self.print_header("Testing Match Simulation")
        
        try:
            if 'challenge' not in self.test_data:
                self.print_error("No challenge available for match simulation")
                return False
            
            challenge = self.test_data['challenge']
            challenger = self.test_data['players'][0]
            challenged = self.test_data['players'][1]
            
            self.print_info(f"Simulating match: {challenger.username} vs {challenged.username}")
            self.print_info(f"Before match - {challenger.username}: {challenger.elo_rating} Elo, {challenged.username}: {challenged.elo_rating} Elo")
            
            # Calculate Elo changes (challenger wins)
            challenger_change, challenged_change = EloCalculator.calculate_match_elo_changes(
                challenger.elo_rating, challenger.matches_played,
                challenged.elo_rating, challenged.matches_played,
                True  # challenger wins
            )
            
            self.print_info(f"Calculated Elo changes: {challenger.username}: {EloCalculator.format_elo_change(challenger_change)}, {challenged.username}: {EloCalculator.format_elo_change(challenged_change)}")
            
            # Record Elo changes
            await self.db.record_elo_change(
                challenger.id, challenger.elo_rating, challenger.elo_rating + challenger_change,
                challenge.id, challenged.id, MatchResult.WIN,
                EloCalculator.get_k_factor(challenger.matches_played)
            )
            
            await self.db.record_elo_change(
                challenged.id, challenged.elo_rating, challenged.elo_rating + challenged_change,
                challenge.id, challenger.id, MatchResult.LOSS,
                EloCalculator.get_k_factor(challenged.matches_played)
            )
            
            # Update challenge with results
            await self.db.update_challenge_status(
                challenge.id,
                ChallengeStatus.COMPLETED,
                completed_at=datetime.now(timezone.utc),
                challenger_result=MatchResult.WIN,
                challenged_result=MatchResult.LOSS,
                challenger_elo_change=challenger_change,
                challenged_elo_change=challenged_change
            )
            
            self.print_success("Match completed and recorded")
            
            # Verify final state
            final_challenge = await self.db.get_challenge_by_id(challenge.id)
            if final_challenge and final_challenge.status == ChallengeStatus.COMPLETED:
                self.print_success("Challenge marked as completed")
                self.print_info(f"Final Elo changes recorded: {final_challenge.challenger_elo_change}, {final_challenge.challenged_elo_change}")
            
            return True
            
        except Exception as e:
            self.print_error(f"Match simulation test failed: {e}")
            return False
    
    async def test_player_stats(self):
        """Test comprehensive player statistics"""
        self.print_header("Testing Player Statistics")
        
        try:
            if 'players' not in self.test_data:
                self.print_error("No players available for stats test")
                return False
            
            for player in self.test_data['players'][:2]:  # Test first 2 players
                stats = await self.db.get_player_stats(player.id)
                
                if stats:
                    player_data = stats['player']
                    recent_matches = stats['recent_matches']
                    elo_history = stats['elo_history']
                    
                    self.print_success(f"Retrieved stats for {player_data.username}")
                    self.print_info(f"  Elo: {player_data.elo_rating}")
                    self.print_info(f"  Matches: {player_data.matches_played}")
                    self.print_info(f"  Win Rate: {player_data.win_rate:.1f}%")
                    self.print_info(f"  Recent matches: {len(recent_matches)}")
                    self.print_info(f"  Elo history entries: {len(elo_history)}")
                    
                    # Show status information
                    status = "Provisional" if player_data.is_provisional else "Ranked"
                    self.print_info(f"  Status: {status}")
                    
                else:
                    self.print_error(f"Failed to retrieve stats for {player.username}")
            
            return True
            
        except Exception as e:
            self.print_error(f"Player statistics test failed: {e}")
            return False
    
    async def test_data_integrity(self):
        """Test data integrity and relationships"""
        self.print_header("Testing Data Integrity")
        
        try:
            # Test foreign key relationships
            self.print_info("Testing foreign key relationships...")
            
            if 'challenge' in self.test_data:
                challenge = await self.db.get_challenge_by_id(self.test_data['challenge'].id)
                if challenge:
                    # Verify relationships are properly loaded
                    if challenge.challenger and challenge.challenged and challenge.event:
                        self.print_success("Challenge relationships loaded correctly")
                        self.print_info(f"  Challenger: {challenge.challenger.username}")
                        self.print_info(f"  Challenged: {challenge.challenged.username}")
                        self.print_info(f"  Event: {challenge.event.name} ({challenge.event.scoring_type})")
                    else:
                        self.print_error("Challenge relationships not loaded properly")
                else:
                    self.print_error("Challenge not found")
            
            # Test data consistency
            self.print_info("Testing data consistency...")
            
            players = await self.db.get_leaderboard(100)  # Get all players
            for player in players:
                # Check that calculated fields make sense
                total_matches = player.wins + player.losses + player.draws
                if total_matches != player.matches_played:
                    self.print_error(f"Match count mismatch for {player.username}: {total_matches} != {player.matches_played}")
                else:
                    self.print_success(f"Match counts consistent for {player.username}")
                
                # Check win rate calculation
                if player.matches_played > 0:
                    expected_win_rate = (player.wins / player.matches_played) * 100
                    if abs(expected_win_rate - player.win_rate) > 0.1:
                        self.print_error(f"Win rate calculation error for {player.username}")
                    else:
                        self.print_success(f"Win rate calculation correct for {player.username}")
            
            return True
            
        except Exception as e:
            self.print_error(f"Data integrity test failed: {e}")
            return False
    
    async def cleanup_test_data(self):
        """Clean up test data"""
        if self.config['cleanup_after_test']:
            self.print_header("Cleaning Up Test Data")
            
            try:
                if self.db:
                    await self.db.close()
                    self.print_success("Database connection closed")
                
                # Remove test database file
                if self.config['use_test_db']:
                    test_db_file = 'manual_test_tournament.db'
                    if os.path.exists(test_db_file):
                        os.remove(test_db_file)
                        self.print_success(f"Removed test database: {test_db_file}")
                
            except Exception as e:
                self.print_error(f"Cleanup failed: {e}")
    
    def show_configuration_menu(self):
        """Show and handle configuration menu"""
        while True:
            self.print_header("Test Configuration")
            print(f"1. Use test database: {Colors.GREEN if self.config['use_test_db'] else Colors.RED}{self.config['use_test_db']}{Colors.END}")
            print(f"2. Cleanup after test: {Colors.GREEN if self.config['cleanup_after_test'] else Colors.RED}{self.config['cleanup_after_test']}{Colors.END}")
            print(f"3. Verbose output: {Colors.GREEN if self.config['verbose_output'] else Colors.RED}{self.config['verbose_output']}{Colors.END}")
            print(f"4. Simulate Discord data: {Colors.GREEN if self.config['simulate_discord_data'] else Colors.RED}{self.config['simulate_discord_data']}{Colors.END}")
            print(f"5. {Colors.CYAN}Start Tests{Colors.END}")
            print(f"6. {Colors.RED}Exit{Colors.END}")
            
            choice = input(f"\n{Colors.YELLOW}Select option (1-6): {Colors.END}").strip()
            
            if choice == '1':
                self.config['use_test_db'] = not self.config['use_test_db']
            elif choice == '2':
                self.config['cleanup_after_test'] = not self.config['cleanup_after_test']
            elif choice == '3':
                self.config['verbose_output'] = not self.config['verbose_output']
            elif choice == '4':
                self.config['simulate_discord_data'] = not self.config['simulate_discord_data']
            elif choice == '5':
                return True
            elif choice == '6':
                return False
            else:
                print(f"{Colors.RED}Invalid option. Please select 1-6.{Colors.END}")
    
    async def show_main_menu(self):
        """Show main menu and handle selection"""
        test_methods = [
            ('Configuration System', self.test_configuration),
            ('Elo Calculations', self.test_elo_calculations),
            ('Database Operations', self.test_database_operations),
            ('Challenge System', self.test_challenge_system),
            ('Match Simulation', self.test_match_simulation),
            ('Player Statistics', self.test_player_stats),
            ('Data Integrity', self.test_data_integrity),
        ]
        
        while True:
            self.print_header("Tournament Bot Manual Test Suite")
            print(f"{Colors.CYAN}Available Tests:{Colors.END}")
            
            for i, (name, _) in enumerate(test_methods, 1):
                print(f"{i}. {name}")
            
            print(f"{len(test_methods) + 1}. {Colors.GREEN}Run All Tests{Colors.END}")
            print(f"{len(test_methods) + 2}. {Colors.BLUE}Configure Tests{Colors.END}")
            print(f"{len(test_methods) + 3}. {Colors.RED}Exit{Colors.END}")
            
            choice = input(f"\n{Colors.YELLOW}Select option: {Colors.END}").strip()
            
            try:
                choice_num = int(choice)
                
                if 1 <= choice_num <= len(test_methods):
                    # Run single test
                    name, method = test_methods[choice_num - 1]
                    await self.run_single_test(name, method)
                elif choice_num == len(test_methods) + 1:
                    # Run all tests
                    await self.run_all_tests(test_methods)
                elif choice_num == len(test_methods) + 2:
                    # Configure tests
                    if not self.show_configuration_menu():
                        continue
                elif choice_num == len(test_methods) + 3:
                    # Exit
                    break
                else:
                    print(f"{Colors.RED}Invalid option. Please try again.{Colors.END}")
                    
            except ValueError:
                print(f"{Colors.RED}Please enter a valid number.{Colors.END}")
            
            input(f"\n{Colors.CYAN}Press Enter to continue...{Colors.END}")
    
    async def run_single_test(self, name: str, method):
        """Run a single test method"""
        self.print_header(f"Running Test: {name}")
        
        if not await self.setup_test_environment():
            return
        
        try:
            success = await method()
            if success:
                self.print_success(f"Test '{name}' completed successfully")
            else:
                self.print_error(f"Test '{name}' failed")
        except Exception as e:
            self.print_error(f"Test '{name}' crashed: {e}")
        finally:
            await self.cleanup_test_data()
    
    async def run_all_tests(self, test_methods):
        """Run all tests in sequence"""
        self.print_header("Running All Tests")
        
        if not await self.setup_test_environment():
            return
        
        results = []
        
        try:
            for name, method in test_methods:
                self.print_info(f"Running: {name}")
                try:
                    success = await method()
                    results.append((name, success))
                    if success:
                        self.print_success(f"✅ {name}")
                    else:
                        self.print_error(f"❌ {name}")
                except Exception as e:
                    self.print_error(f"💥 {name}: {e}")
                    results.append((name, False))
                
                print()  # Add spacing between tests
        
        finally:
            await self.cleanup_test_data()
        
        # Print summary
        self.print_header("Test Summary")
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        for name, success in results:
            status = f"{Colors.GREEN}✅ PASS{Colors.END}" if success else f"{Colors.RED}❌ FAIL{Colors.END}"
            print(f"{status} - {name}")
        
        print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed ({(passed/total)*100:.1f}%){Colors.END}")
        
        if passed == total:
            self.print_success("🎉 All tests passed! Foundation is ready for Phase 2.")
        else:
            self.print_warning(f"⚠️ {total - passed} test(s) failed. Please review and fix issues.")

async def main():
    """Main entry point"""
    print(f"{Colors.HEADER}{Colors.BOLD}")
    print("  ████████╗ ██████╗ ██╗   ██╗██████╗ ███╗   ██╗ █████╗ ███╗   ███╗███████╗███╗   ██╗████████╗")
    print("  ╚══██╔══╝██╔═══██╗██║   ██║██╔══██╗████╗  ██║██╔══██╗████╗ ████║██╔════╝████╗  ██║╚══██╔══╝")
    print("     ██║   ██║   ██║██║   ██║██████╔╝██╔██╗ ██║███████║██╔████╔██║█████╗  ██╔██╗ ██║   ██║   ")
    print("     ██║   ██║   ██║██║   ██║██╔══██╗██║╚██╗██║██╔══██║██║╚██╔╝██║██╔══╝  ██║╚██╗██║   ██║   ")
    print("     ██║   ╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║██║  ██║██║ ╚═╝ ██║███████╗██║ ╚████║   ██║   ")
    print("     ╚═╝    ╚═════╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚═╝  ╚═══╝   ╚═╝   ")
    print(f"{Colors.END}")
    print(f"{Colors.CYAN}                           Manual Test Suite - Phase 1 Foundation{Colors.END}")
    print()
    
    test_suite = ManualTestSuite()
    await test_suite.show_main_menu()
    
    print(f"\n{Colors.CYAN}Thank you for testing the Tournament Bot foundation!{Colors.END}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test suite interrupted by user.{Colors.END}")
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.END}")
        sys.exit(1)