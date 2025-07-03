# LB-Tournament-Arc Implementation Plan C (Concise Overview)

## Executive Summary

Production-ready implementation roadmap for the Discord tournament bot prioritizing architectural soundness, security, and incremental value delivery through 7 phases.

**Key Principles:**
- Service Layer Architecture with separation of concerns
- Transaction Safety with atomic operations
- Security First with RBAC and rate limiting
- Manual weekly resets for leaderboard events (user preference)

## Current State

### Implemented
- Core match flow (/challenge, /accept, /report)
- Per-event Elo tracking with dual-track system
- Database models for most features
- Basic scoring strategies (1v1, FFA, Team)
- Modal UI infrastructure
- Elo Hierarchy Calculations (fully implemented)

### L Missing Critical Systems
1. **Leaderboard Events** - No Z-score conversion or weekly processing
2. **Ticket Economy** - Models exist but no earning/spending logic
3. **Shard of the Crown** - Not implemented
4. **Leverage System** - Field exists but unused
5. **Betting System** - Not implemented
6. **Admin Tools** - Critical gap for operations

## Implementation Phases

### Phase 1: Foundation & Infrastructure ='
**Goal**: Core architecture, security, and configuration systems

- **Service Layer & Database Safety**: Create service structure, atomic operations, transaction safety patterns, logging, RBAC, rate limiting
- **Configuration Management**: Migrate to database-backed configuration with 52+ parameters across 7 categories (elo, metagame, earning, shop, system, leaderboard_system, rate_limits, game_mechanics)

### Phase 2: Profile System & Basic Leaderboards <�
**Goal**: Modern profile/leaderboard system with interactive UI

- **Interactive Profile**: "Culling Games Passport" with Discord embed layouts, navigation buttons, drill-down views
- **Enhanced Leaderboard**: "Sortable Data Hub" with strategic insights, multiple sorting options, pagination
- **Performance Optimization**: Database indexes, caching, ghost player support

### Phase 3: Leaderboard Events =�
**Goal**: Functional leaderboard events with Z-score conversion

- **Database Models**: LeaderboardScore, score_direction field, personal best tracking
- **Score Submission**: `/submit-score` command with validation and real-time feedback
- **Z-Score Conversion**: Statistical normalization service (ELO_PER_SIGMA = 200)
- **Manual Weekly Processing**: `/admin weekly-reset` with dual-component formula (50% all-time, 50% weekly average)

### Phase 4: Wallet System & Ticket Economy =�
**Goal**: Secure ticket transactions with full earning/spending economy

- **Core Wallet**: O(1) atomic operations, double-entry bookkeeping, idempotency via external_ref
- **Ticket Earning**: All participation/game/leaderboard rewards from CSV integration
- **Shop Implementation**: All items from Ticket System.csv (collusion, chaos, gambling, bounties, leverage, strategy, tournaments, protection)

### Phase 5: Meta-Game Features =Q
**Goal**: Advanced competitive features

- **Shard of the Crown**: 300 Elo bonus pool system with real-time calculation, King tracking, season-end freeze
- **Leverage System**: Standard/forced leverage with toggle workflow, consumption mechanics, dramatic reveals
- **Pari-mutuel Betting**: Complete workflow with VIG (10%), atomic transactions, payout announcements

### Phase 6: Administration Tools & UX Enhancements =�
**Goal**: Operational tools and user experience improvements

- **UX Commands**: Core statistics (/detailed-profile, /head-to-head, /recent-form), advanced analytics, QoL commands
- **Season Management**: `/admin season-end`, `/admin season-archive`, `/admin season-reset` with Final Score formula

### Phase 7: Security Hardening & Production Readiness =�
**Goal**: Production security and deployment preparation

- **Security**: Comprehensive rate limiting, input validation, fraud detection
- **Monitoring**: Logging infrastructure, health monitoring, backup strategy
- **Performance**: Database optimization, response time targets (<1 second), caching
- **Deployment**: Docker containerization, documentation, testing suite

## Key Technical Components

### Service Layer Architecture
```
Discord Commands (Cogs) � Service Layer (Business Logic) � Repository Layer (Data Access) � Database (SQLAlchemy Models)
```

### Core Services
1. **WalletService** - Atomic ticket transactions with double-entry bookkeeping
2. **EloHierarchyService** - Cluster and overall calculations (implemented)
3. **BettingService** - Pari-mutuel pool management with VIG
4. **GameMechanicsService** - Hidden effects and dramatic reveals
5. **LeaderboardService** - Cached leaderboard generation
6. **ConfigurationService** - Dynamic configuration management (52 parameters)

### Database Models (New)
- **ShardPool** - Tracks Shard of the Crown bonus pools per event
- **Bet** - Player bets on matches for pari-mutuel system
- **KingDefeat** - Tracks when players defeat the King
- **LeaderboardScore** - Personal bests for leaderboard events
- **Configuration** - Database-backed configuration with hot reload

### Critical Implementation Details
- **Draw Policy**: "Explicitly not handled" - players must cancel and replay
- **Ghost Player Policy**: Never delete Player records - mark as "(Left Server)"
- **Manual Weekly Reset**: Leaderboard events use manual admin command
- **Betting Window**: Closes instantly when ANY participant uses `/match-report`
- **Leverage Consumption**: Token consumed when holder INITIATES match
- **Shard Bonuses**: Calculated and displayed in real-time, frozen at season end

### Success Metrics
- Zero currency inconsistencies
- All commands respond within 1 second
- 80% user engagement with economy
- <1% transaction error rate
- Complete audit trail coverage

### Final Score Formula
```
Final Score = Overall Scoring Elo + Shard Bonuses + Shop Bonuses
```

---

*This concise overview covers the essential structure and goals of Plan C without implementation details. See planC.md for complete technical specifications.*