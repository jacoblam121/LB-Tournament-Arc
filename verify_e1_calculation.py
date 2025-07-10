#!/usr/bin/env python3
"""
Verify the E1 calculation to determine if it's correct or a bug
"""

def verify_single_player_calculation():
    print("=== E1 Calculation Verification ===")
    
    # From test output: Player 1 before E1
    print("Before E1 test:")
    print("  Weekly Elo Average: 1077.25")
    print("  Weeks Participated: 8")
    
    # Single player calculation
    print("\nSingle player week calculation:")
    print("  Score: 35.75 (Event 19 = LOW direction)")
    print("  Mean: 35.75 (only 1 player)")
    print("  Std Dev: 1.0 (default for single player)")
    print("  Z-score: (35.75 - 35.75) / 1.0 = 0")
    print("  Weekly Elo: 1000 + (0 * 200) = 1000")
    
    # Running average calculation
    print("\nRunning average update:")
    current_total = 1077.25 * 8
    print(f"  Current total: {current_total}")
    new_total = current_total + 1000
    print(f"  New total: {new_total}")
    new_weeks = 8 + 1
    print(f"  New weeks: {new_weeks}")
    new_average = new_total / new_weeks
    print(f"  New average: {new_average}")
    
    # From actual test output
    print("\nActual test result:")
    print("  Weekly Elo Average: 1088.2857142857142")
    print("  Weeks Participated: 7")
    
    print(f"\nExpected vs Actual:")
    print(f"  Expected weeks: 9, Actual: 7")
    print(f"  Expected average: {new_average}, Actual: 1088.2857142857142")
    
    # Let me check if this is an inactivity penalty issue
    print("\nChecking if inactivity penalties affected this...")
    
    # If weeks went from 8 to 7, that's very odd
    # Let me calculate what would give us 1088.28 with 7 weeks
    
    # If weekly_elo_average = 1088.28 and weeks = 7
    # Then total = 1088.28 * 7 = 7618
    total_for_7_weeks = 1088.2857142857142 * 7
    print(f"  Total Elo for 7 weeks: {total_for_7_weeks}")
    
    # What was the previous total for 6 weeks?
    # 7618 - new_weekly_elo = previous_total
    # So new_weekly_elo = 7618 - previous_total
    
    # Let me try different scenarios...
    print("\nTrying to reverse engineer...")
    
    # Scenario: Player had 6 weeks before, got 1000 this week
    prev_weeks = 6
    current_average = 1088.2857142857142
    total_now = current_average * 7
    new_elo_this_week = total_now - (prev_weeks * (total_now - 1000) / 6)
    
    print("This is getting complex. Let me check the actual database state before/after...")

if __name__ == "__main__":
    verify_single_player_calculation()