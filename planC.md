# LB-Tournament-Arc Implementation Plan C (Phase-Based)

## Executive Summary

This document provides a production-ready implementation roadmap for the LB-Tournament-Arc Discord tournament bot. The plan prioritizes architectural soundness, security, and incremental value delivery through a phased approach.

**Key Implementation Principles:**
1. **Service Layer Architecture** - Separation of concerns and maintainability
2. **Transaction Safety** - Atomic operations for all currency/scoring changes
3. **Security First** - RBAC, rate limiting, and audit trails throughout
4. **Incremental Delivery** - User-visible features every phase

**Critical Decisions:**
- Manual weekly resets for leaderboard events (per user preference)
- 52 configurable parameters across 7 categories
- Double-entry bookkeeping for ticket economy
- Production monitoring and observability from day one

### Phase Overview
- **Phase 1**: Foundation & Infrastructure (Service Layer, Configuration System)
- **Phase 2**: Profile System & Basic Leaderboards
- **Phase 3**: Leaderboard Events with Z-score Conversion
- **Phase 4**: Wallet System & Ticket Economy
- **Phase 5**: Meta-Game Features (Shard, Leverage, Betting)
- **Phase 6**: Administration Tools & Season Management
- **Phase 7**: Security Hardening & Production Readiness

### Major Enhancements from High Level Overview Analysis
- **Leaderboard Event System**: Added complete ADDENDUM B details including Z-score conversion, dual-component formula, manual weekly reset per user request
- **Betting System**: Expanded with full pari-mutuel workflow, betting window timing, VIG percentage, and dramatic payout announcements
- **Shard of the Crown**: Added activation mechanism, distribution logic, and King tracking details
- **Leverage System**: Enhanced with purchase/toggle workflow, consumption timing, and dramatic reveal mechanics
- **Profile "Passport"**: Added detailed multi-layered UI design with exact field layouts
- **Leaderboard "Data Hub"**: Added sortable columns with strategic insights
- **Ticket Economy**: Specified all earning mechanisms with exact values from CSV
- **QOL Commands**: Added 6 new commands for better user experience
- **Season Management**: Detailed admin commands for season lifecycle

## Current State Analysis

### ✅ Implemented Systems
- Core match flow (/challenge, /accept, /report)
- Per-event Elo tracking with dual-track system
- Database models for most features (with gaps)
- Basic scoring strategies (1v1, FFA, Team)
- Modal UI infrastructure
- **Elo Hierarchy Calculations** - FULLY IMPLEMENTED in bot/operations/elo_hierarchy.py with exact multipliers (4.0x, 2.5x, 1.5x, 1.0x) and weights (60%, 25%, 15%)
- **Profile/Leaderboard Commands** - Exist in bot/cogs/player.py but not properly wired

### ❌ Missing Core Systems
1. **Leaderboard Events** - Models exist but no Z-score conversion, score submission, or weekly processing
2. **Ticket Economy** - Models exist but no earning/spending logic
3. **Shard of the Crown** - No implementation at all (missing ShardPool model)
4. **Leverage System** - Field exists but unused (consumption logic missing)
5. **Betting System** - Not implemented (no Bet model)
6. **Admin Tools** - Critical gap for operations
7. **Draw Handling** - Policy not implemented ("explicitly not handled")
8. **Ghost Player Policy** - Not enforced ("never delete Player records")
9. **Season Management** - Commands not implemented (!season-end, !season-archive, !season-reset)
10. **Shop Bonus Integration** - How bonuses affect Final Score not defined

## Architectural Foundation

### Service Layer Pattern (CRITICAL)
```
Discord Commands (Cogs)
         ↓
    Service Layer (Business Logic)
         ↓
    Repository Layer (Data Access)
         ↓
    Database (SQLAlchemy Models)
```

### Exception Hierarchy
```python
# bot/services/exceptions.py
class WalletServiceError(Exception):
    """Base exception for wallet operations."""
    pass

class InsufficientFundsError(WalletServiceError):
    """Raised when player lacks sufficient tickets for transaction."""
    def __init__(self, required: int, available: int):
        self.required = required
        self.available = available
        super().__init__(f"Required {required} tickets, but only {available} available")

class PlayerNotFoundError(WalletServiceError):
    """Raised when player does not exist in database."""
    pass

class DuplicateTransactionError(WalletServiceError):
    """Raised when external_ref already exists (idempotency violation)."""
    pass

class BalanceIntegrityError(WalletServiceError):
    """Raised when cached balance doesn't match ledger sum."""
    pass

class InvalidTransactionError(WalletServiceError):
    """Raised when transaction violates business rules."""
    pass
```

### Transaction Safety Pattern
- Use `async with db.begin()` for all multi-table operations
- Implement SELECT FOR UPDATE for balance modifications
- Never UPDATE balances directly - always use ledger entries
- Add database constraints: `CHECK (tickets >= 0)`

## Implementation Phases

## Phase 1: Foundation & Infrastructure 🔧
**Goal**: Establish core architecture, security, and configuration systems

### 1.1 Service Layer & Database Safety
- [ ] Create service layer structure (bot/services/)
- [ ] Implement base service classes with logging and error handling
- [ ] Add database migrations for missing columns and constraints
- [ ] Create transaction safety patterns (SELECT FOR UPDATE)
- [ ] Set up comprehensive logging and monitoring
- [ ] Implement basic RBAC framework
- [ ] Add rate limiting infrastructure
- [ ] Create audit trail foundation

### 1.2 Configuration Management System
- [ ] Migrate from 7 hardcoded values to database-backed configuration
- [ ] Create ConfigCategory and ConfigEntry models
- [ ] Implement all 52 configuration parameters across 7 categories
- [ ] Add admin slash commands for runtime configuration
- [ ] Create configuration validation and type safety
- [ ] Set up audit trail for configuration changes

**Complete Configuration Categories (52+ Parameters):**
```yaml
elo:      # 6 CRITICAL parameters for competitive rating system
  k_factor_provisional: 40     # Higher K-factor for new players (< 5 matches)
  k_factor_standard: 20        # Standard K-factor for established players
  starting_elo: 1000           # New player baseline Elo
  provisional_match_threshold: 5  # Matches before becoming standard player
  scoring_elo_threshold: 1000  # Minimum Raw Elo for leaderboard inclusion
  leaderboard_base_elo: 1000   # Z-score conversion anchor for leaderboard events

metagame: # 5 parameters for prestige and hierarchy calculations
  cluster_multipliers: [4.0, 2.5, 1.5, 1.0]  # Prestige weighting for top 4 clusters
  overall_tier_weights:        # Weights for Overall Elo calculation
    ranks_1_10: 0.60          # 60% weight for top 10 clusters
    ranks_11_15: 0.25         # 25% weight for middle clusters  
    ranks_16_20: 0.15         # 15% weight for remaining clusters
  shard_bonus_pool: 300        # Shard of the Crown bonus amount
  event_formula_weights:       # Leaderboard event Elo formula
    all_time_weight: 0.5      # All-time performance weight
    weekly_weight: 0.5        # Average weekly performance weight

earning:  # 11 configurable rewards from expanded CSV analysis
  participation_reward: 5      # Per match participation
  first_blood_reward: 50       # First match in event
  hot_tourist_reward: 250      # All clusters achievement
  warm_tourist_reward: 50      # All events in cluster
  social_butterfly_reward: 50  # Match against new opponent
  lightfalcon_bounty: 50       # Beat owner reward
  giant_slayer_reward: 25      # Beat +200 elo opponent
  hot_streak_reward: 50        # 3 wins in a row
  frying_streak_reward: 75     # 5 wins in a row
  party_pooper_reward: 50      # End someone's win streak
  golden_road_reward: 500      # #1 after weekly reset
  win_reward: 10               # Basic win bonus
  first_match_of_day_bonus: 10 # Daily engagement bonus

shop:     # 25+ configurable items from expanded CSV analysis
  drop_lowest_cost: 1000       # Remove worst cluster
  inflation_base_cost: 200     # +10 final score points (cost doubles each purchase)
  inflation_bonus_points: 10   # Points added to final score per purchase
  bounty_costs: {50: 100, 100: 200, 200: 400}  # Bounty amount: cost
  leverage_costs: {'0.5x': 50, '2x': 150, '3x': 300, '5x': 500}  # Multiplier: cost
  forced_leverage_costs: {'0.5x': 100, '1.5x': 300}  # Forced leverage costs
  veto_cost: 300               # Protection from bounty/forced effects
  lifesteal_cost: 200          # Hidden activation - steal 20% tickets
  insider_info_cost: 100       # See betting distribution (3 uses)
  booster_shot_cost: 100       # +10% betting payout bonus
  loot_box_cost: 100          # Random 1-200 ticket reward
  ticket_wager_minimum: 1      # Minimum challenge wager amount
  sponsorship_cost_per_point: 1 # Cost per elo point boost
  tournament_cost: 500         # Host tournament sponsorship
  tournament_prize_split: {first: 0.70, second: 0.20, third: 0.10}

system:   # 8 operational parameters
  match_expiry_hours: 24       # Timeout for unreported matches
  bounty_duration_hours: 48    # How long bounties last
  giant_slayer_elo_threshold: 200  # Elo difference for upset bonus
  hot_streak_threshold: 3      # Wins needed for streak bonus
  vig_percentage: 0.10         # House cut from betting
  elo_per_sigma: 200          # Z-score conversion for leaderboards (ADDENDUM B)
  cache_ttl_hierarchy: 900     # Hierarchy calculation cache (15 minutes)
  cache_ttl_shop: 300         # Shop data cache (5 minutes)
  cache_max_size: 1000        # Maximum cache entries
  owner_discord_id: null      # Configurable owner ID (from env/admin)
  admin_role_name: "tournament-admin"     # Discord role for admin permissions
  moderator_role_name: "tournament-mod"  # Discord role for mod permissions

leaderboard_system: # 15+ CRITICAL parameters for comprehensive ADDENDUM B implementation
  base_elo: 1000                   # Z-score conversion anchor point
  elo_per_sigma: 200              # Elo points per standard deviation (vs original 100)
  min_population_size: 3          # Minimum players for valid statistics
  default_std_dev_fallback: 1.0   # Fallback when std_dev = 0 (identical scores)
  max_z_score_limit: 5.0         # Outlier detection threshold
  statistical_confidence_level: 0.95  # Statistical significance level
  weekly_reset_day: 6             # Sunday (0=Monday, 6=Sunday)  
  weekly_reset_hour: 23           # 11 PM UTC for global compatibility
  weekly_reset_timezone: "UTC"    # Timezone for weekly processing
  automated_processing_enabled: false # Manual control preferred (per user request)
  cache_ttl_scores: 300           # Score cache TTL (5 minutes)
  cache_ttl_statistics: 900       # Population stats cache TTL (15 minutes)
  batch_calculation_size: 100     # Players processed per batch
  max_concurrent_calculations: 5  # Parallel calculation limit
  score_submission_rate_limit: 10 # Max submissions per player per hour
  outlier_detection_enabled: true # Enable statistical outlier filtering
  historical_data_retention_weeks: 52  # Keep weekly data for 1 year

rate_limits: # 5 CRITICAL security parameters for DoS protection
  detailed_profile_cooldown: 30    # Seconds between detailed profile requests per user
  head_to_head_cooldown: 60       # Seconds between H2H analysis requests per user  
  recent_form_cooldown: 45        # Seconds between recent form requests per user
  performance_trends_cooldown: 90 # Seconds between performance trend requests per user
  admin_bypass_enabled: true      # Whether admins bypass all rate limits

game_mechanics: # 12 CRITICAL parameters for hidden activation system
  lifesteal_percentage: 0.20      # Percentage of tickets stolen (20%)
  lifesteal_max_steal: 500        # Maximum tickets stolen per activation
  forced_leverage_gain_mult: 1.5  # Winner's elo multiplier for forced leverage
  forced_leverage_loss_mult: 0.5  # Loser's elo multiplier for forced leverage
  veto_decision_timeout: 30       # Seconds to decide on veto response
  booster_shot_payout_bonus: 0.10 # Betting payout bonus percentage (10%)
  insider_info_max_uses: 3        # Uses per insider info purchase
  loot_box_min_reward: 1         # Minimum loot box payout
  loot_box_max_reward: 200       # Maximum loot box payout
  bounty_duration_hours: 48       # How long bounties remain active
  match_effect_reveal_delay: 2    # Seconds before revealing hidden effects
  effect_animation_duration: 5    # Seconds for effect reveal animations
```

**Phase 1 Deliverables**: Core architecture with service layer, transaction safety, and comprehensive configuration

## Phase 2: Profile System & Basic Leaderboards 🎯
**Goal**: Modern profile/leaderboard system with interactive UI

### 2.1 Complete Profile & Leaderboard Overhaul 🎮

#### 2.1.1 Slash Command Foundation
- [ ] **Convert to Modern Commands**:
  - `/profile [user]` - Replace !profile with proper slash command
  - `/leaderboard [type] [cluster]` - Replace !leaderboard with options
  - Add app_commands decorators and parameter descriptions
  - Remove old prefix commands from player.py
- [ ] **Command Options Setup**:
  - User parameter with proper Member type
  - Leaderboard type dropdown (Overall, Cluster, Event)
  - Cluster selection dropdown when applicable

#### 2.2 Interactive Profile Command
- [ ] **Main Stats View** - High-level summary embed:
  ```
  Title: Culling Games Profile: [Player Name]
  Thumbnail: Player's Discord avatar
  Color: Dynamic (gold for #1 ranked, standard otherwise)
  
  Fields:
  🏆 Final Score: 2150          | 🌍 Server Rank: #1/50      | 🎟️ Tickets: 350
  📈 Overall Scoring Elo: 1950  | 📊 Overall Raw Elo: 1950
  ⚔️ Match Record: W:42 L:20 D:3 (67.7% Winrate)
  🔥 Current Streak: W3 (only show if ≥3)
  
  👑 Top 3 Clusters:            | 💀 Areas for Improvement:
  1. Fighting Games (2100)      | 18. Running (1500)
  2. Minecraft (2050)           | 19. Trivia (1500)  
  3. Chess (1980)               | 20. Rhythm Games (1500)
  ```
- [ ] **Interactive Navigation Components**:
  - Row 1 Buttons: [Clusters Overview] [Match History] [Ticket Ledger] [View on Leaderboard]
  - Row 2: Dropdown menu "Select a Cluster to view its Events..."
- [ ] **Drill-Down Views** (edit original message on interaction):
  - **Clusters Overview**: Paginated list of all 20 clusters with Scoring/Raw Elo
  - **Cluster Details**: Selected cluster's events with 💀 for sub-1000 Raw
  - **Match History**: Recent 5 matches with results and Elo changes
  - **Ticket Ledger**: Recent transactions with reasons
  - All views include [Back to Main Profile] button

#### 2.3 Enhanced Leaderboard Features - "The Sortable Data Hub"
- [ ] **Main Leaderboard View** (`/leaderboard [--sort=column]`):
  ```
  | Rank | Player   | Final Score▼ | Overall Scoring | Overall Raw | Shard | Shop |
  |------|----------|-------------|-----------------|-------------|-------|------|
  | 1    | Alice    | 2150        | 1950           | 1950        | 0     | +200 |
  | 2    | Bob      | 2075        | 2025           | 2025        | +50   | +0   |
  | 3    | David    | 1850        | 1850           | 1850        | 0     | +0   |
  | 4    | Charlie  | 1823        | 1823           | 1785        | 0     | +0   |
  ```
- [ ] **Sorting Insights**:
  - Default: Sort by Final Score (shows tournament leader)
  - By Scoring Elo: Shows skill-based leader (Bob)
  - By Raw Elo: Reveals true skill, exposes "floored" players (Charlie at 1785)
  - By Shard Bonus: King slayers leaderboard
  - By Shop Bonus: Strategic spenders/"whales"
- [ ] **Interactive Features**:
  - Click column headers or use `--sort` parameter
  - Pagination: 10 players per page with [Previous] [Next]
  - User's rank shown in footer: "Your rank: #7/50"
  - Dropdown for quick sorting without commands
- [ ] **Multiple Leaderboard Types**:
  - `/leaderboard` or `/leaderboard overall` - Main competition view
  - `/leaderboard cluster [name]` - Cluster-specific rankings
  - `/leaderboard event [name]` - Event-specific rankings
  - All support `--sort` parameter for column sorting

#### 2.4 EloHierarchyCalculator Integration & Performance
- [ ] **Import and Wire Calculator**:
  - Import EloHierarchyCalculator into player.py
  - Replace legacy player.elo_rating with calculated hierarchy
  - Display cluster Elo and overall Elo properly
  - Show dual-track (Raw vs Scoring) with 💀 emoji for sub-1000 Raw
- [ ] **Performance Optimization**:
  - Replace memory-heavy rank calculation with efficient SQL query
  - Implement efficient H2H record retrieval
  - Add hierarchy calculation caching (15-minute TTL)
- [ ] **Database Indexes**:
  - Add compound index: `(player_id, recorded_at DESC)` on EloHistory
  - Add compound index: `(player_id, opponent_id)` on EloHistory
  - Add compound index: `(match_id, placement)` on MatchParticipant
  - Add index: `(event_id, updated_at DESC)` on PlayerEventStats

#### 2.5 Special Policies & Features
- [ ] **Ghost Player Support**: "(Left Server)" tag for departed players
- [ ] **Draw Policy**: "Explicitly not handled" - cancel and replay
- [ ] **Loading Indicators**: For slower calculations
- [ ] **Error Handling**: Graceful failures with user-friendly messages

**Phase 2 Deliverables**: Modern UI/UX with interactive profile and leaderboard system

## Phase 3: Leaderboard Events 📊
**Goal**: Make leaderboard events fully functional with Z-score conversion (ADDENDUM B from overview)

**Philosophy**: Leaderboard events are asynchronous, performance-based competitions (e.g., Tetris high score, 40L Sprint time, 1-mile run) where players compete against a metric rather than each other directly. The system must reward excellence, encourage consistent participation, maintain competitiveness, and be fair/transparent.

### 3.1 Database Models & Infrastructure
- [ ] Create `LeaderboardScore` model:
  ```python
  class LeaderboardScore(Base):
      __tablename__ = 'leaderboard_scores'
      id = Column(Integer, primary_key=True)
      player_id = Column(Integer, ForeignKey('players.id'))
      event_id = Column(Integer, ForeignKey('events.id'))
      score = Column(Float, nullable=False)
      score_type = Column(String(20))  # 'all_time' or 'weekly'
      submitted_at = Column(DateTime, default=func.now())
      week_number = Column(Integer, nullable=True)  # For weekly scores
      __table_args__ = (
          UniqueConstraint('player_id', 'event_id', 'score_type', 'week_number'),
      )
  ```
- [ ] Add `score_direction` field to Event model (HIGH/LOW enum)
  - HIGH: Higher scores are better (Tetris points, NitroType WPM)
  - LOW: Lower scores are better (40L Sprint time, 1-mile run time)
- [ ] Create `PlayerEventPersonalBest` table for tracking all-time records
- [ ] Add database indexes for score queries
- [ ] **CRITICAL FIX**: Define `ELO_PER_SIGMA` constant in config (200 per ADDENDUM B, NOT 100)
- [ ] Create migration script for new tables

### 3.2 Score Submission System
- [ ] Implement `/submit-score [event] [score]` command
- [ ] Validate event is leaderboard type with score_direction
- [ ] Check if score is personal best (respecting HIGH/LOW direction)
- [ ] Update `PlayerEventPersonalBest` if new PB achieved
- [ ] Add to weekly scores table for current week
- [ ] Return confirmation showing:
  - Current submission vs personal best
  - Current week's best score
  - Whether this triggers leaderboard recalculation
- [ ] **CRITICAL**: When ANY player sets new PB, trigger full event recalculation

### 3.3 Z-Score Statistical Conversion Service
- [ ] Create `LeaderboardScoringService` class implementing statistical normalization:
  ```python
  def calculate_z_score(self, score: float, mean: float, std_dev: float, 
                        direction: ScoreDirection) -> float:
      """Convert raw score to Z-score based on population statistics."""
      if direction == ScoreDirection.HIGH:
          return (score - mean) / std_dev
      else:  # LOW - invert so better times get positive Z-scores
          return (mean - score) / std_dev
  
  def z_score_to_elo(self, z_score: float, base_elo: int = 1000, 
                     elo_per_sigma: int = 200) -> int:
      """Convert Z-score to Elo rating (ADDENDUM B: 200 per sigma)."""
      return int(base_elo + (z_score * elo_per_sigma))
  ```
- [ ] **All-Time Elo Calculation** (triggered on any new PB):
  1. Fetch ALL personal bests for the event
  2. Calculate population mean and standard deviation
  3. Convert each player's PB to Z-score
  4. Convert Z-scores to Elo ratings
  5. Store in `all_time_leaderboard_elo` field
- [ ] **Weekly Elo Calculation** (manual admin command):
  1. Fetch all scores for current week only
  2. Calculate weekly mean and standard deviation
  3. Convert to Z-scores and then Elo
  4. Store in `PlayerWeeklyLeaderboardElo` history table
- [ ] Invalidate leaderboard cache on any recalculation

### 3.4 Manual Weekly Processing System
- [ ] Implement `/admin weekly-reset [event]` command (per user request for manual control)
- [ ] Process workflow:
  1. Calculate weekly Elo for all participants
  2. Log results to `PlayerWeeklyLeaderboardElo` with week number
  3. Post summary in designated channel: "🏆 Tetris Weekly Results (Week 12): 1st: @Alice (1550 Elo)..."
  4. Clear `WeeklyScores` table for fresh week
  5. Update each player's average weekly Elo
- [ ] **Final Event Elo Formula**: 
  ```
  Event Elo = (All_Time_Elo × 0.5) + (Average_Weekly_Elo × 0.5)
  
  Where Average_Weekly_Elo = Σ(weekly_elo_scores) / weeks_in_season
  ```
- [ ] **CRITICAL**: Missed weeks count as 0 in average (penalizes inactivity)
- [ ] Add `/admin list-weekly` to see which events need processing
- [ ] Add `/admin weekly-stats [event]` to preview before processing

**Example Calculation**:
- Week 4 of season
- Alice's All-Time Tetris Elo: 1600
- Weekly scores: Week 1 (1550), Week 2 (1450), Week 3 (missed = 0), Week 4 (1500)
- Sum: 1550 + 1450 + 0 + 1500 = 4500
- Average Weekly: 4500 / 4 = 1125
- Final Event Elo: (1600 × 0.5) + (1125 × 0.5) = 800 + 562.5 = 1362.5

**Phase 3 Deliverables**: Fully functional leaderboard events with statistical conversion

## Phase 4: Wallet System & Ticket Economy 💰
**Goal**: Secure ticket transactions with full earning/spending economy

### 4.1 Core Wallet Implementation
- [ ] Implement WalletService with O(1) atomic operations
- [ ] Create double-entry bookkeeping with TicketLedger
- [ ] Add idempotency via external_ref
- [ ] Implement admin wallet commands
- [ ] Add database constraints and indexes

### 4.2 Ticket Earning Integration
- [ ] **Participation Rewards** (from Ticket System.csv):
  - **Participation Trophy**: +5 tickets for playing any match
  - **First Blood**: +50 for first match in any event (once per event)
  - **Hot Tourist Destinations**: +250 for playing in all clusters (one time)
  - **Warm Tourist Destinations**: +50 for playing all events in a cluster (once per cluster)
  - **Social Butterfly**: +50 for playing against a new opponent (once per opponent)
- [ ] **Game Rewards**:
  - **Claim a Shard**: +50 for beating LightFalcon in an event (once per event)
  - **Boston Scott**: +25 for winning 1v1 vs opponent with 300+ more Elo
  - **Cooking**: +50 for winning 3 matches in a row (losses reset)
  - **Frying**: +75 for winning 5 matches in a row (losses reset)
  - **Party Pooper**: +50 for ending someone's win streak
- [ ] **Leaderboard Rewards**:
  - **Golden Road**: +500 for being #1 after weekly reset (one time)
- [ ] **Match Result Integration**:
  - Show all earned tickets in match result embed
  - Track achievements in separate table for one-time rewards
  - Update win streaks atomically with match results

### 4.3 Shop Implementation
- [ ] Implement `/shop` command with categories
- [ ] Add all items from Ticket System.csv:
  - Collusion: Drop Lowest Test (1000), Inflation (200+)
  - Chaos: Ticket Wager (1+), Loot Box (100)
  - Gambling: Insider Info (100), Booster Shot (100)
  - Bounties: 50/100/200 ticket bounties
  - Leverage: All types (50-500 tickets)
  - Strategy: Lifesteal (200), Veto (300)
  - Tournament: Sponsorship (1+), Host (500)
- [ ] Create `/balance` command
- [ ] Track all purchases with audit trail

**Phase 4 Deliverables**: Fully functional ticket economy with earning and spending

## Phase 5: Meta-Game Features 👑
**Goal**: Implement advanced competitive features

### 5.1 Shard of the Crown System
- [ ] Create `ShardPool` model (event_id, is_activated, bonus_pool=300)
- [ ] Track matches against owner (Config.OWNER_DISCORD_ID from configuration)

#### Activation & Tracking Mechanism
- [ ] **Dormant State**: Each event starts with inactive 300 Elo bonus pool
- [ ] **Activation Trigger**: 
  - [ ] Pool activates on FIRST match against the King in that event
  - [ ] Record `activation_match_id` for historical tracking
  - [ ] Announce activation: "👑 **Shard Activated!** The King's 300 Elo bonus for [Event] is now in play!"
- [ ] **Tracking King's Status**:
  - [ ] Monitor all matches in activated events
  - [ ] Track if King has been defeated in each event
  - [ ] Maintain list of players who defeated King per event

#### Real-Time Calculation & Display
- [ ] **Scenario 1 - King Undefeated (Active)**:
  - [ ] If King remains undefeated in an activated event
  - [ ] King shows full 300 Elo bonus in current Final Score calculation
  - [ ] Displayed in real-time on leaderboards with "👑 Shard Bonus: +300" notation
- [ ] **Scenario 2 - King Defeated (Active)**:
  - [ ] The moment ANY player beats King, void King's claim permanently
  - [ ] Track all players who defeat King throughout season
  - [ ] Calculate and display current bonus: 300 Elo ÷ number of defeaters
  - [ ] Example: 3 players beat King in Chess → each shows "👑 Shard Bonus: +100" in real-time
  - [ ] Update all leaderboards immediately when new defeater emerges
- [ ] **Unactivated Events**: No bonus shown (King never played)

#### Season-End Freeze
- [ ] **Tournament End**: Freeze current Shard calculations permanently
- [ ] **No Recalculation**: Final scores locked with whatever Shard bonuses were active
- [ ] **Historical Preservation**: Archive final Shard distribution for season records

#### Implementation Details
- [ ] Create `king_defeats` tracking table:
  ```python
  class KingDefeat(Base):
      __tablename__ = 'king_defeats'
      player_id = Column(Integer, ForeignKey('players.id'))
      event_id = Column(Integer, ForeignKey('events.id'))
      match_id = Column(Integer, ForeignKey('matches.id'))
      defeated_at = Column(DateTime, default=func.now())
  ```
- [ ] Add to match completion flow: Check if loser is King
- [ ] Season-end distribution job:
  1. Query all activated ShardPools
  2. For each pool, check if King was defeated
  3. Calculate and distribute bonuses
  4. Update player Final Scores
- [ ] Show Shard bonus separately in leaderboards for transparency

#### Activation & Tracking Mechanism
- [ ] **Dormant State**: Each event starts with inactive 300 Elo bonus pool
- [ ] **Activation Trigger**: 
  - [ ] Pool activates on FIRST match against the King in that event
  - [ ] Record `activation_match_id` for historical tracking
  - [ ] Announce activation: "👑 **Shard Activated!** The King's 300 Elo bonus for [Event] is now in play!"
- [ ] **Tracking King's Status**:
  - [ ] Monitor all matches in activated events
  - [ ] Track if King has been defeated in each event
  - [ ] Maintain list of players who defeated King per event

#### Distribution Logic at Season End
- [ ] **Scenario 1 - King Undefeated**:
  - [ ] If King remains undefeated in an activated event
  - [ ] King claims full 300 Elo bonus for that event
  - [ ] Added directly to King's Final Score calculation
- [ ] **Scenario 2 - King Defeated**:
  - [ ] The moment ANY player beats King, void King's claim permanently
  - [ ] Track all players who defeat King throughout season
  - [ ] At season end: Divide 300 Elo equally among all defeaters
  - [ ] Example: 3 players beat King in Chess → each gets 100 Elo bonus
- [ ] **Unactivated Events**: No bonus distributed (King never played)

#### Implementation Details
- [ ] Create `king_defeats` tracking table:
  ```python
  class KingDefeat(Base):
      __tablename__ = 'king_defeats'
      player_id = Column(Integer, ForeignKey('players.id'))
      event_id = Column(Integer, ForeignKey('events.id'))
      match_id = Column(Integer, ForeignKey('matches.id'))
      defeated_at = Column(DateTime, default=func.now())
  ```
- [ ] Add to match completion flow: Check if loser is King
- [ ] Season-end distribution job:
  1. Query all activated ShardPools
  2. For each pool, check if King was defeated
  3. Calculate and distribute bonuses
  4. Update player Final Scores
- [ ] Show Shard bonus separately in leaderboards for transparency

### 5.2 Leverage System: High-Stakes Manipulation
- [ ] Database: Use existing `Player.active_leverage_token` field

#### Toggle & Activation Workflow
- [ ] **Purchase**: Player buys leverage from `/shop`, added to inventory
- [ ] **Arming the Token**:
  - [ ] `/toggle-leverage` shows dropdown of owned leverage items
  - [ ] Player selects "2x Leverage (Standard)"
  - [ ] Update `active_leverage_token = '2x_standard'`
  - [ ] Confirm: "✅ **2x Leverage ARMED!** It will be consumed on your next initiated match"
  - [ ] Re-toggle to disarm: `active_leverage_token = NULL`
- [ ] **Visual Indicator**: Show armed leverage in player profile/status

#### Consumption & Match Creation
- [ ] **Trigger**: Token consumed when holder INITIATES match (not when accepting)
- [ ] **Standard Leverage (Open Threat)**:
  - [ ] Alter match creation message:
    ```
    ⚠️ **LEVERAGE APPLIED!** @Alice has challenged @Bob to a **2x Elo Match!**
    Match ID: #1338. The stakes have been doubled!
    ```
  - [ ] All players see multiplier upfront
  - [ ] Psychological warfare - opponent knows the risk
- [ ] **Forced Leverage (Hidden Threat)**:
  - [ ] Normal match creation message:
    ```
    @Alice has challenged @Bob. Match ID: #1339. Good luck!
    ```
  - [ ] NO indication of leverage
  - [ ] Creates tension - any match could be leveraged

#### The Dramatic Reveal
- [ ] **Standard Leverage Result**:
  - [ ] Show multiplied Elo in result embed
  - [ ] "Final Elo: Alice: +48 (2x multiplier), Bob: -48 (2x multiplier)"
- [ ] **Forced Leverage Result**:
  - [ ] First show base Elo: "Alice: +12, Bob: -12"
  - [ ] Then dramatic separate message:
    ```
    💥 **FORCED LEVERAGE REVEALED!** 
    @Alice used a 1.5x Forced Leverage token! 
    
    ACTUAL RESULTS:
    Alice: +18 Elo
    Bob: -18 Elo
    
    The trap has been sprung!
    ```
- [ ] **Cleanup**: Set `active_leverage_token = NULL` after match finalized
- [ ] **Protection**: Veto items in shop can block leverage effects

#### Toggle & Activation Workflow
- [ ] **Purchase**: Player buys leverage from `/shop`, added to inventory
- [ ] **Arming the Token**:
  - [ ] `/toggle-leverage` shows dropdown of owned leverage items
  - [ ] Player selects "2x Leverage (Standard)"
  - [ ] Update `active_leverage_token = '2x_standard'`
  - [ ] Confirm: "✅ **2x Leverage ARMED!** It will be consumed on your next initiated match"
  - [ ] Re-toggle to disarm: `active_leverage_token = NULL`
- [ ] **Visual Indicator**: Show armed leverage in player profile/status

#### Consumption & Match Creation
- [ ] **Trigger**: Token consumed when holder INITIATES match (not when accepting)
- [ ] **Standard Leverage (Open Threat)**:
  - [ ] Alter match creation message:
    ```
    ⚠️ **LEVERAGE APPLIED!** @Alice has challenged @Bob to a **2x Elo Match!**
    Match ID: #1338. The stakes have been doubled!
    ```
  - [ ] All players see multiplier upfront
  - [ ] Psychological warfare - opponent knows the risk
- [ ] **Forced Leverage (Hidden Threat)**:
  - [ ] Normal match creation message:
    ```
    @Alice has challenged @Bob. Match ID: #1339. Good luck!
    ```
  - [ ] NO indication of leverage
  - [ ] Creates tension - any match could be leveraged

#### The Dramatic Reveal
- [ ] **Standard Leverage Result**:
  - [ ] Show multiplied Elo in result embed
  - [ ] "Final Elo: Alice: +48 (2x multiplier), Bob: -48 (2x multiplier)"
- [ ] **Forced Leverage Result**:
  - [ ] First show base Elo: "Alice: +12, Bob: -12"
  - [ ] Then dramatic separate message:
    ```
    💥 **FORCED LEVERAGE REVEALED!** 
    @Alice used a 1.5x Forced Leverage token! 
    
    ACTUAL RESULTS:
    Alice: +18 Elo
    Bob: -18 Elo
    
    The trap has been sprung!
    ```
- [ ] **Cleanup**: Set `active_leverage_token = NULL` after match finalized
- [ ] **Protection**: Veto items in shop can block leverage effects

### 5.3 Pari-mutuel Betting System ("The Alex Moment")
- [ ] Create `Bet` model with proper constraints and foreign keys
- [ ] Add `is_betting_open` and `betting_closed_at` to Match model
- [ ] Implement `/bet [match_id] [amount] [@player]` with validation

#### Betting Window Workflow
- [ ] **Opening**: 
  - [ ] When bet-eligible match created (primarily 1v1), announce: "@Alice has challenged @Bob. Match ID: #1340. **Bets are now open!** Use `/bet 1340 ...`"
  - [ ] Attach interactive `[Place a Bet]` button that pre-fills command
  - [ ] Consider dedicated betting thread per match for hype building
- [ ] **Placing Bets**:
  - [ ] Validate betting still open for match
  - [ ] Check bettor has sufficient tickets
  - [ ] Escrow tickets immediately (reduce balance, create ledger entry)
  - [ ] Create Bet record with pending status
  - [ ] Public confirmation: "📈 **New Bet!** @Charlie wagered 50 tickets on @Alice. Total pool: 250 tickets"
- [ ] **Closing**:
  - [ ] **CRITICAL**: Close instant ANY participant uses `/match-report`
  - [ ] Update `is_betting_open = False` atomically
  - [ ] Announce: "🔒 **Betting closed for Match #1340!** Result submitted. Good luck bettors!"
  - [ ] Reject any subsequent bet attempts

#### Pari-mutuel Pool Calculations
- [ ] **House Cut (Vigorish)**:
  - [ ] Define `VIG_PERCENTAGE` in config (default: 10%)
  - [ ] Purpose: Remove tickets from economy, prevent inflation
  - [ ] Example: 500 ticket pool → 50 ticket vig → 450 prize pool
- [ ] **Payout Distribution**:
  ```python
  # After match result confirmed
  total_pool = sum(all_bets_for_match)
  vig_amount = total_pool * VIG_PERCENTAGE
  prize_pool = total_pool - vig_amount
  
  # Get winning bets
  winning_bets = bets.filter(target_player_id == actual_winner_id)
  winning_pool = sum(winning_bets.amounts)
  
  # Distribute proportionally
  for bet in winning_bets:
      payout = (bet.amount / winning_pool) * prize_pool
      # Credit tickets to bettor
  ```
- [ ] **Example**: 
  - Total bets: 500 tickets (150 on winner, 350 on loser)
  - Vig: 50 tickets (10%)
  - Prize pool: 450 tickets
  - Bettor who wagered 75 on winner gets: (75/150) × 450 = 225 tickets

#### Transaction Safety
- [ ] **ATOMIC TRANSACTION**: Close betting and start match report in single transaction
- [ ] SELECT FOR UPDATE on Match row to prevent race conditions
- [ ] Ensure all bet escrows complete before closing window
- [ ] Handle edge cases: match cancelled, draws, disconnections
- [ ] **Public Announcement**: "🎉 **Match #1340 Concluded!** @Bob wins! 450 ticket prize pool distributed to winning bettors. @David turned 75 into 225!"

#### Betting Window Workflow
- [ ] **Opening**: 
  - [ ] When bet-eligible match created (primarily 1v1), announce: "@Alice has challenged @Bob. Match ID: #1340. **Bets are now open!** Use `/bet 1340 ...`"
  - [ ] Attach interactive `[Place a Bet]` button that pre-fills command
  - [ ] Consider dedicated betting thread per match for hype building
- [ ] **Placing Bets**:
  - [ ] Validate betting still open for match
  - [ ] Check bettor has sufficient tickets
  - [ ] Escrow tickets immediately (reduce balance, create ledger entry)
  - [ ] Create Bet record with pending status
  - [ ] Public confirmation: "📈 **New Bet!** @Charlie wagered 50 tickets on @Alice. Total pool: 250 tickets"
- [ ] **Closing**:
  - [ ] **CRITICAL**: Close instant ANY participant uses `/match-report`
  - [ ] Update `is_betting_open = False` atomically
  - [ ] Announce: "🔒 **Betting closed for Match #1340!** Result submitted. Good luck bettors!"
  - [ ] Reject any subsequent bet attempts

#### Pari-mutuel Pool Calculations
- [ ] **House Cut (Vigorish)**:
  - [ ] Define `VIG_PERCENTAGE` in config (default: 10%)
  - [ ] Purpose: Remove tickets from economy, prevent inflation
  - [ ] Example: 500 ticket pool → 50 ticket vig → 450 prize pool
- [ ] **Payout Distribution**:
  ```python
  # After match result confirmed
  total_pool = sum(all_bets_for_match)
  vig_amount = total_pool * VIG_PERCENTAGE
  prize_pool = total_pool - vig_amount
  
  # Get winning bets
  winning_bets = bets.filter(target_player_id == actual_winner_id)
  winning_pool = sum(winning_bets.amounts)
  
  # Distribute proportionally
  for bet in winning_bets:
      payout = (bet.amount / winning_pool) * prize_pool
      # Credit tickets to bettor
  ```
- [ ] **Example**: 
  - Total bets: 500 tickets (150 on winner, 350 on loser)
  - Vig: 50 tickets (10%)
  - Prize pool: 450 tickets
  - Bettor who wagered 75 on winner gets: (75/150) × 450 = 225 tickets

#### Transaction Safety
- [ ] **ATOMIC TRANSACTION**: Close betting and start match report in single transaction
- [ ] SELECT FOR UPDATE on Match row to prevent race conditions
- [ ] Ensure all bet escrows complete before closing window
- [ ] Handle edge cases: match cancelled, draws, disconnections
- [ ] **Public Announcement**: "🎉 **Match #1340 Concluded!** @Bob wins! 450 ticket prize pool distributed to winning bettors. @David turned 75 into 225!"

**Phase 5 Deliverables**: Complete meta-game features (Shard, Leverage, Betting)

## Phase 6: Administration Tools & UX Enhancements 🛡️
**Goal**: Operational tools, season lifecycle, and user experience improvements

### 6.1 UX Enhancement Commands
For commands that involve specifying the event, it should be cluster:X Event:Y for distinction; some events have the same name but are in different clusters
- [ ] **Core Statistics (Implementation Priority)**:
  - `/detailed-profile [@player]` - Deep dive into player stats
  - `/head-to-head @player1 @player2` - Compare two players
  - `/recent-form [@player]` - Last 10 matches analysis
- [ ] **Advanced Analytics**:
  - `/player-vs-event @player [event]` - Performance in specific event
  - `/match-details [match_id]` - Full match breakdown
  - `/performance-trends [@player]` - Elo graphs over time
- [ ] **Additional QoL Commands**:
  - `/match-history [@player] [--event] [--limit]` - Filtered history
  - `/active-matches [event]` - Active matches (can be specified by event or for all events)
  - `/bounties` - Current bounty board
  - `/my-bets` - Personal betting history
  - `/streaks` - Current win/loss streaks leaderboard
  - `/inventory` - Private view of owned consumables and strategic items
  - `/admin-inventory [@player]` - Admin command to view any player's inventory

#### 6.1.1 Inventory System Implementation
- [ ] **`/inventory` Command (Private Response)**:
  - [ ] **Privacy**: Use `ephemeral=True` - only visible to command user
  - [ ] **Categories Display**:
    ```
    🎒 **Your Inventory**
    
    **Leverage Tokens** 💪
    • 2x Standard Leverage (2 owned)
    • 1.5x Forced Leverage (1 owned)
    • 0.5x Standard Leverage (3 owned)
    
    **Strategic Items** 🧠
    • Veto Protection (2 owned)
    • Insider Info (1 owned, 2 uses remaining)
    • Booster Shot (3 owned)
    
    **Chaos Items** 🎲
    • Loot Box (5 owned)
    • Lifesteal (1 owned - ready to activate)
    
    **Currently Armed** ⚡
    • 2x Standard Leverage (will be consumed on next initiated match)
    ```
  - [ ] **Interactive Elements**:
    - [ ] [Toggle Leverage] button for quick leverage management
    - [ ] [Use Item] dropdown for immediate consumption items
    - [ ] [Refresh] button to update inventory status
  - [ ] **Usage Tracking**: Show remaining uses for multi-use items
  - [ ] **Armed Status**: Highlight currently active/armed items

- [ ] **`/admin-inventory [@player]` Command (Admin Only)**:
  - [ ] **Permissions**: Require admin role or owner status
  - [ ] **Same Layout**: Identical to player inventory but for specified player
  - [ ] **Additional Info**: Show purchase history timestamps
  - [ ] **Admin Actions**: Optional [Grant Item] [Remove Item] buttons
  - [ ] **Audit Trail**: Log all admin inventory views for security

### 6.2 Season Management Commands
- [ ] `/admin season-end` - Freeze all scoring and match reporting
  - Calculate all Shard of Crown distributions
  - Apply all shop bonuses to Final Scores
  - Generate final leaderboard snapshot
  - Announce season winner with fanfare
- [ ] `/admin season-archive` - Save complete season state
  - Create historical tables with season number
  - Archive all player stats, matches, transactions
  - Generate season summary statistics
- [ ] `/admin season-reset` - Prepare for new season
  - Reset all Elo to starting values (1000)
  - Clear match history and ticket balances
  - Preserve player accounts (ghost player policy)
  - Reset Shard pools to dormant state
- [ ] **Final Score Formula**: 
  ```
  Final Score = Overall Scoring Elo + Shard Bonuses + Shop Bonuses
  ```

**Phase 6 Deliverables**: Complete admin toolkit, UX enhancements, and season management

## Phase 7: Security Hardening & Production Readiness 🚀
**Goal**: Production security and deployment preparation

### 7.1 Security Implementation
- [ ] **Comprehensive Rate Limiting**:
  - Per-command configurable limits stored in database
  - Admin/owner bypass capability
  - Graceful error messages for rate limit hits
  - DDoS protection at command level
- [ ] **Input Validation & Sanitization**:
  - Validate all user inputs (match IDs, amounts, player mentions)
  - SQL injection prevention (parameterized queries already in use)
  - Command injection protection for admin commands
  - Maximum bet/wager limits enforcement
- [ ] **Fraud Detection**:
  - Detect suspicious betting patterns
  - Flag unusual ticket transfers
  - Monitor for match fixing indicators
  - Alert system for admin review

### 7.2 Production Monitoring & Observability
- [ ] **Logging Infrastructure**:
  - Structured logging with proper log levels
  - Centralized log aggregation setup
  - Error tracking and alerting
  - Performance metrics collection
- [ ] **Health Monitoring**:
  - Database connection health checks
  - Discord API status monitoring
  - Command success/failure rates
  - Response time tracking
- [ ] **Backup Strategy**:
  - Automated daily database backups
  - Transaction log archival
  - Disaster recovery procedures
  - Backup restoration testing

### 7.3 Performance Optimization
- [ ] **Database Optimization**:
  - Query performance analysis
  - Missing index identification
  - Connection pool tuning
  - Query result caching
- [ ] **Command Response Times**:
  - Target < 1 second for all commands
  - Async operation optimization
  - Background job processing
  - Rate limit implementation

### 7.4 Deployment & Documentation
- [ ] **Deployment Package**:
  - Docker containerization
  - Environment configuration
  - Secrets management
  - Health check endpoints
- [ ] **Documentation**:
  - API documentation
  - Admin operation guide
  - Troubleshooting playbook
  - Configuration reference
- [ ] **Testing Suite**:
  - Unit test coverage > 80%
  - Integration test scenarios
  - Load testing results
  - Security audit completion

**Phase 7 Deliverables**: Production-ready system with monitoring, security, and deployment package

## Key Architectural Components

### Service Layer Architecture
```
Discord Commands (Cogs)
         ↓
    Service Layer (Business Logic)
         ↓
    Repository Layer (Data Access)  
         ↓
    Database (SQLAlchemy Models)
```

### Core Services
1. **WalletService** - Atomic ticket transactions with double-entry bookkeeping
2. **EloHierarchyService** - Cluster and overall calculations (already implemented)
3. **BettingService** - Pari-mutuel pool management with VIG
4. **GameMechanicsService** - Hidden effects and dramatic reveals
5. **LeaderboardService** - Cached leaderboard generation
6. **ConfigurationService** - Dynamic configuration management (52 parameters)

### Transaction Safety Pattern
- Use `async with db.begin()` for all multi-table operations
- Implement SELECT FOR UPDATE for balance modifications
- Never UPDATE balances directly - always use ledger entries
- Add database constraints: `CHECK (tickets >= 0)`

## Critical Implementation Details

### Draw Policy
"Explicitly not handled" - Players must cancel match and replay

### Ghost Player Policy  
Never delete Player records when users leave server - mark as "(Left Server)"

### Manual Weekly Reset
Leaderboard events use manual `/admin weekly-reset [event]` command (per user preference)

### Betting Window Timing
Closes instantly when ANY participant uses `/match-report`

### Leverage Consumption
Token consumed when holder INITIATES match (not accepts)

## Testing Strategy

### Unit Tests
- WalletService: Atomic operations, race conditions
- EloHierarchyService: Calculation accuracy
- BettingService: Payout distribution
- ConfigurationService: Type safety

### Integration Tests
- End-to-end match flow with rewards
- Betting lifecycle from open to payout
- Season reset with data preservation
- Admin operations with audit trails

### Performance Tests
- 1000+ concurrent transactions
- Large leaderboard generation
- Cache effectiveness
- Query optimization validation

## Success Metrics

- Zero currency inconsistencies
- All commands respond within 1 second
- 80% user engagement with economy
- <1% transaction error rate
- Complete audit trail coverage

## Risk Mitigation

1. **Currency Integrity** - O(1) operations with full audit trail
2. **Security** - RBAC, rate limiting, input validation
3. **Performance** - Caching, indexes, query optimization
4. **Rollback** - Feature flags and reversible migrations

## Database Models Required

### New Models to Create
```python
# bot/database/models.py additions

class TransactionType(Enum):
    """Types of ticket transactions."""
    MATCH_WIN = "match_win"
    MATCH_PARTICIPATION = "match_participation"
    STREAK_BONUS = "streak_bonus"
    UPSET_BONUS = "upset_bonus"
    SHOP_PURCHASE = "shop_purchase"
    ADMIN_GRANT = "admin_grant"
    ADMIN_REMOVE = "admin_remove"
    BET_ESCROW = "bet_escrow"
    BET_PAYOUT = "bet_payout"
    BET_REFUND = "bet_refund"
    RECONCILIATION = "reconciliation"
    SEASON_REWARD = "season_reward"

class ShardPool(Base):
    """Tracks Shard of the Crown bonus pools per event."""
    __tablename__ = 'shard_pools'
    
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey('events.id'), unique=True, nullable=False)
    is_activated = Column(Boolean, default=False)
    bonus_pool = Column(Integer, default=300)
    activation_match_id = Column(Integer, ForeignKey('matches.id'), nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    event = relationship("Event")
    activation_match = relationship("Match")

class Bet(Base):
    """Tracks player bets on matches for pari-mutuel system."""
    __tablename__ = 'bets'
    
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey('matches.id'), nullable=False)
    bettor_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    target_player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    amount = Column(Integer, nullable=False)
    potential_payout = Column(Float, nullable=True)  # Calculated when betting closes
    actual_payout = Column(Integer, nullable=True)   # Set when match completes
    status = Column(String(20), default='pending')   # pending, won, lost, refunded
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    match = relationship("Match")
    bettor = relationship("Player", foreign_keys=[bettor_id])
    target_player = relationship("Player", foreign_keys=[target_player_id])
    
    # Constraints
    __table_args__ = (
        CheckConstraint('amount > 0', name='positive_bet_amount'),
        UniqueConstraint('match_id', 'bettor_id', 'target_player_id', name='unique_bet_per_target'),
    )

class KingDefeat(Base):
    """Tracks when players defeat the King for Shard distribution."""
    __tablename__ = 'king_defeats'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'))
    event_id = Column(Integer, ForeignKey('events.id'))
    match_id = Column(Integer, ForeignKey('matches.id'))
    defeated_at = Column(DateTime, default=func.now())

class LeaderboardScore(Base):
    """Tracks personal bests for leaderboard events."""
    __tablename__ = 'leaderboard_scores'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id'), nullable=False)
    score = Column(Float, nullable=False)
    submitted_at = Column(DateTime, default=func.now())
    is_personal_best = Column(Boolean, default=False)
    
    # Relationships
    player = relationship("Player")
    event = relationship("Event")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('player_id', 'event_id', 'is_personal_best', name='unique_personal_best'),
    )

class Configuration(Base):
    """Database-backed configuration with hot reload capability."""
    __tablename__ = 'configurations'
    
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), nullable=False)  # 'int', 'float', 'bool', 'str', 'json'
    description = Column(Text)
    is_sensitive = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=func.now())
    updated_by = Column(String(100))
```

### Existing Models to Update
- Add `score_direction` to Event model (HIGH/LOW)
- Add `is_betting_open` and `betting_closed_at` to Match model
- Ensure `Player.active_leverage_token` exists

## Configuration Parameters (52 Total)

### Categories:
1. **elo** (6): K-factors, starting values, thresholds
2. **metagame** (5): Cluster multipliers [4.0, 2.5, 1.5, 1.0], tier weights [60%, 25%, 15%]
3. **earning** (11): All ticket earning mechanisms from CSV
4. **shop** (15): All shop items and costs
5. **system** (8): Operational parameters
6. **rate_limits** (5): DoS protection settings
7. **game_mechanics** (2): VIG percentage, other mechanics

## Appendix: Code Examples

Code examples and detailed implementations have been moved to separate documentation files to keep this plan focused and readable. See:
- `docs/wallet_service.md` - WalletService implementation details
- `docs/game_mechanics.md` - Hidden effect system and leverage
- `docs/configuration.md` - Configuration service with 52 parameters
- `docs/betting_system.md` - Pari-mutuel betting implementation

---

*End of Implementation Plan C (Phase-Based)*