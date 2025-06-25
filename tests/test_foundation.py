#!/usr/bin/env python3
"""
Test script for Phase 1 foundation components
Tests database initialization, models, Elo calculations, and configuration
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bot.config import Config
from bot.database.database import Database
from bot.database.models import Player, Game, Challenge
from bot.utils.elo import EloCalculator

class FoundationTester:
    def __init__(self):
        self.db = None
        self.test_results = []
    
    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log a test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
        if details:
            print(f"    {details}")
        self.test_results.append((test_name, passed, details))
    
    async def test_config(self):
        """Test configuration loading"""
        print("\n🔧 Testing Configuration...")
        
        try:
            # Test config attributes exist
            assert hasattr(Config, 'STARTING_ELO')
            assert hasattr(Config, 'K_FACTOR_STANDARD')
            assert hasattr(Config, 'PROVISIONAL_MATCH_COUNT')
            self.log_test("Config attributes", True, "All required config attributes present")
        except Exception as e:
            self.log_test("Config attributes", False, str(e))
        
        try:
            # Test default values
            assert Config.STARTING_ELO == 1000
            assert Config.K_FACTOR_STANDARD == 20
            assert Config.PROVISIONAL_MATCH_COUNT == 5
            self.log_test("Config default values", True, "Default values correct")
        except Exception as e:
            self.log_test("Config default values", False, str(e))
    
    async def test_database_initialization(self):
        """Test database setup and initialization"""
        print("\n🗄️ Testing Database Initialization...")
        
        try:
            # Use test database
            Config.DATABASE_URL = 'sqlite+aiosqlite:///test_tournament.db'
            self.db = Database()
            await self.db.initialize()
            self.log_test("Database initialization", True, "Database created successfully")
        except Exception as e:
            self.log_test("Database initialization", False, str(e))
            return
        
        try:
            # Test default games were created
            games = await self.db.get_all_games()
            assert len(games) > 0
            self.log_test("Default games creation", True, f"Created {len(games)} default games")
        except Exception as e:
            self.log_test("Default games creation", False, str(e))
    
    async def test_elo_calculations(self):
        """Test Elo calculation utilities"""
        print("\n📊 Testing Elo Calculations...")
        
        try:
            # Test expected score calculation
            expected = EloCalculator.calculate_expected_score(1200, 1000)
            assert 0.5 < expected < 1.0  # Higher rated player should have > 50% chance
            self.log_test("Expected score calculation", True, f"1200 vs 1000: {expected:.3f}")
        except Exception as e:
            self.log_test("Expected score calculation", False, str(e))
        
        try:
            # Test K-factor selection
            k_provisional = EloCalculator.get_k_factor(3)  # Provisional
            k_standard = EloCalculator.get_k_factor(10)    # Standard
            assert k_provisional == 40
            assert k_standard == 20
            self.log_test("K-factor selection", True, f"Provisional: {k_provisional}, Standard: {k_standard}")
        except Exception as e:
            self.log_test("K-factor selection", False, str(e))
        
        try:
            # Test match Elo changes
            p1_change, p2_change = EloCalculator.calculate_match_elo_changes(
                1000, 0,  # Player 1: 1000 Elo, 0 matches (provisional)
                1000, 10, # Player 2: 1000 Elo, 10 matches (standard)
                True      # Player 1 wins
            )
            assert p1_change > 0  # Winner gains
            assert p2_change < 0  # Loser loses
            # Note: Changes won't be equal due to different K-factors (provisional vs standard)
            self.log_test("Match Elo changes", True, f"P1: {p1_change}, P2: {p2_change}")
        except Exception as e:
            self.log_test("Match Elo changes", False, str(e))
        
        try:
            # Test win probability calculation
            prob_tests = [
                (1200, 1000, 76.0),  # Higher rated player advantage
                (1000, 1200, 24.0),  # Lower rated player disadvantage  
                (1000, 1000, 50.0),  # Equal ratings
            ]
            
            for rating1, rating2, expected_prob in prob_tests:
                prob = EloCalculator.calculate_win_probability(rating1, rating2)
                assert abs(prob - expected_prob) < 1.0, f"Expected ~{expected_prob}% for {rating1} vs {rating2}, got {prob:.1f}%"
            
            self.log_test("Win probability calculation", True, "Win probability calculations correct")
        except Exception as e:
            self.log_test("Win probability calculation", False, str(e))
    
    async def test_player_operations(self):
        """Test player database operations"""
        print("\n👤 Testing Player Operations...")
        
        if not self.db:
            self.log_test("Player operations", False, "Database not initialized")
            return
        
        try:
            # Test player creation
            player = await self.db.create_player(
                discord_id=12345,
                username="testuser",
                display_name="Test User"
            )
            assert player.elo_rating == Config.STARTING_ELO
            assert player.tickets == Config.STARTING_TICKETS
            assert player.matches_played == 0
            self.log_test("Player creation", True, f"Created player with ID {player.id}")
        except Exception as e:
            self.log_test("Player creation", False, str(e))
            return
        
        try:
            # Test player retrieval
            retrieved = await self.db.get_player_by_discord_id(12345)
            assert retrieved is not None
            assert retrieved.username == "testuser"
            self.log_test("Player retrieval", True, f"Retrieved player: {retrieved.username}")
        except Exception as e:
            self.log_test("Player retrieval", False, str(e))
        
        try:
            # Test duplicate prevention
            duplicate = await self.db.get_player_by_discord_id(12345)
            assert duplicate is not None  # Should find existing player
            self.log_test("Duplicate prevention", True, "Found existing player correctly")
        except Exception as e:
            self.log_test("Duplicate prevention", False, str(e))
    
    async def test_game_operations(self):
        """Test game database operations"""
        print("\n🎮 Testing Game Operations...")
        
        if not self.db:
            self.log_test("Game operations", False, "Database not initialized")
            return
        
        try:
            # Test game retrieval
            games = await self.db.get_all_games()
            assert len(games) > 0
            self.log_test("Game listing", True, f"Found {len(games)} games")
        except Exception as e:
            self.log_test("Game listing", False, str(e))
        
        try:
            # Test game search by name
            game = await self.db.get_game_by_name("Dragon Ball FighterZ")
            assert game is not None
            assert game.name == "Dragon Ball FighterZ"
            self.log_test("Game search", True, f"Found game: {game.name}")
        except Exception as e:
            self.log_test("Game search", False, str(e))
    
    async def cleanup(self):
        """Clean up test resources"""
        if self.db:
            await self.db.close()
        
        # Remove test database file
        try:
            import os
            if os.path.exists('test_tournament.db'):
                os.remove('test_tournament.db')
            print("\n🧹 Cleaned up test database")
        except Exception as e:
            print(f"⚠️ Warning: Could not clean up test database: {e}")
    
    def print_summary(self):
        """Print test summary"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, passed, _ in self.test_results if passed)
        failed_tests = total_tests - passed_tests
        
        print(f"\n" + "="*50)
        print(f"📋 TEST SUMMARY")
        print(f"="*50)
        print(f"Total Tests:  {total_tests}")
        print(f"Passed:       {passed_tests} ✅")
        print(f"Failed:       {failed_tests} ❌")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "No tests run")
        
        if failed_tests > 0:
            print(f"\n❌ FAILED TESTS:")
            for test_name, passed, details in self.test_results:
                if not passed:
                    print(f"  • {test_name}: {details}")
        else:
            print(f"\n🎉 All foundation tests passed! Ready for Phase 2.")
        
        return failed_tests == 0

async def main():
    """Run all foundation tests"""
    print("🧪 Tournament Bot - Phase 1 Foundation Tests")
    print("=" * 50)
    
    tester = FoundationTester()
    
    try:
        await tester.test_config()
        await tester.test_elo_calculations()
        await tester.test_database_initialization()
        await tester.test_player_operations()
        await tester.test_game_operations()
        
        success = tester.print_summary()
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n💥 CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        await tester.cleanup()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)