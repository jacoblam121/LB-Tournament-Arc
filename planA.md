# LB-Tournament-Arc Implementation Plan A

## Overview
Transform the current simplified FFA system into a proper hierarchical tournament structure with per-event Elo ratings, challenge acceptance workflows, and comprehensive admin tools.

## Clarification on per-event elo ratings
Events are classfied as each game mode from the LB Culling Games List.csv. The match types are just multiple ways to gain elo in that event. So Diep (1v1), Diep(FFA), and Diep(Team) would NOT have separate elos. They would all share ONE elo under the Diep event. There are simply multiple ways to gain/lose elo in that event. 

## Current State Analysis

### What Works
- Match confirmation system functional
- Basic FFA matches work (but incorrectly)
- Modal UI for d5 players
- Hybrid command infrastructure (prefix + slash)

### Critical Issues Identified
1. **No Data**: Clusters/events from CSV not in database
2. **Broken Architecture**: /ffa creates ad-hoc events, bypassing hierarchy (MUST BE REMOVED)
3. **Wrong Elo System**: Global Elo instead of per-event
4. **Missing Commands**: No /challenge command for proper flow
5. **Missing Core Systems**: Ticket Economy, Leverage System, Shard of the Crown unimplemented
6. **No Leaderboard Events**: Statistical scoring system for asynchronous competitions missing
7. **Broken Commands**: Player info commands don't load

### Key Files & Data Sources
- **LB Culling Games List.csv**: 20 clusters, 60+ events with scoring types
- **Ticket System.csv**: Complete earning/spending system specification
- **bot/database/models.py**: Full hierarchy models exist but underutilized
- **bot/cogs/match_commands.py**: Current FFA implementation

## Architecture Requirements

### Tournament Hierarchy
```
Cluster (20 categories)
    → Event (60+ games)
        → Match (game instances)
            → MatchParticipant (player results)
```

### Elo System Architecture
- **Current**: Single global elo_rating per player
- **Required**: Per-event Elo with hierarchy:
  - Event Elo: Direct from matches in that event
  - Cluster Elo: Weighted average of event Elos (prestige system)
  - Overall Elo: Tiered weighting across clusters

### Dual-Track Elo System
- **Raw Elo**: True skill rating (can go below 1000)
- **Scoring Elo**: For leaderboards (floored at 1000)

## ✅ Phase 0: Security Foundation (COMPLETED)

### ✅ 0.1 Critical Security Fix - Admin Permission Bypass (COMPLETED)
**Issue**: Admin permission checks had vulnerabilities allowing potential bypasses
**Solution**: 
- ✅ Implemented owner-only permission model (Config.OWNER_DISCORD_ID only)
- ✅ Created centralized permission utilities: `is_bot_owner()` and `is_user_bot_owner()`
- ✅ Fixed vulnerable locations in match_commands.py (lines 154, 694, 1453)
- ✅ Updated all user-facing messages from "admin" to "owner"
- ✅ Fixed modal UI permission check bug (force parameter)
- ✅ Created comprehensive manual test suite (test_phase_0_security_fix.md)
- ✅ Validated with Gemini 2.5 Pro CodeReview

**Status**: ✅ COMPLETE - Security vulnerability patched, ready for Phase 1

## Phase 1: Database & Architecture Foundation

### 1.1 Create PlayerEventStats Model
```python
class PlayerEventStats(Base):
    __tablename__ = 'player_event_stats'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    
    # Dual-track Elo system
    raw_elo = Column(Integer, default=1000)
    scoring_elo = Column(Integer, default=1000)  # max(raw_elo, 1000)
    
    # Event-specific stats
    matches_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    
    # Leaderboard Event fields (for scoring_type="Leaderboard")
    all_time_leaderboard_elo = Column(Integer, nullable=True)  # From personal best Z-score conversion
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    player = relationship("Player", back_populates="event_stats")
    event = relationship("Event", back_populates="player_stats")
    
    # K-factor tracking
    @property
    def is_provisional(self) -> bool:
        return self.matches_played < 5
    
    @property
    def k_factor(self) -> int:
        return 40 if self.is_provisional else 20
    
    def update_scoring_elo(self):
        """Apply dual-track Elo floor rule"""
        self.scoring_elo = max(self.raw_elo, 1000)

    __table_args__ = (
        UniqueConstraint('player_id', 'event_id', name='uq_player_event_stats'),
    )

# Add SQLAlchemy event listeners for automatic dual-track enforcement
@event.listens_for(PlayerEventStats, "before_insert")
@event.listens_for(PlayerEventStats, "before_update")
def _apply_dual_track_floor(mapper, connection, target):
    """Automatically apply scoring Elo floor on every insert/update"""
    target.scoring_elo = max(target.raw_elo, 1000)

# Update Player model to include relationship and meta-game support
# Add to Player class:
# event_stats = relationship("PlayerEventStats", back_populates="player", cascade="all, delete-orphan")
# active_leverage_token = Column(String(50), nullable=True)  # e.g., "2x_standard", "1.5x_forced"
# current_streak = Column(Integer, default=0)              # Current win/loss streak
# max_streak = Column(Integer, default=0)                  # Highest win streak achieved
# display_name = Column(String(100), nullable=True)        # Cached Discord display name

# Update Event model to include relationship (CRITICAL - Missing from original plan)  
# Add to Event class:
# player_stats = relationship("PlayerEventStats", back_populates="event", cascade="all, delete-orphan")
# score_direction = Column(String(10), nullable=True)  # "HIGH" or "LOW" for leaderboard events
```

### 1.1.1 Additional Models for Leaderboard Events
```python
class PlayerEventPersonalBest(Base):
    __tablename__ = 'player_event_personal_bests'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    
    best_score = Column(Float, nullable=False)  # Actual score (points, time, etc.)
    # Note: For LOW score direction events (speedruns), lower values are better
    # Comparison logic: effective_score = best_score * (1 if event.score_direction=="HIGH" else -1)
    timestamp_achieved = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("Player")
    event = relationship("Event")
    
    __table_args__ = (
        UniqueConstraint('player_id', 'event_id'),
    )

class WeeklyScores(Base):
    __tablename__ = 'weekly_scores'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    
    score = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=func.now())
    
    # Archive strategy: Move rows to weekly_scores_archive table instead of deletion
    # This preserves historical data for audits and retrospectives

class PlayerWeeklyLeaderboardElo(Base):
    __tablename__ = 'player_weekly_leaderboard_elo'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    
    week_number = Column(Integer, nullable=False)  # Season week number
    weekly_elo_score = Column(Integer, nullable=False)
    
    # Permanent log of weekly results
    
    __table_args__ = (
        UniqueConstraint('player_id', 'event_id', 'week_number'),
    )
```

### 1.1.2 TicketLedger Model (Essential for Meta-Game)
```python
class TicketLedger(Base):
    __tablename__ = 'ticket_ledger'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    
    change_amount = Column(Integer, nullable=False)  # Can be positive or negative
    reason = Column(String(255), nullable=False)     # e.g., "MATCH_WIN", "ADMIN_GRANT", "SHOP_PURCHASE"
    balance_after = Column(Integer, nullable=False)  # Computed atomically with SELECT FOR UPDATE
    
    # Optional references
    related_match_id = Column(Integer, ForeignKey('matches.id'), nullable=True)
    
    # Metadata
    timestamp = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("Player", back_populates="ticket_history")
    match = relationship("Match", foreign_keys=[related_match_id])
    
# Update Player model to include ticket system:
# Add to Player class:
# tickets = Column(Integer, default=0)  # Current ticket balance
# ticket_history = relationship("TicketLedger", back_populates="player", cascade="all, delete-orphan")
```

### 1.2 Data Population System
- Create `populate_from_csv.py` script
- Parse `LB Culling Games List.csv` to create:
  - 20 Clusters (Chess, Pokemon, FPS, etc.)
  - 60+ Events with proper cluster associations
  - Correct scoring_type for each event (1v1, FFA, Team, Leaderboard)
- **Score Direction**: Parse and set `score_direction` field for Leaderboard events (HIGH/LOW)
- Add `/admin-populate-data` command to refresh from CSVs
- Use database transactions for atomic updates

#### CSV Parsing Strategy for Mixed Scoring Types
Handle complex scoring types from CSV:

**Mixed Types (e.g., "1v1/FFA"):**
- Create separate Event records for each type
- Example: "Krunker,1v1/FFA" → "Krunker (1v1)" and "Krunker (FFA)" events
- Both events belong to same cluster

**Team Types (e.g., "2v2", "Team"):**
- "2v2" treated as Team format using average Elo approach (per high level overview.md)
- Team average calculation: `R_TeamA = (R_PlayerA1 + R_PlayerA2) / 2`
- Single 1v1 Elo calculation between team averages, same ΔR applied to all team members
- Example: "Basketball Legends,2v2" → "Basketball Legends (Team)" event with scoring_type="Team"

**Multiple Types (e.g., "1v1/Team/FFA"):**
- Create up to 3 separate events per entry
- Append type suffix to event name for clarity
- Normalize "2v2" to "Team" in scoring type classification

**Unknown Types ("???"):**
- Skip during initial population
- Log for manual review
- Default to "1v1" if forced to import

**Implementation:**
```python
def parse_scoring_types(scoring_type_str: str) -> List[str]:
    """Parse mixed scoring types into individual types with case normalization"""
    if '/' in scoring_type_str:
        types = [t.strip().lower() for t in scoring_type_str.split('/')]
        # Normalize all variations to proper case
        normalized = []
        for t in types:
            if t in ('2v2', 'team'):
                normalized.append('Team')
            elif t == '1v1':
                normalized.append('1v1')
            elif t == 'ffa':
                normalized.append('FFA')
            elif t == 'leaderboard':
                normalized.append('Leaderboard')
            else:
                normalized.append(t.capitalize())  # Fallback for unknown types
        return list(dict.fromkeys(normalized))  # Remove duplicates while preserving order
    elif scoring_type_str.strip().lower() == '???':
        return []  # Skip unknown types
    else:
        # Normalize single types
        normalized = scoring_type_str.strip().lower()
        if normalized in ('2v2', 'team'):
            return ['Team']
        elif normalized == '1v1':
            return ['1v1']
        elif normalized == 'ffa':
            return ['FFA']
        elif normalized == 'leaderboard':
            return ['Leaderboard']
        else:
            return [normalized.capitalize()]

def create_event_name_with_suffix(base_name: str, scoring_type: str) -> str:
    """Create event name with appropriate suffix for all scoring types"""
    if scoring_type == 'Team':
        return f"{base_name} (Team)"
    elif scoring_type == 'Leaderboard':
        return f"{base_name} (Leaderboard)"
    elif scoring_type in ['1v1', 'FFA']:
        return f"{base_name} ({scoring_type})"
    else:
        return f"{base_name} ({scoring_type})"  # Fallback for unknown types
```

### 1.3 Database Migration Implementation Strategy

**Reset Approach**: Complete wipe of existing test data as agreed with user

**Migration Script Structure**:
```python
# migration_reset_for_per_event_elo.py
async def migrate_database():
    async with AsyncSessionLocal() as session:
        try:
            # 1. Clear existing data (using correct model names)
            await session.execute(delete(EloHistory))
            await session.execute(delete(MatchParticipant))
            await session.execute(delete(Match))
            await session.execute(delete(Challenge))
            await session.execute(delete(TicketLedger))  # Correct model name
            
            # 2. Create new tables for per-event system FIRST
            # PlayerEventStats, TicketLedger, ShardPool, KingDefeat models (all defined below in this plan)
            # Done via Alembic migration or create_all()
            
            # 2a. Remove legacy Challenge columns BEFORE bulk deletes (to avoid ALTER errors)
            # ALTER TABLE challenges DROP COLUMN challenger_id IF EXISTS;
            # ALTER TABLE challenges DROP COLUMN challenged_id IF EXISTS;
            
            # 3. Add new columns to Player model (ensure they exist before reset)
            # ALTER TABLE players ADD COLUMN active_leverage_token VARCHAR(50);
            # ALTER TABLE players ADD COLUMN current_streak INTEGER DEFAULT 0;
            # ALTER TABLE players ADD COLUMN max_streak INTEGER DEFAULT 0;
            # ALTER TABLE players ADD COLUMN final_score INTEGER;
            # ALTER TABLE players ADD COLUMN shard_bonus INTEGER DEFAULT 0;
            # ALTER TABLE players ADD COLUMN shop_bonus INTEGER DEFAULT 0;
            # ALTER TABLE players ADD COLUMN display_name VARCHAR(100);
            
            # 4. Reset Player stats but keep Discord registrations
            await session.execute(
                update(Player).values(
                    elo_rating=1000,
                    tickets=0,
                    matches_played=0,
                    wins=0,
                    losses=0,
                    draws=0,
                    # Reset new meta-game fields (now that columns exist)
                    active_leverage_token=None,
                    current_streak=0,
                    max_streak=0,
                    final_score=None,
                    shard_bonus=0,
                    shop_bonus=0
                )
            )
            
            # 5. Populate clusters and events from CSV
            await populate_clusters_and_events(session)
            
            await session.commit()
            
        except Exception as e:
            await session.rollback()
            raise e

async def populate_clusters_and_events(session):
    # Clear existing
    await session.execute(delete(Event))
    await session.execute(delete(Cluster))
    
    # Read CSV and create clusters/events
    # Handle mixed scoring types (1v1/FFA -> separate events)
```

**Key Implementation Details**:
- PlayerEventStats created on-demand when player first participates in an event
- **Race Condition Protection**: Use SELECT...FOR UPDATE lock or handle UniqueConstraint integrity errors gracefully for concurrent player-event creation
- All players start at 1000 Elo for each event they participate in
- Preserve Player Discord registrations but reset all tournament stats
- Atomic migration using database transactions
- Add `/admin-reset-elo` command for future testing phases

## Phase 2: Core Challenge System

### 2.1 Implement /challenge Command
Dynamic UI flow with Discord slash command autocomplete:

```
/challenge 
  � cluster: [Select from 20 clusters]
  � event: [Dynamically filtered list based on cluster]
  � type: [Auto-determined by event's scoring_type]
  � players/opponents: [Based on type]

  flow: /challenge /cluster /event /type /players
```

**Discord Autocomplete Pagination Strategy:**
Discord limits autocomplete to 25 choices, but we have 60+ events. Solution:
- **Primary Filter**: Cluster selection (20 options - fits within limit)
- **Dynamic Event Filtering**: Events autocomplete shows only events from selected cluster
- **Search-based Pagination**: Event autocomplete supports typing to filter:
  ```python
  async def event_autocomplete(self, interaction, current: str) -> List[discord.app_commands.Choice]:
      cluster_id = interaction.namespace.cluster  # Get selected cluster
      events = get_events_for_cluster(cluster_id)
      
      # Filter by user input for search functionality
      if current:
          events = [e for e in events if current.lower() in e.name.lower()]
      
      # Return max 25 results
      return [discord.app_commands.Choice(name=e.name, value=e.id) 
              for e in events[:25]]
  ```
- **Fallback**: If cluster has >25 events, user can type partial name to search
- **UI Flow**: Cluster selection → Event selection (filtered by cluster) → Challenge creation

### 2.2 Challenge Workflows by Type

**1v1 Challenges:**
- Challenger selects single opponent
- Creates Challenge record (pending status)
- Sends acceptance request to opponent
- 24-hour expiration

**Team Challenges:**
- Challenger specifies:
  - Own teammates (must accept)
  - Opposing team members (must accept)
- All players must accept before match starts
- Team formation UI with clear team assignments

**FFA Challenges:**
- Challenger invites 2-15 other players via `/challenge cluster:X event:Y` where event scoring_type="FFA"
- All must accept to start
- **CRITICAL**: Remove `/ffa` command entirely - all FFA matches use `/challenge` workflow

### 2.3 Challenge Acceptance System
- Embed with Accept/Decline buttons
- Real-time status updates as players respond
- Notification when all players accept
- Auto-expiration after 24 hours
- Clear rejection handling (show who rejected and why)

### 2.4 Challenge Model Architecture Limitations & Solutions

**Current Issue**: Challenge model only supports 2 players (challenger_id, challenged_id)

**UPDATED STRATEGY (From Gemini 2.5 Pro Review)**: Implement ChallengeParticipant from Day 1

**Benefits of Immediate ChallengeParticipant Implementation**:
- Eliminates future technical debt and complex data migration
- Single consistent architecture for all challenge types (1v1, Team, FFA)
- Reduces implementation risk and development complexity
- Future-proofs the system for N-player support

**Required Enum Definition**:
```python
from sqlalchemy import Enum as SQLEnum
from enum import Enum

class ConfirmationStatus(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted" 
    DECLINED = "declined"
    EXPIRED = "expired"
```

**ChallengeParticipant Model (Implement Immediately)**:
```python
class ChallengeParticipant(Base):
    __tablename__ = 'challenge_participants'
    
    id = Column(Integer, primary_key=True)
    challenge_id = Column(Integer, ForeignKey('challenges.id'), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    
    # Participant role
    is_initiator = Column(Boolean, default=False)  # Who created the challenge
    team_id = Column(String(50), nullable=True)    # For team matches (A, B, Red, Blue)
    
    # Acceptance tracking
    status = Column(SQLEnum(ConfirmationStatus), default=ConfirmationStatus.PENDING)
    responded_at = Column(DateTime, nullable=True)
    
    # Relationships
    challenge = relationship("Challenge", back_populates="participants")
    player = relationship("Player")
    
    # Database constraints
    __table_args__ = (
        UniqueConstraint('challenge_id', 'player_id', name='unique_player_per_challenge'),
    )

# Update Challenge model to REMOVE challenger_id/challenged_id:
# REMOVE: challenger_id = Column(Integer, ForeignKey('players.id'), nullable=False)
# REMOVE: challenged_id = Column(Integer, ForeignKey('players.id'), nullable=False)
# ADD: participants = relationship("ChallengeParticipant", back_populates="challenge", cascade="all, delete-orphan")
```

**Implementation Strategy**:
- Phase 2: Replace Challenge 2-player fields with ChallengeParticipant relationship
- All challenge types (1v1, Team, FFA) use same unified architecture from start
- 1v1 challenges create 2 ChallengeParticipant records (initiator + opponent)
- No future migration needed - single implementation path

## Phase 3: Match & Elo System

### 3.1 Fix Elo Calculations
- Update EloCalculator to use PlayerEventStats instead of global Player.elo_rating
- Provisional status (<5 matches) calculated per event
- K-factor: 40 (provisional), 20 (established)
- Proper multi-player calculations for FFA/Team matches
- Scale K-factor by K/(N-1) for FFA to prevent excessive volatility

### 3.2 Match Result Recording
- Update match completion to modify event-specific Elo
- Create EloHistory records with event context
- Update PlayerEventStats for each participant
- Calculate cluster/overall Elo using weighted formulas from high-level design

### 3.3 Hierarchy Calculations - EXACT FORMULAS

**Event Elo (Level 1):**
- **1v1 Matches**: Standard Elo formula: `ΔR_A = K × (S_A - E_A)`
  - Expected Score: `E_A = 1 / (1 + 10^((R_B - R_A) / 400))`
  - K-factor: 40 (provisional <5 matches), 20 (established)

- **FFA Matches**: Pairwise comparisons with scaled K-factor
  - For N players: `N * (N-1) / 2` pairwise comparisons
  - Scaled K-factor: `K_scaled = K / (N - 1)`
  - Higher placement beats lower placement (S=1.0 vs S=0.0)
  - Total Elo change = sum of all pairwise changes
  - Note: Ensure K-factor scaling is applied once per comparison, not double-applied

- **Team Matches**: Average team rating approach (generalized for any team size)
  - Team average: `R_TeamA = sum(team_A_ratings) / len(team_A_ratings)`
  - Team average: `R_TeamB = sum(team_B_ratings) / len(team_B_ratings)`
  - Single 1v1 Elo calculation between team averages (`R_TeamA` vs `R_TeamB`) 
  - Same ΔR applied to all team members: Winners get `+ΔR`, Losers get `-ΔR`

**Cluster Elo (Level 2) - Prestige Weighting System:**
```
Prestige Multipliers:
- Player's best event in cluster: 4.0x
- Player's second-best event: 2.5x  
- Player's third-best event: 1.5x
- Player's 4+ events: 1.0x

Calculation:
1. Sort player's Event Elos in cluster (highest to lowest)
2. Apply multipliers: Raw_Prestige_Value = Event_Elo × Multiplier
3. Total_Raw_Prestige = Σ(All Raw Prestige Values)
4. Total_Multiplier = Σ(All Assigned Multipliers)
5. Cluster_Elo = Total_Raw_Prestige / Total_Multiplier

Edge Case Handling:
- If player has fewer events than prestige ranks, multipliers still apply in descending order
- Example: Player with 2 events gets 4.0x and 2.5x multipliers
```

**Overall Elo (Level 3) - Weighted Generalist System:**
```
Tier Weights:
- Tier 1 (Ranks 1-10): 60% weight
- Tier 2 (Ranks 11-15): 25% weight
- Tier 3 (Ranks 16-20): 15% weight

Calculation:
1. Sort all 20 Cluster Elos (highest to lowest)
2. Avg_T1 = Average(Ranks 1-10)
3. Avg_T2 = Average(Ranks 11-15)  
4. Avg_T3 = Average(Ranks 16-20)
5. Overall_Elo = (Avg_T1 × 0.60) + (Avg_T2 × 0.25) + (Avg_T3 × 0.15)

Edge Case Handling:
- If player has fewer clusters than required for a tier, tiers are filled top-down
- Example: Player with 12 clusters gets top 10 for Avg_T1, next 2 for Avg_T2, Avg_T3 = 0
- Example: Player with 8 clusters gets all 8 for Avg_T1, Avg_T2 and Avg_T3 = 0
```

**Dual-Track Floor Rule:**
`Scoring_Elo = max(Raw_Elo, 1000)` (applied at ALL levels)

### 3.4 Final Score Calculation System
**Status**: ESSENTIAL - Core competitive feature for leaderboards
**Formula**: `Final Score = Overall Scoring Elo + Shard Bonus + Shop Bonus`

**Database Requirements**:
```python
# Add to Player model:
# final_score = Column(Integer, nullable=True)  # Calculated and cached value
# shard_bonus = Column(Integer, default=0)      # From Shard of the Crown system
# shop_bonus = Column(Integer, default=0)       # From ticket purchases
```

**Calculation Triggers**:
- Recalculated whenever Overall Scoring Elo changes
- Updated when Shard bonuses are awarded (season end)
- Modified when shop purchases affect final score
- Cached for performance in leaderboard queries

**Implementation Phase**: Phase 3 (with Elo system integration)

## Phase 4: Admin Tools

### 4.1 Data Management
- `/admin-populate-data` - Refresh clusters/events from CSVs
- `/admin-reset-elo [all|cluster:name|event:name|player:@user]` - Reset Elo ratings
- `/admin-match-revert <match_id>` - Undo match result (already exists)

### 4.2 Challenge/Match Control
- `/admin-challenge-list` - View all pending challenges
- `/admin-challenge-cancel <id>` - Force cancel a challenge
- `/admin-match-force-complete <id>` - Force a match to complete if players abandon

### 4.3 Player Management & Ticket Administration
- `/admin-player-ban @player event` - Ban player from specific events
- `/admin-tickets <subcommand> user:<@user> amount:<amount> reason:[reason]` - Unified ticket management
  - Subcommands: add, set, remove
  - All operations include audit trail and transaction logging

### 4.4 Season Management (From High Level Overview)
**Status**: ESSENTIAL - Required for tournament operation
- `!season-end` - Freeze scoring, calculate final bonuses, declare winner
- `!season-archive` - Save final state to historical tables
- `!season-reset` - Reset all Elo scores, wipe match history, clear tickets
- **Implementation Phase**: Phase 4 (before system completion)

### 4.5 System Monitoring
- `/admin-logs [matches|tickets|admin]` - View audit logs

## Discussion Notes & Decisions

### Key Clarifications from User
1. **Elo Reset**: All existing Elo was for testing - reset everything to 1000
2. **Priority**: Fix Elo architecture and hierarchy first, then implement 1v1/team challenges
3. **UX**: Continuous interaction through slash commands with autocomplete
4. **Deprecation**: Remove /ffa command - everything goes through /challenge
5. **Acceptance Required**: All matches require opponent acceptance (no auto-join)
6. **Player Commands**: Wait on profile/leaderboard - implement later per high-level design
7. **Ticket Economy**: Defer to future, create ticket_economy.md for notes
8. **Database**: Complete wipe for clean start

### Technical Decisions
- Discord slash command autocomplete IS possible for dynamic event filtering
- Build CSV refresh into bot as admin command (not one-time script)
- Team challenges require teammates AND opponents to accept
- Challenge workflow uses existing Challenge model with acceptance system

### Architecture Evolution
- **Before**: /ffa creates "FFA N-player by User" events dynamically
- **After**: /challenge cluster:Chess event:Bullet → proper Challenge → accepted → Match
- **REMOVE**: /ffa command entirely - all FFA matches through /challenge workflow
- **Goal**: Unified challenge system supporting all match types (1v1, Team, FFA) + separate Leaderboard events

## Implementation Order (Updated with Security Priorities)

### Phase 0: Critical Security Fixes (IMMEDIATE)
1. **Fix admin permission bypass vulnerability** in match-report force parameter
2. **Enhance input validation** in placement parsing functions
3. **Secure configuration validation** on startup

### Phase 1: Database Architecture (Foundation)
1. **Database architecture** (PlayerEventStats, leaderboard models, data population)
2. **Security-enhanced permission system** with proper validation
3. **Secure CSV import** with validation for mixed scoring types
4. **Player model updates** (active_leverage_token field)

### Phase 2: Core Challenge System & Leaderboard Events
1. **Implement /challenge command using ChallengeParticipant model** for unified 1v1, Team, and FFA support
2. **Challenge acceptance workflow** with proper validation
3. **Leaderboard event implementation** (/submit-score, Z-score calculations)
4. **Remove /ffa command entirely** - all FFA through /challenge workflow

### Phase 3: Elo System & Meta-Game Foundation
1. **Fix Elo calculations** for per-event ratings using PlayerEventStats
2. **Implement hierarchy calculations** (prestige weighting, weighted generalist)
3. **Basic Ticket Economy** (earning rules, ledger tracking)
4. **Leverage System foundation** (purchase, activation, consumption)

### Phase 4: Enhanced UI & Core Meta-Game
1. **Enhance /challenge command UI** for team formation and FFA invitations (building on ChallengeParticipant from Phase 2)
2. **Shard of the Crown system** (bonus pools, king defeat tracking)
3. **Complete Ticket Economy** (/shop, /buy, /inventory commands)
4. **Leverage integration** (standard/forced leverage in matches)

### Phase 5: Advanced Features & Polish
1. **Pari-mutuel betting system** (optional enhancement)
2. **MatchCommandsCog refactoring** (split into smaller, focused classes)
3. **Profile/leaderboard commands** with full meta-game integration
4. **Admin tools** and final testing

**Priority Note**: Address security vulnerabilities BEFORE implementing new features

## Core Meta-Game Systems (From High Level Overview)

### The Shard of the Crown System
**Status**: ESSENTIAL - Must implement for complete tournament system
- 300 Elo bonus pools for each of 20+ events
- Activated when first challenge against server owner occurs in event
- King claims bonus if undefeated; players share pool if King defeated

**Database Requirements (Future-Proofed)**:
```python
class ShardPool(Base):
    __tablename__ = 'shard_pools'
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    is_activated = Column(Boolean, default=False)
    activated_at = Column(DateTime, nullable=True)
    is_voided = Column(Boolean, default=False)  # True if king defeated
    
    # Relationships
    event = relationship("Event")
    king_defeats = relationship("KingDefeat", back_populates="shard_pool")
    
class KingDefeat(Base):
    __tablename__ = 'king_defeats'
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=False)
    shard_pool_id = Column(Integer, ForeignKey('shard_pools.id'), nullable=False)
    timestamp = Column(DateTime, default=func.now())
    
    # Relationships
    event = relationship("Event")
    player = relationship("Player")
    match = relationship("Match")
    shard_pool = relationship("ShardPool", back_populates="king_defeats")
```

**Implementation Phase**: Phase 4 (foundation models in Phase 1, logic in Phase 4)

### The Ticket Economy System  
**Status**: CORE FEATURE - Foundation required, logic deferred
- **Foundation**: TicketLedger model and Player.tickets field (Phase 1)
- **Future Logic**: Earning rules (Participation +5, Hot Streak +50, etc.)
- **Future Commands**: `/shop`, `/buy`, `/inventory`, `/toggle-leverage`
- **Database**: Models future-proofed for earning/spending workflows
- **Implementation**: Foundation Phase 1, full system Phase 3+

### The Leverage System
**Status**: HIGH-STAKES FEATURE - Foundation required, logic deferred
- **Foundation**: `Player.active_leverage_token` field (Phase 1)
- **Future Logic**: Purchase, activation, consumption workflow
- **Future Types**: Standard leverage (visible) vs Forced leverage (hidden)
- **Database**: Token state tracking ready for future implementation
- **Implementation**: Foundation Phase 1, full system Phase 3+

### The Pari-Mutuel Betting System
**Status**: SOCIAL FEATURE - Foundation future-proofed, implementation deferred
- **Foundation**: Design ready for future `Bets` table and `Match.is_betting_open`
- **Future Logic**: Pari-mutuel pool distribution with house vig
- **Database**: Models can be added without disrupting existing schema
- **Implementation**: Foundation prepared, full system Phase 5+

### Leaderboard Event System (ADDENDUM B)
**Status**: REQUIRED - Complete scoring type coverage needed
- Asynchronous competitions (Tetris scores, speedruns, etc.)
- Statistical Z-score conversion to Elo ratings
- All-Time PB (50%) + Weekly Average (50%) composite scoring
- **Database Requirements**: 
  - `Event.score_direction` field (HIGH/LOW)
  - `PlayerEventPersonalBest` table
  - `WeeklyScores` and `PlayerWeeklyLeaderboardElo` tables
- **Commands**: `/submit-score`, weekly automated calculations
- **Implementation Phase**: Phase 2 (essential for complete system)

### Profile & Leaderboard Commands (UI/UX Systems)
**Status**: ESSENTIAL FEATURES - Foundation required, full UI deferred
- **Foundation**: Basic read-only `/profile` and `/leaderboard` commands (Phase 3)
- **Future UI**: Interactive components per high level overview specifications:
  - Profile: Drill-down cluster views, match history, ticket ledger pagination
  - Leaderboard: Sortable by all columns (Final Score, Elo, Shard Bonus, Shop Bonus)
  - Navigation: Buttons, select menus, "Culling Games Passport" design
- **Database**: All required data available through existing models
- **Implementation**: Basic commands Phase 3, full interactive UI Phase 5

### Advanced Features (Future Seasons)
- Tournament bracket system
- Scheduled events
- Advanced statistics dashboard
- Season management and archival

## Risk Mitigation & Security Considerations

### Critical Security Issues (From O3 Review)
1. **Admin Permission Bypass Fix**:
   ```python
   # BEFORE (vulnerable):
   is_admin = user.guild_permissions.administrator or user.id == Config.OWNER_DISCORD_ID
   
   # AFTER (secure - BOT OWNER ONLY):
   is_owner = user.id == Config.OWNER_DISCORD_ID
   ```

2. **Input Validation Enhancement**:
   - Add Discord mention sanitization in `_parse_placements_from_string()`
   - Validate placement values are within expected range (1 to N)
   - Escape special characters in user input before processing

3. **Configuration Security**:
   - Add validation for OWNER_DISCORD_ID on startup
   - Consider multiple admin support instead of single owner dependency
   - Add environment variable validation in Config.validate()

### Architecture Improvements (From O3 Review)
1. **MatchCommandsCog Refactoring** (1600+ lines violates SRP):

**Detailed Component Mapping:**
- **MatchUI**: Contains `PlacementModal` and `MatchConfirmationView` classes plus embed creation methods (`_create_success_embed`, `_create_unified_embed`, `_create_termination_embed`)
- **MatchValidation**: Contains input parsing and validation logic (`_parse_placements_from_string`, `_validate_modal_placements`, `_parse_members_from_string`) 
- **MatchPermissions**: Contains `_check_match_permissions` function and all authorization logic with enhanced security validation
- **MatchCommands**: Main Cog class containing Discord command definitions (`/ffa`, `/match-report`), instantiates and delegates to other classes

**Refactoring Benefits:**
- Each class has single responsibility
- Easier testing and maintenance
- Improved code organization
- Better separation of UI, validation, and business logic

2. **Hierarchy Implementation Integration**:
   - Update EloCalculator to use PlayerEventStats instead of global Player.elo_rating
   - Implement prestige weighting and weighted generalist calculations
   - Add CSV import validation for mixed scoring types

### Testing Strategy
- Use test Discord server for development
- Admin reset commands for easy state cleanup
- Comprehensive test cases for challenge flows
- Edge case handling (timeouts, cancellations, etc.)
- **Security testing**: Test permission bypasses and input validation

### Migration Concerns
- Database schema changes require careful migration
- Existing match data will be wiped (acceptable per user)
- New PlayerEventStats model needs proper indexing
- **Security migration**: Update all permission checks during deployment

### UX Considerations
- Clear error messages for invalid cluster/event combinations
- Helpful guidance when events don't support requested match type
- Smooth autocomplete experience
- Proper handling of Discord interaction timeouts
- **Security feedback**: Clear permission denied messages without revealing system details

## Notes for Implementation

- **Critical**: PlayerEventStats must be created before any Elo calculations
- **Important**: Challenge acceptance must be atomic (all accept or match doesn't start)
- **Remember**: Dual-track Elo system (raw vs scoring) for better user experience
- **Consider**: Batch operations for admin commands to avoid Discord rate limits

This plan transforms the current simple FFA system into a proper competitive tournament framework while preserving the robust confirmation and modal systems already built.

## Final Implementation Notes

### Critical Implementation Details (From Final Reviews)
1. **SQLAlchemy Syntax**: Ensure `__table_args__` tuples have proper trailing commas for version compatibility
2. **Scoring Type Normalization**: Consider standardizing all scoring types to single case convention (e.g., UPPER)
3. **Bulk Update Handling**: Add DB-level CHECK constraints or post-migration scripts for dual-track floor enforcement
4. **Enum Defaults**: Use `server_default=text("'pending'")` for SQLite compatibility in ChallengeParticipant status
5. **Tie-Breaking**: Implement deterministic tie-breakers in hierarchical Elo calculations (secondary sort on IDs)
6. **SQLAlchemy Relationships**: Complete all back_populates relationships for PlayerEventPersonalBest and KingDefeat models
7. **Table Naming**: Consider standardizing singular vs plural table naming convention
8. **Function Mapping**: Map existing MatchCommandsCog functions to target refactor classes for clean migration

## O3 Code Review Integration Summary

**Security Enhancements Added:**
- Critical admin permission bypass fix with proper guild validation
- Enhanced input validation for Discord mentions and placement data
- Configuration security improvements with startup validation

**Architecture Improvements Integrated:**
- MatchCommandsCog refactoring strategy to resolve 1600+ line SRP violation with detailed component mapping
- Hierarchy calculation implementation requirements added to Elo system with Team match formulas
- CSV import security validation for mixed scoring types with 2v2 normalization
- PlayerEventStats Event relationship added for complete ORM configuration
- ChallengeParticipant implementation strategy updated to eliminate technical debt

**Implementation Priority Updates:**
- Security fixes moved to Phase 0 (immediate priority)
- All subsequent phases include security validation requirements
- Clear separation between foundation work and feature additions

**Performance Notes:**
- O(N²) FFA calculations acceptable for tournament size (max 12 players = 66 comparisons)
- Memory usage for Discord views acceptable for small-scale tournament usage
- Database query optimization not critical for tournament participant count

**Risk Mitigation Enhanced:**
- Security testing added to validation requirements
- Permission system hardening throughout all phases
- Clear security feedback patterns specified for user experience

The plan maintains its technical soundness while addressing all critical security and architectural concerns identified in the comprehensive code reviews.

## Gemini 2.5 Pro Review Integration (Latest Updates)

**High Priority Fixes Implemented:**
1. **ChallengeParticipant from Day 1**: Eliminated phased migration strategy, implemented unified N-player architecture from start
2. **PlayerEventStats Event Relationship**: Added missing back_populates relationship for complete SQLAlchemy ORM configuration  
3. **Team/2v2 Scoring Clarification**: Defined exact implementation using team average Elo approach from high level overview
4. **MatchCommandsCog Refactoring Details**: Added specific component mapping with clear responsibility separation
5. **Transaction Safety**: Added race condition protection for concurrent PlayerEventStats creation

**Technical Improvements:**
- 2v2 normalized to Team scoring type throughout CSV parsing
- Enhanced implementation code with team average formula integration
- Detailed refactoring roadmap for 1600+ line codebase split
- Future-proofed Challenge architecture for all match types

**Risk Reduction:**
- Eliminated complex data migration by using unified architecture from start
- Addressed SQLAlchemy relationship completeness for query efficiency  
- Clarified ambiguous team scoring implementation
- Added concurrent access protection for database operations

The implementation plan now provides a **comprehensive, security-first approach** with all architectural concerns resolved and technical ambiguities clarified.