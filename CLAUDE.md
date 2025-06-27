# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**LB-Tournament-Arc** is a Discord-based tournament management system with advanced scoring mechanisms. The project supports multiple challenge types (1v1, FFA, Team, Leaderboard), dual scoring systems (traditional Elo vs Performance Points), and strategic bonus systems like Crownslayer.

**Current Status:** 
- Phase 1: ✅ Complete (Foundation)
- Phase 2A1: ✅ Complete (Game→Event migration) 
- Phase 2A2.4: ✅ Complete (Challenge→Match separation infrastructure)
- Phase 2.2a: ✅ Modal Infrastructure (placement entry for ≤5 players)
- Phase B: ✅ Confirmation system infrastructure
- **Active**: Transitioning to full N-player match support

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

# Required environment variables (.env file):
# DISCORD_TOKEN=your_bot_token
# DISCORD_GUILD_ID=your_guild_id  
# OWNER_DISCORD_ID=owner_user_id
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

# Phase-specific test documentation:
# test_phase_*.md files contain detailed test scenarios for each migration phase
```

### Running the Bot
```bash
# Ensure .env file is configured with required variables
python -m bot.main

# The bot uses SQLAlchemy async with SQLite
# Logs are written to logs/tournament_bot_YYYYMMDD.log
```

### Database Management
```bash
# The bot automatically initializes SQLite database
# Development DB: tournament.db
# Test DB: manual_test_tournament.db (auto-cleanup)

# View database structure
sqlite3 tournament.db ".schema"

# Backup before major changes
cp tournament.db tournament_backup_$(date +%Y%m%d).db
```

## Architecture & Code Structure

### Core Architecture Layers
```
Tournament Bot
├── Discord Integration (bot/main.py, bot/cogs/)
│   ├── Hybrid Commands (prefix + slash)
│   ├── Modal Infrastructure (placement entry)
│   └── Embed-based Responses
├── Business Logic (bot/operations/, bot/utils/)
│   ├── Event Operations
│   ├── Player Operations
│   └── Scoring Strategies
├── Data Access (bot/database/)
│   ├── Async SQLAlchemy ORM
│   ├── Transactional Integrity
│   └── Migration Support
└── Configuration (bot/config.py)
```

### Database Architecture
The system uses **SQLAlchemy async ORM** with evolving tournament structure:
```
Cluster (Tournament Categories)
  └── Event (Individual Competitions) 
      ├── Challenge (1v1 Invitations - Legacy)
      └── Match (N-Player Results - NEW)
          └── MatchParticipant (Individual Placements)
      └── Player (Discord Users with Stats)
```

**Architecture Evolution:**
- **Legacy**: Challenge model handles both invitations AND results (2-player only)
- **Current**: Separating invitation workflow (Challenge) from results (Match/MatchParticipant)
- **Future**: Challenge becomes pure invitation system, Match handles all game results

### Scoring Systems
1. **Traditional Elo** - For competitive events (1v1, FFA, Team) with K-factors (Provisional: 40, Standard: 20)
2. **Performance Points (PP)** - For leaderboard events with no point loss to encourage participation
3. **Crownslayer Bonus** - Special rewards for defeating the server owner

### Key Models & Relationships

#### Core Models
- **Player**: Discord users with Elo ratings, tickets, match statistics
- **Event**: Competition categories with scoring_type field ("1v1", "FFA", "Team", "Leaderboard")
- **Challenge**: 1v1 match invitations (LEGACY - limited to 2 players)
- **Match**: N-player game results with flexible participant count (NEW)
- **MatchParticipant**: Individual player results with placement tracking (NEW)

#### Supporting Models
- **EloHistory**: Tracks all rating changes with context
- **Ticket**: Transaction log for the ticket economy
- **MatchResultProposal**: Proposed match results awaiting confirmation
- **MatchConfirmation**: Player confirmations for match results

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
- **Phase Tests** (test_phase_*.md): Detailed test scenarios for each migration phase
- **Target Coverage**: Both suites must pass (20/20 tests) before phase transitions

### Database Changes
- All models use async SQLAlchemy with proper relationships
- Enum types (ChallengeStatus, MatchResult) must use SQLEnum wrapper
- Foreign key constraints are enforced
- Migration scripts required for schema changes
- Always use transactions for multi-table operations
- Additive migrations preserve backward compatibility

### Discord Integration Patterns

#### Command Structure
- **Hybrid Commands**: Support both prefix (`!`) and slash (`/`) commands
- **Member Parsing**: Use `_parse_members_from_string()` helper for robust parsing
- **Modal Infrastructure**: Dynamic modals for placement entry (≤5 players)
- **Confirmation Workflow**: Multi-step confirmation for match results

#### Response Patterns
- Embed-based responses with consistent color coding
- Error embeds with helpful user guidance
- Pagination for large result sets
- Proper permission checks and cooldowns

### Elo Calculation Rules
- Use EloCalculator utility class for all rating changes
- Always record changes in EloHistory table
- Provisional players (< 5 matches) use higher K-factor
- Multi-player Elo: K/(N-1) scaling to prevent excessive volatility
- FFA calculations: N*(N-1)/2 pairwise comparisons

## Current Development Priorities

### Completed Phases
- ✅ **Phase 2A1**: Game→Event migration complete
- ✅ **Phase 2A2.4**: Challenge→Match separation infrastructure
- ✅ **Phase 2.2a**: Modal infrastructure for placement entry
- ✅ **Phase B**: Confirmation system for match results

### Active Development
1. **Complete N-Player Match Support**
   - Finalize match result recording workflow
   - Implement rejection/retry mechanisms
   - Add comprehensive error handling

2. **Command Migration to Hybrid**
   - Convert remaining prefix-only commands
   - Ensure consistent member parsing patterns
   - Update help documentation

3. **Testing & Stabilization**
   - Pass all phase test scenarios
   - Stress test N-player workflows
   - Validate data integrity

### Technical Debt & Risks
- **Managed Risk**: Challenge refactor using additive migration strategy
- **Performance**: FFA Elo calculations scaled by K/(N-1) to control volatility
- **Architecture**: Scoring strategies being abstracted incrementally
- **Data Integrity**: Transactional boundaries critical for multi-table operations

## Critical Implementation Notes

### Hybrid Command Helpers
When implementing Discord commands that accept multiple members:
```python
# Use the _parse_members_from_string helper for robust parsing
async def _parse_members_from_string(self, ctx, input_string: str) -> List[discord.Member]:
    """Parses mentions, IDs, and names (including those with spaces)"""
```

### Transaction Patterns
```python
# Always use transactions for multi-table operations
async with self.session.begin():
    # Create match
    # Create participants
    # Update player stats
    # All succeed or all fail
```

### Migration Strategy
- **Additive Only**: Never remove columns/tables in active use
- **Dual Support**: Maintain both old and new systems during transition
- **Feature Flags**: Use config toggles for gradual rollout
- **Data Integrity**: Foreign keys and constraints are non-negotiable

### Common Pitfalls to Avoid
1. **N+1 Queries**: Use eager loading with SQLAlchemy relationships
2. **Missing Transactions**: Multi-table operations must be atomic
3. **Hardcoded IDs**: Always use config values for guild/owner IDs
4. **Sync in Async**: Never use blocking operations in async code
5. **Modal Limits**: Discord modals support max 5 text inputs

### Dependencies
Core dependencies from requirements.txt:
- `discord.py>=2.3.0` - Discord bot framework
- `SQLAlchemy>=2.0.0` - Async ORM
- `python-dotenv>=1.0.0` - Environment configuration
- `pandas>=2.0.0` - Data analysis for leaderboards