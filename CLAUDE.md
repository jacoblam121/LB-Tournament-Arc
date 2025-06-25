# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LB-Tournament-Arc** is a Discord-based tournament management system with advanced scoring mechanisms. The project supports multiple challenge types (1v1, FFA, Team, Leaderboard), dual scoring systems (traditional Elo vs Performance Points), and strategic bonus systems like Crownslayer.

**Current Status:** Phase 1 Complete (Foundation) → Transitioning to Phase 2 (Multi-Type Challenges + Advanced Systems)

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Testing
```bash
# Run automated foundation tests (13 unit tests)
python tests/test_foundation.py

# Run comprehensive manual test suite (7 integration tests)
python manual_test.py
# or with the convenience script:
./run_manual_tests.sh

# Test specific components in manual suite:
# 1. Configuration System
# 2. Elo Calculations  
# 3. Database Operations
# 4. Challenge System
# 5. Match Simulation
# 6. Player Statistics
# 7. Data Integrity
```

### Running the Bot
```bash
# Ensure environment variables are set:
# DISCORD_TOKEN, DISCORD_GUILD_ID, OWNER_DISCORD_ID
python -m bot.main
```

### Database Management
```bash
# The bot automatically initializes SQLite database
# Development DB: tournament.db
# Test DB: manual_test_tournament.db (auto-cleanup)
```

## Architecture & Code Structure

### Core Architecture Layers
```
Tournament Bot
├── Discord Integration (bot/main.py, bot/cogs/)
├── Business Logic (bot/utils/)
├── Data Access (bot/database/)
└── Configuration (bot/config.py)
```

### Database Architecture
The system uses **SQLAlchemy async ORM** with a hierarchical tournament structure:
```
Cluster (Tournament Categories)
  └── Event (Individual Competitions) 
      └── Challenge (1v1 Matches - Legacy)
          └── Player (Participants)
```

**Critical Constraint:** The Challenge model is limited to 2 players (challenger_id, challenged_id) and needs refactoring to support N-player events.

### Scoring Systems
1. **Traditional Elo** - For competitive events (1v1, FFA, Team) with K-factors (Provisional: 40, Standard: 20)
2. **Performance Points (PP)** - For leaderboard events with no point loss to encourage participation
3. **Crownslayer Bonus** - Special rewards for defeating the server owner

### Key Models & Relationships
- **Player**: Discord users with Elo ratings, tickets, match statistics
- **Event**: Competition categories with scoring_type field ("1v1", "FFA", "Team", "Leaderboard")
- **Challenge**: 1v1 match invitations (LEGACY - being refactored for N-player support)
- **EloHistory**: Tracks all rating changes with context
- **Ticket**: Transaction log for the ticket economy

### Configuration System
Environment-based config in `bot/config.py`:
- Discord integration settings (token, guild, owner)
- Tournament mechanics (Elo K-factors, starting values)
- Database connection
- Feature flags and limits

## Development Guidelines

### Testing Philosophy
- **Foundation Tests** (tests/test_foundation.py): Unit tests for individual components
- **Manual Test Suite** (manual_test.py): Integration tests with realistic scenarios
- **Target Coverage**: Both suites must pass (20/20 tests) before phase transitions

### Database Changes
- All models use async SQLAlchemy with proper relationships
- Enum types (ChallengeStatus, MatchResult) must use SQLEnum wrapper
- Foreign key constraints are enforced
- Migration scripts required for schema changes

### Discord Integration Patterns
- Cogs organize commands by domain (player, challenge, leaderboard, etc.)
- Embed-based responses with color coding
- Global error handling in main.py
- Proper permission checks and cooldowns

### Elo Calculation Rules
- Use EloCalculator utility class for all rating changes
- Always record changes in EloHistory table
- Provisional players (< 5 matches) use higher K-factor
- Multi-player Elo requires specialized algorithms (FFA = N*(N-1)/2 pairwise)

## Current Development Priorities

### Phase 2A: Core Infrastructure (CRITICAL)
1. **Resolve Game vs Event Model Duplication** - Deprecate Game model, migrate to Event-based system
2. **Challenge Model Refactor** - Separate invitation workflow from N-player results using Match/MatchParticipant tables
3. **Scoring Strategy Pattern** - Abstract base class for different scoring algorithms

### Phase 2B: Multi-Type Challenges (HIGH)
- Extend command structure: `/challenge 1v1`, `/challenge ffa`, `/challenge team`
- Implement placement-based result recording
- Add multi-player Elo calculations

### Technical Debt & Risks
- **High Risk**: Challenge model refactor is a breaking change requiring careful migration
- **Performance**: FFA Elo calculations have O(N²) complexity
- **Architecture**: Missing abstraction layers for scoring strategies

## Role & Mindset

- You are a highly skilled software engineer, not just a code generator.
- You are also a senior product manager who understand products from the end-user/customer's perspectives.
- Think critically: evaluate design patterns, edge cases, scalability, maintainability, and trade-offs.
- Treat security as a top priority; prevent vulnerabilities like SQL injection, command injection, insecure deserialization, and excessive privilege.
- If a feature becomes too diffcult to implement or reason, break down features into smaller, testable parts.
- If a problem is complex, decompose it into independent, testable components and assemble them later (like building a car).
- Be opinionated: call out smells, anti-patterns, and risks. Justify your stance.
- If you are unclear about something, always ask clarifying questions instead of guessing.

### A few other principles to follow

- KISS: Keep it simple, stupid.
- DRY: Don't repeat yourself.
- Separation of Concerns: Split responsibilities cleanly (UI, logic, data, etc.).
- Fail Fast: Test early and detect problems early. Don't spill out 500 lines of code and find out they're broken afterward.
- Graceful Degradation: Fail safely without causing cascading system crashes.
- Observability First: Prioritize logs, metrics, tracing, and monitoring. Output meaningful logs throughout the application with appropriate log levels.