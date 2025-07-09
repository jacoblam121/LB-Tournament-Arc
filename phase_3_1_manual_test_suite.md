# Phase 3.1 Manual Test Suite: Database Models & Infrastructure

## Test Overview
This test suite verifies the Phase 3.1 leaderboard database models and infrastructure implementation including ScoreDirection enum, LeaderboardScore model, updated PlayerEventStats fields, and migration script.

## Pre-Test Setup

### 1. Database Backup
```bash
# Create database backup before testing
cp tournament.db tournament_backup_phase3_1.db
```

### 2. Environment Verification
```bash
# Verify Python environment
python --version  # Should be 3.8+
pip list | grep sqlalchemy  # Should be installed

# Verify database connection
python -c "from bot.database.database import Database; print('Database import successful')"
```

## Test Suite A: Database Model Validation

### Test A1: ScoreDirection Enum
**Objective**: Verify ScoreDirection enum is properly defined and integrated

**Steps**:
1. Run Python interactive shell
2. Execute:
   ```python
   from bot.database.models import ScoreDirection
   
   # Test enum values
   print("HIGH:", ScoreDirection.HIGH)
   print("LOW:", ScoreDirection.LOW)
   print("HIGH value:", ScoreDirection.HIGH.value)
   print("LOW value:", ScoreDirection.LOW.value)
   ```

**Expected Results**:
- HIGH: ScoreDirection.HIGH
- LOW: ScoreDirection.LOW  
- HIGH value: HIGH
- LOW value: LOW

**Pass/Fail**: ___

### Test A2: LeaderboardScore Model Structure
**Objective**: Verify LeaderboardScore model is properly defined

**Steps**:
1. Run Python interactive shell
2. Execute:
   ```python
   from bot.database.models import LeaderboardScore
   
   # Test model structure
   print("Table name:", LeaderboardScore.__tablename__)
   print("Columns:", [col.name for col in LeaderboardScore.__table__.columns])
   
   # Test relationships
   print("Has player relationship:", hasattr(LeaderboardScore, 'player'))
   print("Has event relationship:", hasattr(LeaderboardScore, 'event'))
   ```

**Expected Results**:
- Table name: leaderboard_scores
- Columns: ['id', 'player_id', 'event_id', 'score', 'score_type', 'week_number', 'submitted_at']
- Has player relationship: True
- Has event relationship: True

**Pass/Fail**: ___

### Test A3: PlayerEventStats Updates
**Objective**: Verify PlayerEventStats has new weekly fields

**Steps**:
1. Run Python interactive shell
2. Execute:
   ```python
   from bot.database.models import PlayerEventStats
   
   # Test new fields exist
   columns = [col.name for col in PlayerEventStats.__table__.columns]
   print("Has weekly_elo_average:", 'weekly_elo_average' in columns)
   print("Has weeks_participated:", 'weeks_participated' in columns)
   
   # Test field defaults
   weekly_col = PlayerEventStats.__table__.columns['weekly_elo_average']
   weeks_col = PlayerEventStats.__table__.columns['weeks_participated']
   print("weekly_elo_average default:", weekly_col.default)
   print("weeks_participated default:", weeks_col.default)
   ```

**Expected Results**:
- Has weekly_elo_average: True
- Has weeks_participated: True
- Both fields should have default values

**Pass/Fail**: ___

## Test Suite B: Migration Script Testing

### Test B1: Migration Script Syntax
**Objective**: Verify migration script has no syntax errors

**Steps**:
1. Run syntax check:
   ```bash
   python -m py_compile migrations/add_leaderboard_fields.py
   ```

**Expected Results**:
- No output (indicates no syntax errors)

**Pass/Fail**: ___

### Test B2: Migration Import Test
**Objective**: Verify all imports work correctly

**Steps**:
1. Run Python interactive shell
2. Execute:
   ```python
   import sys
   sys.path.append('.')
   
   # Test imports
   from migrations.add_leaderboard_fields import upgrade, downgrade
   print("Migration functions imported successfully")
   
   # Test database imports
   from bot.database.database import Database
   from bot.config import Config
   print("Database imports successful")
   ```

**Expected Results**:
- Migration functions imported successfully
- Database imports successful

**Pass/Fail**: ___

## Test Suite C: Database Integration Testing

### Test C1: Database Model Import
**Objective**: Verify all models import without conflicts

**Steps**:
1. Run Python interactive shell
2. Execute:
   ```python
   from bot.database.models import (
       ScoreDirection, LeaderboardScore, PlayerEventStats, 
       Event, Player, Base
   )
   
   # Test SQLAlchemy setup
   from sqlalchemy import create_engine
   engine = create_engine('sqlite:///:memory:')
   
   # Test table creation
   Base.metadata.create_all(engine)
   print("All tables created successfully")
   
   # Verify LeaderboardScore table exists
   from sqlalchemy import inspect
   inspector = inspect(engine)
   tables = inspector.get_table_names()
   print("LeaderboardScore table exists:", 'leaderboard_scores' in tables)
   ```

**Expected Results**:
- All tables created successfully
- LeaderboardScore table exists: True

**Pass/Fail**: ___

### Test C2: Event Model Score Direction
**Objective**: Verify Event model uses ScoreDirection enum

**Steps**:
1. Run Python interactive shell
2. Execute:
   ```python
   from bot.database.models import Event, ScoreDirection
   from sqlalchemy import create_engine
   from sqlalchemy.orm import sessionmaker
   
   # Create in-memory database
   engine = create_engine('sqlite:///:memory:')
   Base.metadata.create_all(engine)
   Session = sessionmaker(bind=engine)
   session = Session()
   
   # Test creating event with score direction
   from bot.database.models import Cluster
   cluster = Cluster(name="Test Cluster", number=1)
   session.add(cluster)
   session.commit()
   
   event = Event(
       name="Test Event",
       cluster_id=cluster.id,
       score_direction=ScoreDirection.HIGH
   )
   session.add(event)
   session.commit()
   
   # Verify storage
   retrieved = session.query(Event).first()
   print("Event score direction:", retrieved.score_direction)
   print("Is HIGH enum:", retrieved.score_direction == ScoreDirection.HIGH)
   
   session.close()
   ```

**Expected Results**:
- Event score direction: ScoreDirection.HIGH
- Is HIGH enum: True

**Pass/Fail**: ___

## Test Suite D: Constraint and Index Testing

### Test D1: LeaderboardScore Unique Constraints
**Objective**: Verify NULL-safe unique constraints work correctly

**Steps**:
1. Run Python interactive shell
2. Execute:
   ```python
   from bot.database.models import *
   from sqlalchemy import create_engine
   from sqlalchemy.orm import sessionmaker
   
   # Create in-memory database
   engine = create_engine('sqlite:///:memory:')
   Base.metadata.create_all(engine)
   Session = sessionmaker(bind=engine)
   session = Session()
   
   # Create test data
   cluster = Cluster(name="Test", number=1)
   session.add(cluster)
   session.commit()
   
   event = Event(name="Test Event", cluster_id=cluster.id)
   session.add(event)
   session.commit()
   
   player = Player(discord_id=123456, username="testuser")
   session.add(player)
   session.commit()
   
   # Test all-time score uniqueness
   score1 = LeaderboardScore(
       player_id=player.id,
       event_id=event.id,
       score=100.0,
       score_type='all_time',
       week_number=None
   )
   session.add(score1)
   session.commit()
   
   print("First all-time score added successfully")
   
   # Try to add duplicate all-time score (should fail)
   try:
       score2 = LeaderboardScore(
           player_id=player.id,
           event_id=event.id,
           score=200.0,
           score_type='all_time',
           week_number=None
       )
       session.add(score2)
       session.commit()
       print("ERROR: Duplicate all-time score should not be allowed")
   except Exception as e:
       print("Correctly prevented duplicate all-time score")
   
   session.close()
   ```

**Expected Results**:
- First all-time score added successfully
- Correctly prevented duplicate all-time score

**Pass/Fail**: ___

### Test D2: Weekly Score Constraints
**Objective**: Verify weekly score constraints work correctly

**Steps**:
1. Continue from Test D1 setup
2. Execute:
   ```python
   # Test weekly score uniqueness
   weekly1 = LeaderboardScore(
       player_id=player.id,
       event_id=event.id,
       score=150.0,
       score_type='weekly',
       week_number=1
   )
   session.add(weekly1)
   session.commit()
   
   print("First weekly score added successfully")
   
   # Try to add duplicate weekly score for same week (should fail)
   try:
       weekly2 = LeaderboardScore(
           player_id=player.id,
           event_id=event.id,
           score=175.0,
           score_type='weekly',
           week_number=1
       )
       session.add(weekly2)
       session.commit()
       print("ERROR: Duplicate weekly score for same week should not be allowed")
   except Exception as e:
       print("Correctly prevented duplicate weekly score")
   
   # Add weekly score for different week (should succeed)
   weekly3 = LeaderboardScore(
       player_id=player.id,
       event_id=event.id,
       score=200.0,
       score_type='weekly',
       week_number=2
   )
   session.add(weekly3)
   session.commit()
   
   print("Weekly score for different week added successfully")
   ```

**Expected Results**:
- First weekly score added successfully
- Correctly prevented duplicate weekly score
- Weekly score for different week added successfully

**Pass/Fail**: ___

## Test Suite E: Error Handling and Edge Cases

### Test E1: Invalid Data Handling
**Objective**: Test how models handle invalid data

**Steps**:
1. Run Python interactive shell
2. Execute:
   ```python
   from bot.database.models import *
   from sqlalchemy import create_engine
   from sqlalchemy.orm import sessionmaker
   
   # Create test environment
   engine = create_engine('sqlite:///:memory:')
   Base.metadata.create_all(engine)
   Session = sessionmaker(bind=engine)
   session = Session()
   
   # Test invalid score_type
   try:
       invalid_score = LeaderboardScore(
           player_id=1,
           event_id=1,
           score=100.0,
           score_type='invalid_type',  # Invalid type
           week_number=None
       )
       session.add(invalid_score)
       session.commit()
       print("WARNING: Invalid score_type was accepted")
   except Exception as e:
       print("Correctly rejected invalid score_type")
   
   # Test negative score
   try:
       negative_score = LeaderboardScore(
           player_id=1,
           event_id=1,
           score=-50.0,  # Negative score
           score_type='all_time',
           week_number=None
       )
       session.add(negative_score)
       session.commit()
       print("WARNING: Negative score was accepted")
   except Exception as e:
       print("Correctly rejected negative score")
   
   session.close()
   ```

**Expected Results**:
- Invalid score_type should be rejected (or warning if accepted)
- Negative score should be rejected (or warning if accepted)

**Pass/Fail**: ___

## Test Results Summary

### Test Suite A: Database Model Validation
- A1: ScoreDirection Enum: ___
- A2: LeaderboardScore Model: ___
- A3: PlayerEventStats Updates: ___

### Test Suite B: Migration Script Testing
- B1: Migration Script Syntax: ___
- B2: Migration Import Test: ___

### Test Suite C: Database Integration Testing
- C1: Database Model Import: ___
- C2: Event Model Score Direction: ___

### Test Suite D: Constraint and Index Testing
- D1: LeaderboardScore Unique Constraints: ___
- D2: Weekly Score Constraints: ___

### Test Suite E: Error Handling and Edge Cases
- E1: Invalid Data Handling: ___

## Overall Assessment

**Total Tests**: 9  
**Passed**: ___  
**Failed**: ___  
**Warnings**: ___  

## Issues Found During Testing

### Critical Issues
1. 

### High Priority Issues
1. 

### Medium Priority Issues
1. 

### Notes and Recommendations
1. 

## Next Steps

Based on test results:

1. **If all tests pass**: Proceed to Phase 3.2 implementation
2. **If critical issues found**: Fix immediately before proceeding
3. **If high priority issues found**: Address before production deployment
4. **If medium priority issues found**: Schedule for future improvement

## Test Sign-Off

**Tester**: ________________  
**Date**: ________________  
**Overall Status**: ________________  
**Ready for next phase**: Yes / No