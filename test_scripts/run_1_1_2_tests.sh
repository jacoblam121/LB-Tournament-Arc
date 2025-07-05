#!/bin/bash

# Phase 1.1.2 Database Models Testing - Master Test Runner
# This script runs all tests for Phase 1.1.2 Database Models

echo "🚀 Phase 1.1.2 Database Models - Comprehensive Testing Suite"
echo "============================================================"

# Check if we're in the correct directory
if [ ! -f "bot/main.py" ]; then
    echo "❌ Error: Please run this script from the project root directory (LB-Tournament-Arc/)"
    exit 1
fi

# Create test_scripts directory if it doesn't exist
mkdir -p test_scripts

echo "📋 Available Tests:"
echo "1. SQLite Direct Commands (manual)"
echo "2. Schema Validation (automated)"
echo "3. Concurrent Access (automated)" 
echo "4. Error Handling & Recovery (automated)"
echo "5. All Automated Tests"
echo ""

# Function to run SQLite commands
run_sqlite_tests() {
    echo "📊 SQLite Direct Commands Test"
    echo "-----------------------------"
    echo "To run SQLite tests manually:"
    echo "1. Find your database file (usually in the project root or data/ folder)"
    echo "2. Open with: sqlite3 your_database.db"
    echo "3. Run commands from: test_scripts/test_1_1_2_sqlite_commands.sql"
    echo ""
    echo "📄 SQL commands file location: test_scripts/test_1_1_2_sqlite_commands.sql"
    echo ""
    
    # Try to find the database file
    echo "🔍 Looking for database files..."
    find . -name "*.db" -type f 2>/dev/null | head -5
    echo ""
}

# Function to run schema validation
run_schema_validation() {
    echo "🔧 Schema Validation Test"
    echo "------------------------"
    python3 test_scripts/test_1_1_2_schema_validation.py
    echo ""
}

# Function to run concurrent access test
run_concurrent_test() {
    echo "⚡ Concurrent Access Test"
    echo "-----------------------"
    python3 test_scripts/test_1_1_2_concurrent_access.py
    echo ""
}

# Function to run error handling test
run_error_handling() {
    echo "🛡️ Error Handling & Recovery Test"
    echo "--------------------------------"
    python3 test_scripts/test_1_1_2_error_handling.py
    echo ""
}

# Function to run all automated tests
run_all_automated() {
    echo "🎯 Running All Automated Tests"
    echo "=============================="
    
    echo "Test 1/3: Schema Validation"
    echo "----------------------------"
    python3 test_scripts/test_1_1_2_schema_validation.py
    
    echo ""
    echo "Test 2/3: Concurrent Access"
    echo "---------------------------"
    python3 test_scripts/test_1_1_2_concurrent_access.py
    
    echo ""
    echo "Test 3/3: Error Handling & Recovery"
    echo "-----------------------------------"
    python3 test_scripts/test_1_1_2_error_handling.py
    
    echo ""
    echo "✅ All automated tests completed!"
    echo ""
}

# Check for command line argument
case "$1" in
    "1"|"sqlite")
        run_sqlite_tests
        ;;
    "2"|"schema")
        run_schema_validation
        ;;
    "3"|"concurrent")
        run_concurrent_test
        ;;
    "4"|"error")
        run_error_handling
        ;;
    "5"|"all"|"")
        run_all_automated
        ;;
    *)
        echo "Usage: $0 [1|sqlite|2|schema|3|concurrent|4|error|5|all]"
        echo ""
        echo "Options:"
        echo "  1, sqlite     - Show SQLite direct commands (manual)"
        echo "  2, schema     - Run schema validation test"
        echo "  3, concurrent - Run concurrent access test"
        echo "  4, error      - Run error handling test"
        echo "  5, all        - Run all automated tests (default)"
        exit 1
        ;;
esac

echo "📝 Test Results Summary"
echo "======================"
echo "Schema validation tests the database table structure and basic CRUD operations"
echo "Concurrent access tests database safety under multiple simultaneous operations"
echo "Error handling tests rollback mechanisms and recovery from various failure scenarios"
echo ""
echo "💡 Next Steps:"
echo "- Review any failed tests above"
echo "- Run manual SQLite tests if needed: $0 sqlite"
echo "- Check the Phase_1_1_2_Database_Models_Test_Plan.md for detailed test verification"
echo ""