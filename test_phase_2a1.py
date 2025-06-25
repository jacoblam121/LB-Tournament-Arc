#!/usr/bin/env python3
"""
Phase 2A.1 Test Suite - Database Schema Validation
Tests Cluster and Discipline models, CSV import, and database operations
"""

import asyncio
import sys
import os
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from bot.config import Config
from bot.database.database import Database
from bot.database.models import Cluster, Event

class Colors:
    """Terminal colors for better output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

class Phase2A1TestSuite:
    def __init__(self):
        self.db = None
        self.test_results = []
        
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
        
    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log a test result"""
        status = "PASS" if passed else "FAIL"
        if passed:
            self.print_success(f"{test_name}")
        else:
            self.print_error(f"{test_name}")
        if details:
            print(f"    {details}")
        self.test_results.append((test_name, passed, details))
    
    async def setup_test_environment(self):
        """Setup test environment with fresh database"""
        self.print_header("Setting Up Test Environment")
        
        try:
            # Use test database
            Config.DATABASE_URL = 'sqlite+aiosqlite:///test_phase_2a1.db'
            self.print_info("Using test database: test_phase_2a1.db")
            
            # Initialize database
            self.db = Database()
            await self.db.initialize()
            self.print_success("Database initialized successfully")
            
            return True
            
        except Exception as e:
            self.print_error(f"Failed to setup test environment: {e}")
            return False
    
    async def test_schema_creation(self):
        """Test that new schema elements are created correctly"""
        self.print_header("Testing Schema Creation")
        
        try:
            # Test clusters table exists and has data
            clusters = await self.db.get_all_clusters()
            if len(clusters) > 0:
                self.log_test("Clusters table created and populated", True, f"Found {len(clusters)} clusters")
            else:
                self.log_test("Clusters table created and populated", False, "No clusters found")
                return False
            
            # Test events table exists and has data
            events = await self.db.get_all_events()
            if len(events) > 0:
                self.log_test("Events table created and populated", True, f"Found {len(events)} events")
            else:
                self.log_test("Events table created and populated", False, "No events found")
                return False
            
            # Test cluster-event relationships
            first_cluster = clusters[0]
            cluster_with_events = await self.db.get_cluster_by_id(first_cluster.id)
            if cluster_with_events and cluster_with_events.events:
                self.log_test("Cluster-Event relationships work", True, 
                            f"Cluster '{first_cluster.name}' has {len(cluster_with_events.events)} events")
            else:
                self.log_test("Cluster-Event relationships work", False, "No events found for cluster")
                return False
            
            return True
            
        except Exception as e:
            self.log_test("Schema creation test", False, str(e))
            return False
    
    async def test_csv_import_integrity(self):
        """Test CSV import data integrity"""
        self.print_header("Testing CSV Import Integrity")
        
        try:
            # Test expected number of clusters (should be 20)
            clusters = await self.db.get_all_clusters()
            expected_clusters = 20
            if len(clusters) == expected_clusters:
                self.log_test("Correct number of clusters imported", True, f"{len(clusters)}/{expected_clusters}")
            else:
                self.log_test("Correct number of clusters imported", False, f"{len(clusters)}/{expected_clusters}")
            
            # Test expected number of events (should be 65+)
            events = await self.db.get_all_events()
            min_expected_events = 60  # At least 60 events expected
            if len(events) >= min_expected_events:
                self.log_test("Sufficient events imported", True, f"{len(events)} events (expected ≥{min_expected_events})")
            else:
                self.log_test("Sufficient events imported", False, f"{len(events)} events (expected ≥{min_expected_events})")
            
            # Test specific clusters exist
            test_clusters = ["Chess", "Pokemon", "FPS", "Minecraft"]
            for cluster_name in test_clusters:
                cluster = await self.db.get_cluster_by_name(cluster_name)
                if cluster:
                    self.log_test(f"Cluster '{cluster_name}' exists", True, f"ID: {cluster.id}, Number: {cluster.number}")
                else:
                    self.log_test(f"Cluster '{cluster_name}' exists", False, "Not found")
            
            # Test specific events exist
            test_events = ["Bullet", "Showdown (OU)", "Operations Siege", "Blitz Duels"]
            for event_name in test_events:
                event = await self.db.get_event_by_name(event_name)
                if event:
                    self.log_test(f"Event '{event_name}' exists", True, 
                                f"Cluster: {event.cluster.name}, Type: {event.scoring_type}")
                else:
                    self.log_test(f"Event '{event_name}' exists", False, "Not found")
            
            return True
            
        except Exception as e:
            self.log_test("CSV import integrity test", False, str(e))
            return False
    
    async def test_scoring_type_distribution(self):
        """Test scoring type distribution is reasonable"""
        self.print_header("Testing Scoring Type Distribution")
        
        try:
            events = await self.db.get_all_events()
            scoring_types = {}
            
            for event in events:
                scoring_type = event.scoring_type
                scoring_types[scoring_type] = scoring_types.get(scoring_type, 0) + 1
            
            self.print_info("Scoring type distribution:")
            for scoring_type, count in scoring_types.items():
                print(f"    {scoring_type}: {count} events")
            
            # Test that we have multiple scoring types
            expected_types = ['1v1', 'FFA', 'Team', 'Leaderboard']
            found_types = set(scoring_types.keys())
            
            for expected_type in expected_types:
                if expected_type in found_types:
                    self.log_test(f"Scoring type '{expected_type}' present", True, f"{scoring_types[expected_type]} events")
                else:
                    self.log_test(f"Scoring type '{expected_type}' present", False, "Missing")
            
            # Test that 1v1 is the most common type (should be)
            most_common = max(scoring_types, key=scoring_types.get)
            if most_common == '1v1':
                self.log_test("1v1 is most common scoring type", True, f"{scoring_types[most_common]} events")
            else:
                self.log_test("1v1 is most common scoring type", False, f"Most common: {most_common}")
            
            return True
            
        except Exception as e:
            self.log_test("Scoring type distribution test", False, str(e))
            return False
    
    async def test_database_operations(self):
        """Test CRUD operations for clusters and disciplines"""
        self.print_header("Testing Database Operations")
        
        try:
            # Test cluster operations
            all_clusters = await self.db.get_all_clusters()
            if all_clusters:
                self.log_test("Get all clusters", True, f"Retrieved {len(all_clusters)} clusters")
            else:
                self.log_test("Get all clusters", False, "No clusters retrieved")
                return False
            
            # Test get cluster by ID
            first_cluster = all_clusters[0]
            cluster_by_id = await self.db.get_cluster_by_id(first_cluster.id)
            if cluster_by_id and cluster_by_id.id == first_cluster.id:
                self.log_test("Get cluster by ID", True, f"Retrieved cluster: {cluster_by_id.name}")
            else:
                self.log_test("Get cluster by ID", False, "Failed to retrieve cluster")
            
            # Test get cluster by name
            cluster_by_name = await self.db.get_cluster_by_name(first_cluster.name)
            if cluster_by_name and cluster_by_name.name == first_cluster.name:
                self.log_test("Get cluster by name", True, f"Retrieved cluster: {cluster_by_name.name}")
            else:
                self.log_test("Get cluster by name", False, "Failed to retrieve cluster")
            
            # Test event operations
            all_events = await self.db.get_all_events()
            if all_events:
                self.log_test("Get all events", True, f"Retrieved {len(all_events)} events")
            else:
                self.log_test("Get all events", False, "No events retrieved")
                return False
            
            # Test get events by cluster
            cluster_events = await self.db.get_all_events(cluster_id=first_cluster.id)
            if cluster_events:
                self.log_test("Get events by cluster", True, 
                            f"Retrieved {len(cluster_events)} events for {first_cluster.name}")
            else:
                self.log_test("Get events by cluster", False, "No events for cluster")
            
            # Test get event by ID
            first_event = all_events[0]
            event_by_id = await self.db.get_event_by_id(first_event.id)
            if event_by_id and event_by_id.id == first_event.id:
                self.log_test("Get event by ID", True, f"Retrieved event: {event_by_id.name}")
            else:
                self.log_test("Get event by ID", False, "Failed to retrieve event")
            
            # Test get event by name
            event_by_name = await self.db.get_event_by_name(first_event.name)
            if event_by_name and event_by_name.name == first_event.name:
                self.log_test("Get event by name", True, f"Retrieved event: {event_by_name.name}")
            else:
                self.log_test("Get event by name", False, "Failed to retrieve event")
            
            return True
            
        except Exception as e:
            self.log_test("Database operations test", False, str(e))
            return False
    
    async def test_existing_functionality_preserved(self):
        """Test that existing Game model functionality still works"""
        self.print_header("Testing Existing Functionality Preservation")
        
        try:
            # Test that games still exist
            games = await self.db.get_all_games()
            if len(games) > 0:
                self.log_test("Existing games preserved", True, f"Found {len(games)} games")
            else:
                self.log_test("Existing games preserved", False, "No games found")
            
            # Test game operations still work
            first_game = games[0] if games else None
            if first_game:
                game_by_name = await self.db.get_game_by_name(first_game.name)
                if game_by_name:
                    self.log_test("Game lookup by name works", True, f"Found: {game_by_name.name}")
                else:
                    self.log_test("Game lookup by name works", False, "Game lookup failed")
            
            return True
            
        except Exception as e:
            self.log_test("Existing functionality preservation test", False, str(e))
            return False
    
    async def test_data_constraints(self):
        """Test database constraints and data validation"""
        self.print_header("Testing Data Constraints")
        
        try:
            # Test that cluster numbers are unique
            clusters = await self.db.get_all_clusters()
            cluster_numbers = [c.number for c in clusters]
            unique_numbers = set(cluster_numbers)
            
            if len(cluster_numbers) == len(unique_numbers):
                self.log_test("Cluster numbers are unique", True, f"{len(clusters)} clusters with unique numbers")
            else:
                self.log_test("Cluster numbers are unique", False, f"Duplicate numbers found")
            
            # Test that cluster names are unique
            cluster_names = [c.name for c in clusters]
            unique_names = set(cluster_names)
            
            if len(cluster_names) == len(unique_names):
                self.log_test("Cluster names are unique", True, f"{len(clusters)} clusters with unique names")
            else:
                self.log_test("Cluster names are unique", False, f"Duplicate names found")
            
            # Test that all events have valid scoring types
            events = await self.db.get_all_events()
            valid_scoring_types = {'1v1', 'FFA', 'Team', 'Leaderboard'}
            invalid_events = [e for e in events if e.scoring_type not in valid_scoring_types]
            
            if not invalid_events:
                self.log_test("All events have valid scoring types", True, f"{len(events)} events validated")
            else:
                self.log_test("All events have valid scoring types", False, 
                            f"{len(invalid_events)} events with invalid types")
            
            # Test that all events belong to a cluster
            orphaned_events = [e for e in events if not e.cluster_id]
            
            if not orphaned_events:
                self.log_test("All events belong to a cluster", True, f"{len(events)} events have clusters")
            else:
                self.log_test("All events belong to a cluster", False, 
                            f"{len(orphaned_events)} orphaned events")
            
            return True
            
        except Exception as e:
            self.log_test("Data constraints test", False, str(e))
            return False
    
    async def cleanup_test_data(self):
        """Clean up test data"""
        self.print_header("Cleaning Up Test Data")
        
        try:
            if self.db:
                await self.db.close()
                self.print_success("Database connection closed")
            
            # Remove test database file
            test_db_file = 'test_phase_2a1.db'
            if os.path.exists(test_db_file):
                os.remove(test_db_file)
                self.print_success(f"Removed test database: {test_db_file}")
            
        except Exception as e:
            self.print_error(f"Cleanup failed: {e}")
    
    def print_summary(self):
        """Print test summary"""
        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, passed, _ in self.test_results if passed)
        failed_tests = total_tests - passed_tests
        
        print(f"\n" + "="*60)
        print(f"📋 PHASE 2A.1 TEST SUMMARY")
        print(f"="*60)
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
            print(f"\n🎉 All Phase 2A.1 tests passed! Database schema ready for Phase 2A.2.")
        
        return failed_tests == 0

async def main():
    """Run all Phase 2A.1 tests"""
    print("🧪 Tournament Bot - Phase 2A.1 Test Suite")
    print("Testing: Cluster & Event Models, CSV Import, Database Operations")
    print("=" * 70)
    
    test_suite = Phase2A1TestSuite()
    
    try:
        # Setup test environment
        if not await test_suite.setup_test_environment():
            return 1
        
        # Run all tests
        tests = [
            test_suite.test_schema_creation(),
            test_suite.test_csv_import_integrity(),
            test_suite.test_scoring_type_distribution(),
            test_suite.test_database_operations(),
            test_suite.test_existing_functionality_preserved(),
            test_suite.test_data_constraints(),
        ]
        
        for test in tests:
            await test
        
        success = test_suite.print_summary()
        return 0 if success else 1
        
    except Exception as e:
        print(f"\n💥 CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        await test_suite.cleanup_test_data()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)