# LB-Tournament-Arc Implementation Plan B

## Executive Summary

This document provides a comprehensive implementation roadmap that maintains complete fidelity to planA.md while accounting for the current state of the codebase. The critical architectural changes required:

1. **Remove /ffa command entirely** - It violates the tournament hierarchy by creating ad-hoc events
2. **Implement hierarchical /challenge command** - Proper flow: `/challenge cluster:IO_Games event:Diep type:1v1 players:@user1`
3. **Populate database from CSV** - No features work without proper cluster/event data
4. **Complete transition to per-event Elo** - Global Elo must be deprecated

## Current Implementation State Analysis

### ✅ Completed Components (Verified in Codebase)

#### Phase 0: Security Foundation
- Owner-only permission model implemented
- Centralized permission utilities: `is_bot_owner()` and `is_user_bot_owner()`
- All admin functions restricted to `Config.OWNER_DISCORD_ID`
- Modal UI permission checks fixed

#### Phase 1.1: Database Models
- `PlayerEventStats` model fully implemented (models.py lines 623-681)
- Includes dual-track Elo system (raw_elo, scoring_elo)
- SQLAlchemy event listeners for automatic floor enforcement
- `TicketLedger` model exists (lines 762-793)
- `ChallengeParticipant` model exists (lines 507-541)

#### Phase 1.2: PlayerEventStats Integration
- `complete_match_with_results()` uses PlayerEventStats (match_operations.py)
- `ParticipantResult` includes event_id field
- EloHistory records include event_id
- K-factor calculation based on event-specific matches

#### Phase 1.3: CSV Infrastructure
- `populate_from_csv.py` script exists
- `event_name_parser.py` for complex scoring type parsing
- Support for base_event_name extraction

#### Phase 2.1: Scoring Strategies
- `ScoringStrategy` abstract base class
- `Elo1v1Strategy` for traditional matches
- `EloFfaStrategy` with K/(N-1) scaling
- `PerformancePointsStrategy` for leaderboard events

#### Phase 2A2: Match System
- `Match` model with N-player support
- `MatchParticipant` for individual results
- `MatchOperations` service class
- Bridge functions for Challenge→Match workflow

#### Phase 2.2a: UI Infrastructure
- `PlacementModal` for ≤5 player placement entry
- `MatchConfirmationView` for result approval
- Event browser with pagination (`EventBrowserView`)

### ❌ Missing/Incomplete Components

1. **No Database Data**
   - Clusters/events tables empty
   - CSV data not imported
   - No events to challenge in

2. **/challenge Command**
   - Only placeholder exists (challenge.py)
   - No autocomplete implementation
   - No acceptance workflow

3. **/ffa Creates Ad-hoc Events**
   - Line 1037-1041 in match_commands.py creates events on-the-fly
   - Violates tournament hierarchy
   - Must be removed entirely

4. **Global Elo Still Primary**
   - Player.elo_rating still updated
   - Per-event Elo not fully replacing global
   - Hierarchy calculations not implemented

5. **Meta-game Systems**
   - Ticket economy unused
   - No leverage system
   - No Shard of the Crown
   - No leaderboard events

### 🚨 Critical Discrepancies with planA.md

1. **Architecture Violation**: /ffa bypasses proper hierarchy
   - planA.md line 433: "CRITICAL: Remove `/ffa` command entirely"
   - Current: Creates "FFA N-player by {username}" events dynamically

2. **Out-of-Order Implementation**: 
   - Built: Match system (Phase 2A2)
   - Missing: Challenge system (Phase 2)
   - Result: No proper invitation workflow

3. **Incomplete Model Usage**:
   - ChallengeParticipant exists but unused
   - Challenge model still has 2-player fields
   - Not leveraging N-player architecture

## Phase-by-Phase Implementation Plan

### Phase 1: Foundation Corrections (Week 1)

#### 1.1 Remove /ffa Command Completely

**File**: `bot/cogs/match_commands.py`

**Actions**:
1. Delete entire `create_ffa_match` command (lines 942-1151)
2. Remove any references in command registration
3. Update help documentation

**Rationale**: As stated in planA.md line 433, all FFA matches must go through /challenge workflow to maintain proper tournament hierarchy.

    Phase 1.1 Expansion - Foundation Corrections

    Critical Issues Found:

    1. Architectural Violation: /ffa command creates ad-hoc events dynamically, bypassing the tournament hierarchy
    2. Empty Database: Clusters/events tables have no data - CSV import hasn't been run
    3. Legacy Model Fields: Challenge model still has 2-player fields (challenger_id, challenged_id)
    4. Missing Infrastructure: No challenge operations service, placeholder challenge command

    Detailed Implementation Steps:

    Step 1: Remove /ffa Command (Day 1)

    - Delete entire create_ffa_match command from match_commands.py (lines 942-1151)
    - Delete create_ffa_event function from event operations
    - Add deprecation notice command to guide users

    Step 2: Populate Database (Day 1)

    - Run python populate_from_csv.py to import tournament structure
    - Verify 20 clusters and 60+ events are created
    - Test database queries to ensure data integrity

    Step 3: Database Schema Cleanup (Day 2)

    - Remove legacy Challenge fields (challenger_id, challenged_id)
    - Add performance indexes for frequently queried columns
    - Run migration scripts to clean test data

    Step 4: Prepare Challenge Infrastructure (Day 2-3)

    - Create ChallengeOperations service class
    - Design challenge acceptance UI components
    - Plan autocomplete implementation for cluster/event selection

    This expanded Phase 1.1 will establish the proper foundation for implementing the hierarchical challenge 
    system in Phase 2.

#### 1.2 Populate Database from CSV

**Command**: 
```bash
python populate_from_csv.py
```

**Pre-requisites**:
- Ensure "LB Culling Games List.csv" exists
- Verify database connection in .env
- Check CSV format matches parser expectations

**Expected Results**:
- 20 clusters created
- 60+ events with proper scoring types
- base_event_name fields populated

#### 1.3 Database Schema Updates

**Migration Required**:
```sql
-- Remove legacy Challenge model fields as specified in planA.md lines 493-495
ALTER TABLE challenges DROP COLUMN IF EXISTS challenger_id;
ALTER TABLE challenges DROP COLUMN IF EXISTS challenged_id;

-- Add indexes for performance
CREATE INDEX idx_challenge_participants_challenge ON challenge_participants(challenge_id);
CREATE INDEX idx_challenge_participants_player ON challenge_participants(player_id);
CREATE INDEX idx_challenge_participants_status ON challenge_participants(status);
CREATE INDEX idx_events_base_name ON events(base_event_name);
```

### Phase 2: Implement /challenge Command (Week 2)

#### 2.1 Command Structure Implementation

**File**: `bot/cogs/challenge.py` (complete rewrite)

```python
import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List
from datetime import datetime, timedelta

from bot.database.models import (
    Challenge, ChallengeStatus, ChallengeParticipant,
    ConfirmationStatus, Cluster, Event, Player
)
from bot.database.database import Database
from bot.operations.challenge_operations import ChallengeOperations
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)

class ChallengeCog(commands.Cog):
    """Hierarchical challenge system for all match types"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db
        self.challenge_ops = ChallengeOperations(self.db)
    
    @app_commands.command(
        name="challenge",
        description="Create a match challenge through tournament hierarchy"
    )
    @app_commands.describe(
        cluster="Select tournament cluster",
        event="Select event within cluster",
        match_type="Match format (1v1, Team, FFA)",
        players="Players to challenge (space-separated @mentions)"
    )
    @app_commands.choices(match_type=[
        app_commands.Choice(name="1v1", value="1v1"),
        app_commands.Choice(name="Free for All", value="ffa"),
        app_commands.Choice(name="Team", value="team"),
    ])
    async def challenge(
        self,
        interaction: discord.Interaction,
        cluster: str,  # Will use autocomplete
        event: str,    # Will use autocomplete  
        match_type: str,
        players: str
    ):
        """Create a challenge through proper tournament hierarchy"""
        
        # Implementation continues below...
```

#### 2.2 Autocomplete Implementation

**Critical Feature**: Dynamic filtering as specified in planA.md lines 397-414

```python
@challenge.autocomplete('cluster')
async def cluster_autocomplete(
    self, 
    interaction: discord.Interaction, 
    current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete for cluster selection"""
    try:
        # Get all active clusters
        async with self.db.get_session() as session:
            clusters = await self.db.get_all_clusters(active_only=True, session=session)
        
        # Filter by current input
        if current:
            clusters = [c for c in clusters if current.lower() in c.name.lower()]
        
        # Return max 25 choices (Discord limit)
        return [
            app_commands.Choice(name=c.name, value=str(c.id))
            for c in clusters[:25]
        ]
    except Exception as e:
        logger.error(f"Cluster autocomplete error: {e}")
        return []

@challenge.autocomplete('event')
async def event_autocomplete(
    self,
    interaction: discord.Interaction,
    current: str
) -> List[app_commands.Choice[str]]:
    """Autocomplete for event selection, filtered by chosen cluster"""
    try:
        # Get selected cluster from interaction
        cluster_id = interaction.namespace.cluster
        if not cluster_id:
            return []
        
        async with self.db.get_session() as session:
            # Get events for selected cluster
            events = await self.db.get_events_for_cluster(
                int(cluster_id), 
                active_only=True,
                session=session
            )
        
        # Filter by current input
        if current:
            events = [e for e in events if current.lower() in e.name.lower()]
        
        # Return max 25 choices
        return [
            app_commands.Choice(name=e.name, value=str(e.id))
            for e in events[:25]
        ]
    except Exception as e:
        logger.error(f"Event autocomplete error: {e}")
        return []
```

#### 2.3 Match Type Static Choices

Match types are defined as static choices since they are a fixed, small list. This avoids Discord.py conflicts between `choices` and `autocomplete` decorators:

```python
# Match type choices are defined directly in the @app_commands.choices decorator
# No autocomplete function needed for static options
```

#### 2.4 Challenge Creation Logic

```python
async def challenge(self, interaction: discord.Interaction, ...):
    """Main challenge command implementation with bifurcated flow"""
    
    try:
        # 1. Early validation before any response
        cluster_id = int(cluster)
        event_id = int(event)
        
        # 2. Parse mentioned players
        mentioned_users = await self._parse_players(interaction, players)
        
        # 3. Validate player count for match type
        if not self._validate_player_count(match_type, len(mentioned_users)):
            await interaction.response.send_message(
                embed=self._create_error_embed("Invalid player count for match type"),
                ephemeral=True
            )
            return
        
        # 4. Auto-include challenger if not mentioned
        if interaction.user not in mentioned_users:
            mentioned_users.append(interaction.user)
        
        # BIFURCATED FLOW: Team vs Non-Team
        if match_type == "team":
            # For team matches: Send modal as IMMEDIATE response
            team_modal = TeamFormationModal(
                challenge_cog=self,
                cluster_id=cluster_id,
                event_id=event_id,
                mentioned_users=mentioned_users
            )
            await interaction.response.send_modal(team_modal)
        else:
            # For 1v1/FFA matches: Use traditional defer flow
            await interaction.response.defer()
            
            # Create challenge with participants
            async with self.db.transaction() as session:
                # Get or create Player records
                player_records = await self._ensure_players_exist(mentioned_users, session)
                
                # Create Challenge
                challenge = await self.challenge_ops.create_challenge(
                    event_id=event_id,
                    initiator_id=player_records[interaction.user.id].id,
                    match_format=match_type,
                    session=session
                )
                
                # Create ChallengeParticipant records with initiator auto-accepted
                for discord_user in mentioned_users:
                    player = player_records[discord_user.id]
                    is_initiator = (discord_user.id == interaction.user.id)
                    await self.challenge_ops.add_participant(
                        challenge_id=challenge.id,
                        player_id=player.id,
                        is_initiator=is_initiator,
                        status=ConfirmationStatus.ACCEPTED if is_initiator else ConfirmationStatus.PENDING,
                        session=session
                    )
            
            # Send acceptance UI
            embed, view = self._create_challenge_embed(challenge, mentioned_users)
            await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        logger.error(f"Challenge creation failed: {e}")
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=self._create_error_embed(str(e)),
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                embed=self._create_error_embed(str(e)),
                ephemeral=True
            )
```

#### 2.5 Challenge Acceptance System

```python
class ChallengeAcceptanceView(discord.ui.View):
    """Interactive view for challenge acceptance/rejection"""
    
    def __init__(self, challenge_id: int, challenge_ops: ChallengeOperations):
        super().__init__(timeout=86400)  # 24 hour timeout
        self.challenge_id = challenge_id
        self.challenge_ops = challenge_ops
    
    @discord.ui.button(
        label="Accept", 
        style=discord.ButtonStyle.success,
        custom_id="challenge_accept"
    )
    async def accept_button(
        self, 
        interaction: discord.Interaction, 
        button: discord.ui.Button
    ):
        """Handle challenge acceptance"""
        await interaction.response.defer()
        
        try:
            # Update participant status
            async with self.challenge_ops.db.transaction() as session:
                success = await self.challenge_ops.update_participant_status(
                    challenge_id=self.challenge_id,
                    player_discord_id=interaction.user.id,
                    status=ConfirmationStatus.ACCEPTED,
                    session=session
                )
                
                if not success:
                    await interaction.followup.send(
                        "You are not a participant in this challenge.",
                        ephemeral=True
                    )
                    return
                
                # Check if all accepted
                if await self.challenge_ops.all_participants_accepted(
                    self.challenge_id, 
                    session
                ):
                    # Create match
                    match = await self.challenge_ops.create_match_from_challenge(
                        self.challenge_id,
                        session
                    )
                    
                    # Update embed to show match created
                    embed = self._create_match_ready_embed(match)
                    await interaction.message.edit(embed=embed, view=None)
                else:
                    # Update embed with current status
                    embed = await self._update_status_embed(self.challenge_id)
                    await interaction.message.edit(embed=embed)
            
            await interaction.followup.send(
                "You have accepted the challenge!",
                ephemeral=True
            )
            
        except Exception as e:
            logger.error(f"Challenge acceptance error: {e}")
            await interaction.followup.send(
                "An error occurred processing your response.",
                ephemeral=True
            )

class TeamFormationModal(discord.ui.Modal):
    """
    Modal for assigning players to teams in team-based challenges.
    
    As specified in planA.md lines 423-428, team challenges require clear
    team assignments with all players accepting their team placement.
    
    This modal is self-contained and handles all challenge creation logic
    for team matches in its on_submit method.
    """
    
    def __init__(self, challenge_cog, cluster_id: int, event_id: int, mentioned_users: List[discord.Member]):
        super().__init__(title="Team Formation", timeout=300)
        self.challenge_cog = challenge_cog
        self.cluster_id = cluster_id
        self.event_id = event_id
        self.mentioned_users = mentioned_users
        
        # Create text inputs for team assignment
        # Format: "Team A: @user1 @user2\nTeam B: @user3 @user4"
        player_list = " ".join([f"@{p.display_name}" for p in mentioned_users])
        
        self.team_input = discord.ui.TextInput(
            label="Team Assignments",
            placeholder=f"Team A: {player_list[:50]}...\nTeam B: ...",
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=True
        )
        self.add_item(self.team_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Process team assignments AND create the challenge"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Parse team assignments from input
            team_assignments = self._parse_team_assignments(self.team_input.value)
            
            if not team_assignments:
                await interaction.followup.send(
                    "Invalid team format. Please use: Team A: @user1 @user2",
                    ephemeral=True
                )
                return
            
            # Validate all players are assigned and no duplicates
            assigned_users = set()
            for team_members in team_assignments.values():
                for member in team_members:
                    if member in assigned_users:
                        await interaction.followup.send(
                            f"Player {member.display_name} assigned to multiple teams.",
                            ephemeral=True
                        )
                        return
                    assigned_users.add(member)
            
            if len(assigned_users) != len(self.mentioned_users):
                await interaction.followup.send(
                    "Not all players were assigned to teams. Please check your assignments.",
                    ephemeral=True
                )
                return
            
            # CREATE THE CHALLENGE (moved from main command)
            async with self.challenge_cog.db.transaction() as session:
                # Get or create Player records
                player_records = await self.challenge_cog._ensure_players_exist(self.mentioned_users, session)
                
                # Create Challenge
                challenge = await self.challenge_cog.challenge_ops.create_challenge(
                    event_id=self.event_id,
                    initiator_id=player_records[interaction.user.id].id,
                    match_format="team",
                    session=session
                )
                
                # Create ChallengeParticipant records with team assignments
                for team_name, team_members in team_assignments.items():
                    for member in team_members:
                        player = player_records[member.id]
                        is_initiator = (member.id == interaction.user.id)
                        await self.challenge_cog.challenge_ops.add_participant(
                            challenge_id=challenge.id,
                            player_id=player.id,
                            team_id=team_name,
                            is_initiator=is_initiator,
                            status=ConfirmationStatus.ACCEPTED if is_initiator else ConfirmationStatus.PENDING,
                            session=session
                        )
            
            # Send challenge created notification
            embed, view = self.challenge_cog._create_challenge_embed(challenge, self.mentioned_users)
            await interaction.followup.send(
                "Team challenge created successfully!",
                embed=embed,
                view=view,
                ephemeral=False  # Make public so all participants can see
            )
            
        except Exception as e:
            logger.error(f"Team formation error: {e}")
            await interaction.followup.send(
                "Error processing team assignments and creating challenge.",
                ephemeral=True
            )
    
    def _parse_team_assignments(self, input_text: str) -> Optional[Dict[str, List[discord.Member]]]:
        """
        Parse team assignment text into structured data.
        
        Expected format:
        Team A: @user1 @user2
        Team B: @user3 @user4
        """
        import re
        
        assignments = {}
        player_mentions = {str(p.id): p for p in self.mentioned_users}
        mention_pattern = re.compile(r"<@!?(\d+)>")
        
        for line in input_text.strip().split('\n'):
            if ':' not in line:
                continue
                
            parts = line.split(':', 1)
            if len(parts) != 2:
                continue
                
            team_name = parts[0].strip()
            member_text = parts[1].strip()
            
            # Find user IDs in mentions
            found_ids = mention_pattern.findall(member_text)
            team_members = [player_mentions[uid] for uid in found_ids if uid in player_mentions]
            
            if team_members:
                assignments[team_name] = team_members
        
        # Validate we have at least 2 teams with players
        if len(assignments) < 2 or not all(len(members) > 0 for members in assignments.values()):
            return None
            
        return assignments
    
    async def on_timeout(self):
        """Handle modal timeout"""
        logger.info(f"Team formation modal timed out for user {self.mentioned_users[0].id if self.mentioned_users else 'unknown'}")
```

### Phase 3: Complete Per-Event Elo Transition (Week 3)

#### 3.1 Remove Global Elo Updates

**File**: `bot/database/match_operations.py`

**Changes Required**:
1. Remove all updates to `Player.elo_rating`
2. Ensure only `PlayerEventStats` is modified
3. Update `EloHistory` to always include `event_id`

```python
# In complete_match_with_results()
# REMOVE these lines:
# player.elo_rating = new_elo  
# player.matches_played += 1
# player.wins += 1 (etc)

# KEEP only:
event_stats.raw_elo = new_elo
event_stats.update_scoring_elo()  # Applies floor
event_stats.matches_played += 1
# etc.
```

#### 3.2 Implement Hierarchy Calculations

**New File**: `bot/operations/elo_hierarchy.py`

```python
from typing import List, Dict
from bot.database.models import Player, PlayerEventStats, Cluster, Event

class EloHierarchyCalculator:
    """Calculates cluster and overall Elo from event-level ratings"""
    
    @staticmethod
    async def calculate_cluster_elo(
        player_id: int, 
        cluster_id: int,
        session
    ) -> int:
        """
        Calculate cluster Elo using prestige weighting system.
        
        From planA.md lines 519-557:
        - Best event: 4.0x weight
        - Second best: 2.5x weight  
        - Third best: 1.5x weight
        - Fourth+: 1.0x weight
        """
        # Get all event stats for player in cluster
        event_stats = await session.execute(
            select(PlayerEventStats)
            .join(Event)
            .where(
                PlayerEventStats.player_id == player_id,
                Event.cluster_id == cluster_id
            )
            .order_by(PlayerEventStats.scoring_elo.desc())
        )
        
        stats_list = event_stats.scalars().all()
        if not stats_list:
            return 1000  # Default
        
        # Apply prestige multipliers
        weights = [4.0, 2.5, 1.5]  # First 3 get special weights
        total_weighted = 0
        total_weight = 0
        
        for i, stat in enumerate(stats_list):
            weight = weights[i] if i < len(weights) else 1.0
            total_weighted += stat.scoring_elo * weight
            total_weight += weight
        
        return int(total_weighted / total_weight)
    
    @staticmethod
    async def calculate_overall_elo(player_id: int, session) -> int:
        """
        Calculate overall Elo using tiered weighting.
        
        From planA.md lines 559-577:
        - Top 10 clusters: 60% weight
        - Clusters 11-15: 25% weight
        - Clusters 16-20: 15% weight
        """
        # Implementation continues...
```

#### 3.3 Migration Scripts

```sql
-- Reset all Elo to 1000 as requested
UPDATE players SET elo_rating = 1000;
UPDATE player_event_stats SET raw_elo = 1000, scoring_elo = 1000;

-- Clear test data
DELETE FROM elo_history WHERE event_id IS NULL;
DELETE FROM matches WHERE event_id IN (
    SELECT id FROM events WHERE name LIKE '%FFA%by%'
);
DELETE FROM events WHERE name LIKE '%FFA%by%';
```

### Phase 4: Testing & Validation (Week 4)

#### 4.1 Test Scenarios

1. **Challenge Creation Flow**
   - Test autocomplete filtering
   - Verify participant limits
   - Check duplicate prevention

2. **Acceptance Workflow**  
   - All accept → Match created
   - One rejects → Challenge cancelled
   - Timeout → Auto-expire

3. **Elo Calculations**
   - 1v1: Standard Elo
   - FFA: K/(N-1) scaling
   - Team: Average rating approach

4. **Data Integrity**
   - No orphaned challenges
   - Proper cascade deletes
   - Transaction atomicity

#### 4.2 Performance Testing

```python
# Test autocomplete with large datasets
async def test_autocomplete_performance():
    # Create 100 clusters with 30 events each
    # Measure autocomplete response time
    # Should be <100ms for 25 results
```

## Risk Analysis & Mitigation

### High-Risk Items

1. **Data Loss from /ffa Removal**
   - **Risk**: Historical FFA matches deleted
   - **Mitigation**: Archive before deletion
   - **Query**: `SELECT * FROM matches WHERE event_id IN (SELECT id FROM events WHERE name LIKE '%FFA%by%')`

2. **User Confusion**
   - **Risk**: Users try /ffa, get error
   - **Mitigation**: Grace period with helpful message
   - **Implementation**: Catch command, redirect to /challenge

3. **Incomplete Challenges**
   - **Risk**: Challenges never accepted, clutter database
   - **Mitigation**: 24-hour auto-expiration
   - **Background job**: Clean expired challenges hourly

### Medium-Risk Items

1. **Performance Impact**
   - **Risk**: Autocomplete slow with many events
   - **Mitigation**: Database indexes, result limiting
   - **Monitoring**: Log autocomplete response times

2. **Complex Team Formation**
   - **Risk**: Confusion over team assignment
   - **Mitigation**: Clear UI, color coding
   - **Future**: Team formation modal

## Implementation Checklist

### Week 1: Foundation
- [ ] Remove /ffa command from match_commands.py
- [ ] Run populate_from_csv.py
- [ ] Verify database has clusters/events
- [ ] Add missing indexes

### Week 2: Challenge System  
- [ ] Rewrite challenge.py with full implementation
- [ ] Implement autocomplete functions
- [ ] Create ChallengeOperations service
- [ ] Test acceptance workflow

### Week 3: Elo Completion
- [ ] Remove global Elo updates
- [ ] Implement hierarchy calculations
- [ ] Run migration scripts
- [ ] Verify per-event tracking

### Week 4: Polish
- [ ] Comprehensive testing
- [ ] Performance optimization
- [ ] Documentation updates
- [ ] User announcements

## Appendix A: File Changes Summary

### Files to Modify
1. `bot/cogs/match_commands.py` - Remove /ffa
2. `bot/cogs/challenge.py` - Complete rewrite
3. `bot/database/match_operations.py` - Remove global Elo
4. `bot/database/database.py` - Add helper methods

### Files to Create
1. `bot/operations/challenge_operations.py`
2. `bot/operations/elo_hierarchy.py`
3. `bot/ui/challenge_views.py`

### Files to Delete
- None (preserve for history)

## Appendix B: Database Schema Changes

```sql
-- Indexes for performance
CREATE INDEX idx_clusters_active ON clusters(is_active);
CREATE INDEX idx_events_cluster ON events(cluster_id, is_active);
CREATE INDEX idx_events_base_name ON events(base_event_name);
CREATE INDEX idx_challenge_participants_challenge ON challenge_participants(challenge_id);
CREATE INDEX idx_challenge_participants_player ON challenge_participants(player_id);
CREATE INDEX idx_player_event_stats_event ON player_event_stats(event_id);
CREATE INDEX idx_player_event_stats_player ON player_event_stats(player_id);

-- Cleanup bad data
DELETE FROM events WHERE cluster_id IS NULL;
DELETE FROM matches WHERE event_id NOT IN (SELECT id FROM events);
```

## Appendix C: Configuration Updates

### Environment Variables
```bash
# .env additions
CHALLENGE_EXPIRY_HOURS=24
AUTOCOMPLETE_MAX_RESULTS=25
ELO_CALCULATION_TIMEOUT=30
```

### Config Constants
```python
# bot/config.py additions
class Config:
    # Challenge System
    CHALLENGE_EXPIRY_HOURS = int(os.getenv("CHALLENGE_EXPIRY_HOURS", "24"))
    MIN_FFA_PLAYERS = 3
    MAX_FFA_PLAYERS = 16
    MIN_TEAM_SIZE = 2
    MAX_TEAM_SIZE = 8
```

## Conclusion

This plan provides a clear path to align the implementation with planA.md's vision. The critical changes - removing /ffa and implementing hierarchical /challenge - will establish the proper tournament structure. With the foundation corrected, all subsequent features can build on solid architecture.

The phased approach minimizes risk while ensuring each component is properly tested before moving forward. By Week 4, the system will have proper challenge workflows, per-event Elo tracking, and a maintainable codebase ready for meta-game features.