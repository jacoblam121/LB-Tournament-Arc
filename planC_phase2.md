# Phase 2: Profile System & Basic Leaderboards - Implementation Plan

## Executive Summary

Phase 2 modernizes the Discord bot's user interface by implementing interactive profiles and leaderboards using Discord's slash commands and UI components. Building on Phase 1's foundation, this phase delivers a rich user experience with real-time data visualization and strategic insights.

**Timeline:** 5-7 days
**Key Deliverables:** Interactive profile system, sortable leaderboards, slash command migration, performance optimization
**Total Implementation:** ~1,100 lines of code

## Core Principles

1. **Progressive Enhancement** - Basic functionality first, then add interactivity
2. **Service Layer Consistency** - Continue Phase 1's BaseService pattern
3. **Performance First** - Efficient queries with proper indexes and caching
4. **User Experience** - Responsive interactions with loading states

---

## Phase 2.1: Complete Profile & Leaderboard Overhaul

### 2.1.1 Slash Command Foundation (~200 lines)

Convert legacy prefix commands to modern slash commands with proper type hints and descriptions.

**✅ COMPLETED - Implementation Notes:**
- Added missing global aggregated fields to Player model: `final_score`, `overall_scoring_elo`, `overall_raw_elo`, `shard_bonus`, `shop_bonus`
- Updated ProfileData class to include `shard_bonus` and `shop_bonus` fields for consistency
- Updated ProfileService to populate all new fields from Player model
- These fields are required for the ProfileService to work correctly
- Fields default to appropriate values (1000 for elo, 0 for scores/bonuses)
- Code review completed with gemini-2.5-pro and o3 - all issues resolved
- Global aggregation logic will be implemented in Phase 2.2+

#### Implementation Steps

1. **Command Migration in player.py**:
```python
# bot/cogs/player.py (modify existing file)
from discord import app_commands
from discord.ext import commands
import discord
from typing import Optional
from dataclasses import replace
from bot.services.profile import ProfileService, PlayerNotFoundError
from bot.services.leaderboard import LeaderboardService
from bot.views.profile import ProfileView
from bot.views.leaderboard import LeaderboardView
from bot.services.rate_limiter import rate_limit
import logging

logger = logging.getLogger(__name__)

class PlayerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.profile_service = ProfileService(bot.db.session_factory, bot.config_service)
        self.leaderboard_service = LeaderboardService(bot.db.session_factory, bot.config_service)
    
    @app_commands.command(name="profile", description="View a player's profile and statistics")
    @app_commands.describe(member="The player whose profile you want to view (defaults to you)")
    @rate_limit("profile", limit=3, window=30)
    async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Display interactive player profile with stats and navigation."""
        # Defer for database operations
        await interaction.response.defer()
        
        target_member = member or interaction.user
        
        try:
            # Check if player has left the server (ghost status)
            is_ghost = interaction.guild.get_member(target_member.id) is None
            
            # Fetch profile data through service
            profile_data = await self.profile_service.get_profile_data(target_member.id)
            
            # Update ghost status in profile data if needed
            if is_ghost and not profile_data.is_ghost:
                profile_data = replace(profile_data, 
                                       is_ghost=True, 
                                       display_name=f"{profile_data.display_name} (Left Server)")
            
            # Build main profile embed
            embed = self._build_profile_embed(profile_data, target_member)
            
            # Create interactive view
            view = ProfileView(
                target_user_id=target_member.id,
                profile_service=self.profile_service,
                bot=self.bot
            )
            
            await interaction.followup.send(embed=embed, view=view)
            
        except PlayerNotFoundError:
            embed = discord.Embed(
                title="Player Not Found",
                description=f"{target_member.mention} hasn't joined the tournament yet!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        except ValueError as e:
            embed = discord.Embed(
                title="Invalid Input",
                description=str(e),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in profile command: {e}")
            embed = discord.Embed(
                title="Error",
                description="An error occurred while fetching profile data. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
    
    def _build_profile_embed(self, profile_data, target_member: discord.Member) -> discord.Embed:
        """Build the main profile embed with all stats."""
        # Create main embed
        embed = discord.Embed(
            title=f"🏆 Tournament Profile: {profile_data.display_name}",
            color=profile_data.profile_color or discord.Color.blue()
        )
        
        # Add user avatar
        embed.set_thumbnail(url=target_member.display_avatar.url)
        
        # Core stats section
        embed.add_field(
            name="📊 Core Statistics",
            value=(
                f"**Final Score:** {profile_data.final_score:,}\n"
                f"**Scoring Elo:** {profile_data.overall_scoring_elo:,}\n"
                f"**Raw Elo:** {profile_data.overall_raw_elo:,}\n"
                f"**Server Rank:** #{profile_data.server_rank:,} / {profile_data.total_players:,}"
            ),
            inline=True
        )
        
        # Match stats section
        streak_text = f" ({profile_data.current_streak} streak)" if profile_data.current_streak else ""
        embed.add_field(
            name="⚔️ Match History",
            value=(
                f"**Total Matches:** {profile_data.total_matches}\n"
                f"**Wins:** {profile_data.wins} | **Losses:** {profile_data.losses} | **Draws:** {profile_data.draws}\n"
                f"**Win Rate:** {profile_data.win_rate:.1%}{streak_text}"
            ),
            inline=True
        )
        
        # Economy section
        embed.add_field(
            name="💰 Economy",
            value=f"**Tickets:** {profile_data.ticket_balance:,}",
            inline=True
        )
        
        # Top clusters preview
        if profile_data.top_clusters:
            top_cluster_text = "\n".join([
                f"{i+1}. {cluster.cluster_name}: {cluster.scoring_elo} elo"
                for i, cluster in enumerate(profile_data.top_clusters[:3])
            ])
            embed.add_field(
                name="🏅 Top Clusters",
                value=top_cluster_text,
                inline=False
            )
        
        # Ghost player warning
        if profile_data.is_ghost:
            embed.add_field(
                name="⚠️ Status",
                value="This player has left the server but their data is preserved.",
                inline=False
            )
        
        embed.set_footer(
            text="Use the buttons below to explore detailed statistics"
        )
        
        return embed
    
    @app_commands.command(name="leaderboard", description="View tournament leaderboards")
    @app_commands.describe(
        type="Type of leaderboard to view",
        cluster="Specific cluster (only for cluster leaderboards)",
        event="Specific event (only for event leaderboards)",
        sort="Column to sort by"
    )
    @rate_limit("leaderboard", limit=5, window=60)
    @app_commands.choices(type=[
        app_commands.Choice(name="Overall", value="overall"),
        app_commands.Choice(name="Cluster", value="cluster"),
        app_commands.Choice(name="Event", value="event")
    ])
    @app_commands.choices(sort=[
        app_commands.Choice(name="Final Score", value="final_score"),
        app_commands.Choice(name="Scoring Elo", value="scoring_elo"),
        app_commands.Choice(name="Raw Elo", value="raw_elo"),
        app_commands.Choice(name="Shard Bonus", value="shard_bonus"),
        app_commands.Choice(name="Shop Bonus", value="shop_bonus")
    ])
    async def leaderboard(
        self, 
        interaction: discord.Interaction,
        type: str = "overall",
        cluster: Optional[str] = None,
        event: Optional[str] = None,
        sort: str = "final_score"
    ):
        """Display sortable, paginated leaderboards."""
        await interaction.response.defer()
        
        # Get first page of leaderboard
        leaderboard_data = await self.leaderboard_service.get_page(
            leaderboard_type=type,
            sort_by=sort,
            cluster_name=cluster,
            event_name=event,
            page=1,
            page_size=10
        )
        
        # Build embed
        embed = self._build_leaderboard_embed(leaderboard_data)
        
        # Create paginated view
        view = LeaderboardView(
            leaderboard_service=self.leaderboard_service,
            leaderboard_type=type,
            sort_by=sort,
            cluster_name=cluster,
            event_name=event,
            current_page=1,
            total_pages=leaderboard_data.total_pages
        )
        
        await interaction.followup.send(embed=embed, view=view)
```

2. **Remove Legacy Commands**:
```python
# Remove or comment out old prefix commands
# @commands.command(name="profile")  # DELETE
# @commands.command(name="leaderboard")  # DELETE
```

3. **Auto-completion for Clusters/Events**:
```python
@leaderboard.autocomplete('cluster')
async def cluster_autocomplete(
    self,
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Provide cluster name suggestions."""
    clusters = await self.leaderboard_service.get_cluster_names()
    return [
        app_commands.Choice(name=cluster, value=cluster)
        for cluster in clusters 
        if current.lower() in cluster.lower()
    ][:25]  # Discord limit

@leaderboard.autocomplete('event')
async def event_autocomplete(
    self,
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Provide event name suggestions."""
    # Get cluster context if provided
    cluster = interaction.namespace.cluster
    events = await self.leaderboard_service.get_event_names(cluster)
    return [
        app_commands.Choice(name=event, value=event)
        for event in events
        if current.lower() in event.lower()
    ][:25]
```

**Testing Checklist:**
- [x] Slash commands appear in Discord UI
- [x] Auto-completion works for clusters/events
- [x] Commands defer properly for long operations
- [x] Error handling for invalid inputs

**Implementation Notes (Phase 2.1.1 Complete):**
- ✅ Created data models: ProfileData, ClusterStats, MatchRecord, LeaderboardEntry, LeaderboardPage
- ✅ Implemented ProfileService with caching and optimized queries using window functions
- ✅ Implemented LeaderboardService with pagination and efficient ranking
- ✅ Created interactive ProfileView and LeaderboardView with navigation buttons
- ✅ Updated PlayerCog with /profile and /leaderboard slash commands
- ✅ Added autocomplete for cluster and event parameters
- ✅ Maintained backward compatibility with legacy !register command
- ✅ Comprehensive error handling and graceful degradation
- ✅ Code review completed with high quality assessment
- ✅ Manual test plan created (Phase_2_1_1_Manual_Test_Plan.md)

**Architecture Highlights:**
- Proper separation of concerns: DTOs, services, views, and cogs
- Efficient database queries with ranking using window functions
- TTL caching with size limits to prevent memory leaks
- Rate limiting integrated with existing system
- Ghost player support with appropriate UI indicators

---

### 2.1.2 Database Schema Migration for Global Fields

**✅ COMPLETED - Critical Fix for Phase 2.1.1**

**Problem:** The profile command was failing with `sqlite3.OperationalError: no such column: players.final_score` because the Player model was updated with new global aggregated fields but the database schema wasn't migrated.

**Root Cause:** SQLite's `Base.metadata.create_all()` only creates new tables but doesn't alter existing tables to add new columns. The 5 new fields added to the Player model required explicit `ALTER TABLE` statements.

**Solution:** Created and executed comprehensive migration script `migration_add_global_aggregated_fields.py`:

#### Migration Script Features:
- **Safety First**: Automatic database backup before migration  
- **Version Checking**: Validates SQLite 3.35.0+ for ALTER TABLE support
- **Idempotent**: Safe to run multiple times, checks existing columns
- **Verification**: Confirms all changes applied correctly to 24 existing players
- **Rollback**: Generates automatic rollback script for emergency recovery

#### Fields Added:
```sql
ALTER TABLE players ADD COLUMN final_score INTEGER DEFAULT 0;
ALTER TABLE players ADD COLUMN overall_scoring_elo INTEGER DEFAULT 1000;
ALTER TABLE players ADD COLUMN overall_raw_elo INTEGER DEFAULT 1000;
ALTER TABLE players ADD COLUMN shard_bonus INTEGER DEFAULT 0;
ALTER TABLE players ADD COLUMN shop_bonus INTEGER DEFAULT 0;
```

#### Code Review Results:
**✅ Reviewed with gemini-2.5-pro and o3**

**Approved for Production** with minor enhancement recommendations:

**MEDIUM Priority:**
- SQL injection prevention: Replace f-string formatting with parameterized queries (lines 105-108, 114-117)
- Exception handling: Improve ProfileService._get_ticket_balance error recovery

**LOW Priority:**
- Performance: Add database index on `final_score` field for leaderboard queries
- Transaction safety: Add explicit transaction boundaries for atomic operations

**Architecture Strengths:**
- Excellent backup and rollback strategies
- Comprehensive logging and verification
- Follows project migration patterns
- Defensive programming in ProfileService with fallback values

**Testing Verified:**
- Profile query executes successfully: `SELECT players.final_score, players.overall_scoring_elo, ...`
- All 24 existing players updated with appropriate defaults
- Database schema now matches Player model definition

---

## Phase 2.2: Interactive Profile Command (~400 lines)

### Profile Data Models
```python
# bot/data_models/profile.py
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass(frozen=True)
class ClusterStats:
    """Stats for a single cluster."""
    cluster_name: str
    cluster_id: int
    scoring_elo: int
    raw_elo: int
    matches_played: int
    rank_in_cluster: int
    is_below_threshold: bool  # For =� emoji

@dataclass(frozen=True)
class MatchRecord:
    """Single match history entry."""
    match_id: int
    opponent_name: str
    opponent_id: int
    result: str  # 'win', 'loss', 'draw'
    elo_change: int
    event_name: str
    played_at: datetime

@dataclass(frozen=True)
class ProfileData:
    """Complete profile data for a player."""
    # Basic info
    player_id: int
    display_name: str
    is_ghost: bool  # Left server
    
    # Core stats
    final_score: int
    overall_scoring_elo: int
    overall_raw_elo: int
    server_rank: int
    total_players: int
    
    # Economy
    ticket_balance: int
    
    # Match stats
    total_matches: int
    wins: int
    losses: int
    draws: int
    win_rate: float
    current_streak: Optional[int]  # None if < 3
    
    # Cluster performance
    top_clusters: List[ClusterStats]  # Top 3
    bottom_clusters: List[ClusterStats]  # Bottom 3
    all_clusters: List[ClusterStats]  # All 20
    
    # Recent activity
    recent_matches: List[MatchRecord]  # Last 5
    
    # Customization
    profile_color: Optional[int]  # Hex color for embed
```

### Profile Service Implementation
```python
# bot/services/profile.py
from typing import Optional, List, Dict
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from bot.services.base import BaseService
from bot.services.rate_limiter import rate_limit
from bot.data_models.profile import ProfileData, ClusterStats, MatchRecord
from bot.database.models import Player, PlayerEventStats, EloHistory, TicketLedger, Cluster, Event
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

class PlayerNotFoundError(Exception):
    """Raised when player doesn't exist in database."""
    pass

class ProfileService(BaseService):
    """Service for aggregating player profile data."""
    
    def __init__(self, session_factory, config_service):
        super().__init__(session_factory)
        self.config_service = config_service
        # TTL cache with size limits to prevent memory leaks
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 300  # 5 minutes
        self._cache_max_size = 1000
    
    async def get_profile_data(self, user_id: int) -> ProfileData:
        """Fetch complete profile data with efficient queries and caching."""
        # Check cache first
        cache_key = f"profile:{user_id}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Cleanup cache periodically
        self._cleanup_cache()
        
        async with self.get_session() as session:
            # Main player query with current stats
            player_query = select(
                Player,
                func.rank().over(order_by=Player.final_score.desc()).label('server_rank'),
                func.count(Player.id).over().label('total_players')
            ).where(Player.discord_id == user_id)
            
            result = await session.execute(player_query)
            player_row = result.first()
            
            if not player_row:
                raise PlayerNotFoundError(f"Player {user_id} not found")
            
            player, server_rank, total_players = player_row
            
            # Ghost status will be determined at command layer
            # Service layer should not access Discord API
            
            # Fetch cluster stats with efficient JOIN
            cluster_stats = await self._fetch_cluster_stats(session, player.id)
            
            # Fetch match history
            recent_matches = await self._fetch_recent_matches(session, player.id)
            
            # Calculate match statistics
            match_stats = await self._calculate_match_stats(session, player.id)
            
            # Get current ticket balance
            ticket_balance = await self._get_ticket_balance(session, player.id)
            
            profile_data = ProfileData(
                player_id=player.id,
                display_name=player.display_name,
                is_ghost=player.is_ghost or False,
                final_score=player.final_score or 0,
                overall_scoring_elo=player.overall_scoring_elo or 1000,
                overall_raw_elo=player.overall_raw_elo or 1000,
                server_rank=server_rank,
                total_players=total_players,
                ticket_balance=ticket_balance,
                total_matches=match_stats['total'],
                wins=match_stats['wins'],
                losses=match_stats['losses'],
                draws=match_stats['draws'],
                win_rate=match_stats['win_rate'],
                current_streak=match_stats['streak'],
                top_clusters=cluster_stats[:3],
                bottom_clusters=cluster_stats[-3:] if len(cluster_stats) > 3 else [],
                all_clusters=cluster_stats,
                recent_matches=recent_matches,
                profile_color=player.profile_color
            )
            
            # Cache the result
            self._cache[cache_key] = profile_data
            self._cache_timestamps[cache_key] = time.time()
            
            return profile_data
    
    async def _fetch_cluster_stats(self, session: AsyncSession, player_id: int) -> List[ClusterStats]:
        """Fetch cluster statistics efficiently."""
        # Use single query with window functions
        query = select(
            Cluster.id,
            Cluster.name,
            PlayerEventStats.scoring_elo,
            PlayerEventStats.raw_elo,
            func.sum(PlayerEventStats.match_count).label('matches'),
            func.rank().over(
                partition_by=Cluster.id,
                order_by=PlayerEventStats.scoring_elo.desc()
            ).label('rank')
        ).select_from(PlayerEventStats).join(
            Event, PlayerEventStats.event_id == Event.id
        ).join(
            Cluster, Event.cluster_id == Cluster.id
        ).where(
            PlayerEventStats.player_id == player_id
        ).group_by(
            Cluster.id, Cluster.name, 
            PlayerEventStats.scoring_elo, 
            PlayerEventStats.raw_elo
        ).order_by(PlayerEventStats.scoring_elo.desc())
        
        result = await session.execute(query)
        
        threshold = self.config_service.get('elo.scoring_elo_threshold', 1000)
        
        return [
            ClusterStats(
                cluster_name=row.name,
                cluster_id=row.id,
                scoring_elo=row.scoring_elo or 1000,
                raw_elo=row.raw_elo or 1000,
                matches_played=row.matches,
                rank_in_cluster=row.rank,
                is_below_threshold=row.raw_elo < threshold
            )
            for row in result
        ]
    
    async def _fetch_recent_matches(self, session: AsyncSession, player_id: int, limit: int = 5) -> List[MatchRecord]:
        """Fetch recent match history."""
        
        # Query recent match history without opponent info (to be added later)
        query = select(
            EloHistory.match_id,
            EloHistory.elo_change,
            EloHistory.created_at,
            Event.name.label('event_name'),
            # Determine result based on elo change (simplified)
            func.case(
                (EloHistory.elo_change > 0, 'win'),
                (EloHistory.elo_change < 0, 'loss'),
                else_='draw'
            ).label('result')
        ).select_from(EloHistory).join(
            Event, EloHistory.event_id == Event.id
        ).where(
            EloHistory.player_id == player_id
        ).order_by(
            EloHistory.created_at.desc()
        ).limit(limit)
        
        result = await session.execute(query)
        
        return [
            MatchRecord(
                match_id=row.match_id,
                opponent_name="Unknown",  # TODO: Fetch from match participants table
                opponent_id=0,           # TODO: Fetch from match participants table
                result=row.result,
                elo_change=row.elo_change,
                event_name=row.event_name,
                played_at=row.created_at
            )
            for row in result
        ]
    
    async def _calculate_match_stats(self, session: AsyncSession, player_id: int) -> dict:
        """Calculate win/loss/draw statistics."""
        try:
            # Get all match results for this player
            query = select(
                func.count().label('total'),
                func.sum(case((EloHistory.elo_change > 0, 1), else_=0)).label('wins'),
                func.sum(case((EloHistory.elo_change < 0, 1), else_=0)).label('losses'),
                func.sum(case((EloHistory.elo_change == 0, 1), else_=0)).label('draws')
            ).where(EloHistory.player_id == player_id)
            
            result = await session.execute(query)
            stats = result.first()
            
            total = stats.total or 0
            wins = stats.wins or 0
            losses = stats.losses or 0
            draws = stats.draws or 0
            
            win_rate = (wins / total) if total > 0 else 0.0
            
            # Calculate current streak (simplified)
            streak_query = select(EloHistory.elo_change).where(
                EloHistory.player_id == player_id
            ).order_by(EloHistory.created_at.desc()).limit(10)
            
            streak_result = await session.execute(streak_query)
            recent_changes = [row[0] for row in streak_result]
            
            current_streak = 0
            if recent_changes:
                # Count consecutive wins/losses
                last_result = 'win' if recent_changes[0] > 0 else 'loss' if recent_changes[0] < 0 else 'draw'
                for change in recent_changes:
                    result_type = 'win' if change > 0 else 'loss' if change < 0 else 'draw'
                    if result_type == last_result:
                        current_streak += 1
                    else:
                        break
                
                # Only return streak if >= 3
                current_streak = current_streak if current_streak >= 3 else None
            
            return {
                'total': total,
                'wins': wins,
                'losses': losses,
                'draws': draws,
                'win_rate': win_rate,
                'streak': current_streak
            }
        except Exception as e:
            logger.error(f"Error calculating match stats for player {player_id}: {e}")
            return {
                'total': 0, 'wins': 0, 'losses': 0, 'draws': 0,
                'win_rate': 0.0, 'streak': None
            }
    
    async def _get_ticket_balance(self, session: AsyncSession, player_id: int) -> int:
        """Get current ticket balance from ledger."""
        try:
            # Sum all ticket transactions for this player
            query = select(
                func.coalesce(func.sum(TicketLedger.amount), 0).label('balance')
            ).where(TicketLedger.player_id == player_id)
            
            result = await session.execute(query)
            balance = result.scalar() or 0
            
            return max(0, balance)  # Ensure non-negative balance
        except Exception as e:
            logger.error(f"Error fetching ticket balance for player {player_id}: {e}")
            return 0
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self._cache_timestamps:
            return False
        return time.time() - self._cache_timestamps[cache_key] < self._cache_ttl
    
    def _cleanup_cache(self):
        """Remove expired cache entries and enforce size limits."""
        current_time = time.time()
        
        # Remove expired entries
        expired_keys = [
            key for key, timestamp in self._cache_timestamps.items()
            if current_time - timestamp >= self._cache_ttl
        ]
        
        for key in expired_keys:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        
        # Enforce size limit by removing oldest entries
        if len(self._cache) > self._cache_max_size:
            # Sort by timestamp and remove oldest entries
            sorted_items = sorted(
                self._cache_timestamps.items(),
                key=lambda x: x[1]
            )
            
            # Remove oldest entries until under size limit
            entries_to_remove = len(self._cache) - self._cache_max_size
            for key, _ in sorted_items[:entries_to_remove]:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
    
    # Note: Ghost status checking moved to command layer per architectural principles
```

### Interactive Profile View
```python
# bot/views/profile.py
import discord
from discord.ui import View, Button, Select
from typing import Optional
from bot.data_models.profile import ProfileData

class ProfileView(View):
    """Interactive view for player profiles."""
    
    def __init__(self, target_user_id: int, profile_service, bot, *, timeout: int = 900):
        super().__init__(timeout=timeout)
        self.target_user_id = target_user_id
        self.profile_service = profile_service
        self.bot = bot
        self.current_view = "main"  # main, clusters, history, tickets
        
        # Add navigation buttons
        self._add_nav_buttons()
    
    def _add_nav_buttons(self):
        """Add navigation buttons based on current view."""
        # Clear existing items
        self.clear_items()
        
        if self.current_view == "main":
            # Main view buttons with proper callback wiring
            clusters_btn = Button(
                label="Clusters Overview",
                emoji="🎯",
                style=discord.ButtonStyle.primary,
                custom_id=f"profile:{self.target_user_id}:clusters"
            )
            clusters_btn.callback = self._clusters_callback
            self.add_item(clusters_btn)
            
            history_btn = Button(
                label="Match History",
                emoji="⚔️",
                style=discord.ButtonStyle.primary,
                custom_id=f"profile:{self.target_user_id}:history"
            )
            history_btn.callback = self._history_callback
            self.add_item(history_btn)
            
            tickets_btn = Button(
                label="Ticket Ledger",
                emoji="🎫",
                style=discord.ButtonStyle.primary,
                custom_id=f"profile:{self.target_user_id}:tickets"
            )
            tickets_btn.callback = self._tickets_callback
            self.add_item(tickets_btn)
            
            leaderboard_btn = Button(
                label="View on Leaderboard",
                emoji="🏆",
                style=discord.ButtonStyle.secondary,
                custom_id=f"profile:{self.target_user_id}:leaderboard"
            )
            leaderboard_btn.callback = self._leaderboard_callback
            self.add_item(leaderboard_btn)
            
            # Cluster dropdown on second row
            self.add_item(ClusterSelect(self.profile_service, self.target_user_id))
        else:
            # Back button for sub-views
            self.add_item(Button(
                label="Back to Profile",
                emoji="⬅️",
                style=discord.ButtonStyle.secondary,
                custom_id=f"profile:{self.target_user_id}:back",
                row=1
            ))
    
    
    async def _clusters_callback(self, interaction: discord.Interaction):
        """Handle clusters button click."""
        await interaction.response.defer()
        await self._show_clusters_view(interaction)
    
    async def _history_callback(self, interaction: discord.Interaction):
        """Handle history button click."""
        await interaction.response.defer()
        await self._show_history_view(interaction)
    
    async def _tickets_callback(self, interaction: discord.Interaction):
        """Handle tickets button click."""
        await interaction.response.defer()
        await self._show_tickets_view(interaction)
    
    async def _leaderboard_callback(self, interaction: discord.Interaction):
        """Handle leaderboard button click."""
        await interaction.response.defer()
        await self._jump_to_leaderboard(interaction)
    
    async def _show_clusters_view(self, interaction: discord.Interaction):
        """Show detailed cluster statistics."""
        self.current_view = "clusters"
        self._add_nav_buttons()
        
        # Fetch fresh data
        profile_data = await self.profile_service.get_profile_data(self.target_user_id)
        
        # Build clusters embed
        embed = discord.Embed(
            title=f"Cluster Overview - {profile_data.display_name}",
            color=profile_data.profile_color or discord.Color.blue()
        )
        
        # Add all 20 clusters with pagination if needed
        for i, cluster in enumerate(profile_data.all_clusters, 1):
            skull = "💀 " if cluster.is_below_threshold else ""
            embed.add_field(
                name=f"{i}. {cluster.cluster_name}",
                value=f"{skull}Scoring: {cluster.scoring_elo} | Raw: {cluster.raw_elo}\n"
                      f"Matches: {cluster.matches_played} | Rank: #{cluster.rank_in_cluster}",
                inline=True
            )
        
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=embed,
            view=self
        )

class ClusterSelect(Select):
    """Dropdown for selecting specific cluster details."""
    
    def __init__(self, profile_service, target_user_id):
        self.profile_service = profile_service
        self.target_user_id = target_user_id
        
        options = [
            discord.SelectOption(
                label="Select a Cluster to view its Events...",
                value="none",
                default=True
            )
        ]
        
        super().__init__(
            placeholder="Choose a cluster for detailed event breakdown",
            options=options,
            custom_id=f"profile:{target_user_id}:cluster_select",
            row=2
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle cluster selection."""
        if self.values[0] == "none":
            return
        
        await interaction.response.defer()
        # Show events within selected cluster
        # Implementation continues...
```

**Testing Checklist:**
- [ ] Profile data aggregates correctly
- [ ] Ghost players show "(Left Server)" tag
- [ ] Interactive buttons navigate properly
- [ ] Cluster dropdown populates dynamically
- [ ] Performance < 2 seconds for profile load

---

## Phase 2.3: Enhanced Leaderboard Features (~300 lines)

### Leaderboard Data Models
```python
# bot/data_models/leaderboard.py
from dataclasses import dataclass
from typing import List, Optional

@dataclass(frozen=True)
class LeaderboardEntry:
    """Single leaderboard row."""
    rank: int
    player_id: int
    display_name: str
    final_score: int
    overall_scoring_elo: int
    overall_raw_elo: int
    shard_bonus: int
    shop_bonus: int
    is_ghost: bool

@dataclass(frozen=True)
class LeaderboardPage:
    """Paginated leaderboard data."""
    entries: List[LeaderboardEntry]
    current_page: int
    total_pages: int
    total_players: int
    sort_by: str
    leaderboard_type: str
    cluster_name: Optional[str] = None
    event_name: Optional[str] = None
```

### Leaderboard Service
```python
# bot/services/leaderboard.py
from typing import Optional, List
from sqlalchemy import select, func, case, and_, text
from bot.services.base import BaseService
from bot.services.rate_limiter import rate_limit
from bot.data_models.leaderboard import LeaderboardPage, LeaderboardEntry
from bot.database.models import Player, Cluster, Event, PlayerEventStats
import time

class LeaderboardService(BaseService):
    """Service for leaderboard queries and ranking with caching."""
    
    def __init__(self, session_factory, config_service):
        super().__init__(session_factory)
        self.config_service = config_service
        # TTL cache for leaderboard pages
        self._cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 180  # 3 minutes for leaderboards
        self._cache_max_size = 500
    
    def _is_cache_valid(self, key: str) -> bool:
        """Check if cached leaderboard data is still valid."""
        if key not in self._cache_timestamps:
            return False
        return time.time() - self._cache_timestamps[key] < self._cache_ttl
    
    def _cleanup_cache(self):
        """Remove expired entries and enforce size limits."""
        current_time = time.time()
        # Remove expired entries
        expired_keys = [
            key for key, timestamp in self._cache_timestamps.items()
            if current_time - timestamp >= self._cache_ttl
        ]
        for key in expired_keys:
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
        
        # Enforce size limit by removing oldest entries
        if len(self._cache) > self._cache_max_size:
            sorted_keys = sorted(
                self._cache_timestamps.items(),
                key=lambda x: x[1]
            )
            keys_to_remove = [key for key, _ in sorted_keys[:len(self._cache) - self._cache_max_size]]
            for key in keys_to_remove:
                self._cache.pop(key, None)
                self._cache_timestamps.pop(key, None)
    
    @rate_limit("leaderboard_page", limit=5, window=60)
    async def get_page(
        self,
        leaderboard_type: str = "overall",
        sort_by: str = "final_score",
        cluster_name: Optional[str] = None,
        event_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
        include_ghosts: bool = False
    ) -> LeaderboardPage:
        """Get paginated leaderboard with efficient ranking query and caching."""
        # Input validation
        if not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        if not isinstance(page_size, int) or page_size < 1 or page_size > 50:
            raise ValueError("page_size must be between 1 and 50")
        if leaderboard_type not in ["overall", "cluster", "event"]:
            raise ValueError("leaderboard_type must be 'overall', 'cluster', or 'event'")
        if sort_by not in ["final_score", "scoring_elo", "raw_elo", "shard_bonus", "shop_bonus"]:
            raise ValueError(f"Invalid sort_by value: {sort_by}")
        
        # Check cache first
        cache_key = f"leaderboard:{leaderboard_type}:{sort_by}:{cluster_name}:{event_name}:{page}:{page_size}:{include_ghosts}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        # Cleanup cache periodically
        self._cleanup_cache()
        async with self.get_session() as session:
            # Build base query with window function for ranking
            base_query = self._build_ranking_query(
                leaderboard_type, sort_by, cluster_name, event_name, include_ghosts
            )
            
            # Count total for pagination
            count_query = select(func.count()).select_from(base_query.subquery())
            total_count = await session.scalar(count_query)
            
            # Apply pagination
            offset = (page - 1) * page_size
            paginated_query = base_query.limit(page_size).offset(offset)
            
            # Execute and map to DTOs
            result = await session.execute(paginated_query)
            entries = [
                LeaderboardEntry(
                    rank=row.rank,
                    player_id=row.player_id,
                    display_name=row.display_name + (" (Left Server)" if row.is_ghost else ""),
                    final_score=row.final_score,
                    overall_scoring_elo=row.overall_scoring_elo,
                    overall_raw_elo=row.overall_raw_elo,
                    shard_bonus=row.shard_bonus or 0,
                    shop_bonus=row.shop_bonus or 0,
                    is_ghost=row.is_ghost
                )
                for row in result
            ]
            
            leaderboard_page = LeaderboardPage(
                entries=entries,
                current_page=page,
                total_pages=(total_count + page_size - 1) // page_size,
                total_players=total_count,
                sort_by=sort_by,
                leaderboard_type=leaderboard_type,
                cluster_name=cluster_name,
                event_name=event_name
            )
            
            # Cache the result
            self._cache[cache_key] = leaderboard_page
            self._cache_timestamps[cache_key] = time.time()
            
            return leaderboard_page
    
    def _build_ranking_query(
        self,
        leaderboard_type: str,
        sort_by: str,
        cluster_name: Optional[str],
        event_name: Optional[str],
        include_ghosts: bool
    ):
        """Build efficient ranking query with window functions."""
        # Map sort columns
        sort_columns = {
            'final_score': Player.final_score,
            'scoring_elo': Player.overall_scoring_elo,
            'raw_elo': Player.overall_raw_elo,
            'shard_bonus': Player.shard_bonus,
            'shop_bonus': Player.shop_bonus
        }
        
        sort_column = sort_columns.get(sort_by, Player.final_score)
        
        # Base query with ranking
        query = select(
            Player.id.label('player_id'),
            Player.display_name,
            Player.final_score,
            Player.overall_scoring_elo,
            Player.overall_raw_elo,
            Player.shard_bonus,
            Player.shop_bonus,
            Player.is_ghost,
            func.rank().over(order_by=sort_column.desc()).label('rank')
        )
        
        # Apply filters based on leaderboard type
        if leaderboard_type == "cluster" and cluster_name:
            # Join with cluster-specific data
            query = query.join(
                PlayerEventStats, Player.id == PlayerEventStats.player_id
            ).join(
                Event, PlayerEventStats.event_id == Event.id
            ).join(
                Cluster, Event.cluster_id == Cluster.id
            ).where(Cluster.name == cluster_name)
            
            # Use cluster-specific scoring for ranking
            query = query.with_only_columns(
                Player.id.label('player_id'),
                Player.display_name,
                Player.final_score,
                PlayerEventStats.scoring_elo.label('overall_scoring_elo'),
                PlayerEventStats.raw_elo.label('overall_raw_elo'),
                Player.shard_bonus,
                Player.shop_bonus,
                Player.is_ghost,
                func.rank().over(order_by=PlayerEventStats.scoring_elo.desc()).label('rank')
            )
            
        elif leaderboard_type == "event" and event_name:
            # Join with event-specific data
            query = query.join(
                PlayerEventStats, Player.id == PlayerEventStats.player_id
            ).join(
                Event, PlayerEventStats.event_id == Event.id
            ).where(Event.name == event_name)
            
            # Use event-specific scoring for ranking
            query = query.with_only_columns(
                Player.id.label('player_id'),
                Player.display_name,
                Player.final_score,
                PlayerEventStats.scoring_elo.label('overall_scoring_elo'),
                PlayerEventStats.raw_elo.label('overall_raw_elo'),
                Player.shard_bonus,
                Player.shop_bonus,
                Player.is_ghost,
                func.rank().over(order_by=PlayerEventStats.scoring_elo.desc()).label('rank')
            )
        
        # Filter ghosts unless specifically included
        if not include_ghosts:
            query = query.where(Player.is_ghost == False)
        
        return query
    
    async def get_player_rank(
        self,
        user_id: int,
        sort_by: str = "final_score"
    ) -> Optional[int]:
        """Get a specific player's rank efficiently."""
        async with self.get_session() as session:
            # Use CTE for rank calculation
            rank_cte = self._build_ranking_query(
                "overall", sort_by, None, None, True
            ).cte('ranks')
            
            query = select(rank_cte.c.rank).where(
                rank_cte.c.player_id == user_id
            )
            
            return await session.scalar(query)
```

### Interactive Leaderboard View
```python
# bot/views/leaderboard.py
import discord
from discord.ui import View, Button, Select
from bot.data_models.leaderboard import LeaderboardPage

class LeaderboardView(View):
    """Paginated, sortable leaderboard view."""
    
    def __init__(
        self,
        leaderboard_service,
        leaderboard_type: str,
        sort_by: str,
        cluster_name: Optional[str],
        event_name: Optional[str],
        current_page: int,
        total_pages: int,
        *,
        timeout: int = 900
    ):
        super().__init__(timeout=timeout)
        self.leaderboard_service = leaderboard_service
        self.leaderboard_type = leaderboard_type
        self.sort_by = sort_by
        self.cluster_name = cluster_name
        self.event_name = event_name
        self.current_page = current_page
        self.total_pages = total_pages
        
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current page."""
        self.clear_items()
        
        # Previous button
        prev_button = Button(
            label="Previous",
            style=discord.ButtonStyle.primary,
            disabled=self.current_page <= 1,
            custom_id="leaderboard:prev"
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # Page indicator
        self.add_item(Button(
            label=f"Page {self.current_page}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True
        ))
        
        # Next button
        next_button = Button(
            label="Next",
            style=discord.ButtonStyle.primary,
            disabled=self.current_page >= self.total_pages,
            custom_id="leaderboard:next"
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
        
        # Sort dropdown
        self.add_item(SortSelect(self.sort_by))
    
    async def previous_page(self, interaction: discord.Interaction):
        """Navigate to previous page."""
        await interaction.response.defer()
        self.current_page -= 1
        await self._update_leaderboard(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        """Navigate to next page."""
        await interaction.response.defer()
        self.current_page += 1
        await self._update_leaderboard(interaction)
    
    async def _update_leaderboard(self, interaction: discord.Interaction):
        """Fetch and display updated leaderboard page."""
        # Get new page data
        page_data = await self.leaderboard_service.get_page(
            leaderboard_type=self.leaderboard_type,
            sort_by=self.sort_by,
            cluster_name=self.cluster_name,
            event_name=self.event_name,
            page=self.current_page,
            page_size=10
        )
        
        # Build new embed
        embed = self._build_leaderboard_embed(page_data)
        
        # Update buttons
        self._update_buttons()
        
        # Edit message
        await interaction.followup.edit_message(
            message_id=interaction.message.id,
            embed=embed,
            view=self
        )
    
    def _build_leaderboard_embed(self, page_data: LeaderboardPage) -> discord.Embed:
        """Build formatted leaderboard embed."""
        title = f"{page_data.leaderboard_type.title()} Leaderboard"
        if page_data.cluster_name:
            title += f" - {page_data.cluster_name}"
        if page_data.event_name:
            title += f" - {page_data.event_name}"
        
        embed = discord.Embed(
            title=title,
            description=f"Sorted by: **{page_data.sort_by.replace('_', ' ').title()}**",
            color=discord.Color.gold()
        )
        
        # Table header
        lines = ["```"]
        lines.append(f"{'Rank':<6} {'Player':<20} {'Score':<8} {'S.Elo':<8} {'R.Elo':<8} {'Shard':<7} {'Shop':<7}")
        lines.append("-" * 75)
        
        # Table rows
        for entry in page_data.entries:
            skull = "\U0001F480" if entry.overall_raw_elo < 1000 else "  "
            lines.append(
                f"{entry.rank:<6} {entry.display_name[:20]:<20} "
                f"{entry.final_score:<8} {entry.overall_scoring_elo:<8} "
                f"{skull}{entry.overall_raw_elo:<6} {entry.shard_bonus:<7} "
                f"{entry.shop_bonus:<7}"
            )
        
        lines.append("```")
        embed.description += "\n" + "\n".join(lines)
        
        # Footer with user's rank
        embed.set_footer(text=f"Page {page_data.current_page}/{page_data.total_pages} | Total Players: {page_data.total_players}")
        
        return embed

class SortSelect(Select):
    """Dropdown for changing sort order."""
    
    def __init__(self, current_sort: str):
        options = [
            discord.SelectOption(
                label="Final Score",
                value="final_score",
                description="Tournament ranking score",
                default=current_sort == "final_score"
            ),
            discord.SelectOption(
                label="Scoring Elo",
                value="scoring_elo",
                description="Performance-based rating",
                default=current_sort == "scoring_elo"
            ),
            discord.SelectOption(
                label="Raw Elo",
                value="raw_elo",
                description="True skill rating",
                default=current_sort == "raw_elo"
            ),
            discord.SelectOption(
                label="Shard Bonus",
                value="shard_bonus",
                description="King slayer rewards",
                default=current_sort == "shard_bonus"
            ),
            discord.SelectOption(
                label="Shop Bonus",
                value="shop_bonus",
                description="Strategic purchases",
                default=current_sort == "shop_bonus"
            )
        ]
        
        super().__init__(
            placeholder="Sort by...",
            options=options,
            custom_id="leaderboard:sort"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle sort change."""
        # Parent view will handle the actual sorting
        view: LeaderboardView = self.view
        view.sort_by = self.values[0]
        view.current_page = 1  # Reset to first page
        await view._update_leaderboard(interaction)
```

**Testing Checklist:**
- [ ] Ranking query performs efficiently
- [ ] Pagination works correctly at boundaries
- [ ] Sort dropdown updates table properly
- [ ] Ghost players filtered by default
- [ ] User's rank shown in footer

---

## Phase 2.4: EloHierarchyCalculator Integration (~150 lines)

### Integration and Caching
```python
# bot/services/elo_hierarchy_cache.py
import time
from typing import Dict, Optional, Tuple
from bot.operations.elo_hierarchy import EloHierarchyCalculator

class CachedEloHierarchyService:
    """Wrapper for EloHierarchyCalculator with caching."""
    
    def __init__(self, calculator: EloHierarchyCalculator, config_service):
        self.calculator = calculator
        self.config_service = config_service
        self._cache: Dict[int, Tuple[float, Dict]] = {}  # user_id -> (timestamp, data)
    
    async def get_hierarchy(self, user_id: int) -> Dict:
        """Get hierarchy with caching based on TTL."""
        ttl = self.config_service.get('system.cache_ttl_hierarchy', 900)
        
        # Check cache
        if user_id in self._cache:
            timestamp, data = self._cache[user_id]
            if time.time() - timestamp < ttl:
                return data
        
        # Calculate fresh
        hierarchy_data = await self.calculator.calculate_hierarchy(user_id)
        
        # Update cache
        self._cache[user_id] = (time.time(), hierarchy_data)
        
        # Cleanup old entries if cache too large
        max_size = self.config_service.get('system.cache_max_size', 1000)
        if len(self._cache) > max_size:
            self._cleanup_cache()
        
        return hierarchy_data
    
    def invalidate_user(self, user_id: int):
        """Invalidate cache for specific user."""
        self._cache.pop(user_id, None)
    
    def _cleanup_cache(self):
        """Remove oldest cache entries."""
        # Sort by timestamp and keep newest entries
        sorted_items = sorted(self._cache.items(), key=lambda x: x[1][0], reverse=True)
        max_size = self.config_service.get('system.cache_max_size', 1000)
        self._cache = dict(sorted_items[:max_size])
```

### Database Index Migrations
```python
# migrations/add_performance_indexes.py
"""Add indexes for Phase 2 performance optimization."""

async def upgrade(session):
    """Add performance indexes."""
    indexes = [
        # For EloHistory queries
        "CREATE INDEX idx_elo_history_player_recorded ON elo_history(player_id, recorded_at DESC)",
        "CREATE INDEX idx_elo_history_players ON elo_history(player_id, opponent_id)",
        
        # For MatchParticipant queries
        "CREATE INDEX idx_match_participant_match ON match_participant(match_id, placement)",
        
        # For PlayerEventStats queries
        "CREATE INDEX idx_player_event_stats_event ON player_event_stats(event_id, updated_at DESC)",
        
        # For leaderboard sorting
        "CREATE INDEX idx_player_final_score ON players(final_score DESC) WHERE is_ghost = FALSE",
        "CREATE INDEX idx_player_scoring_elo ON players(overall_scoring_elo DESC) WHERE is_ghost = FALSE",
        "CREATE INDEX idx_player_raw_elo ON players(overall_raw_elo DESC) WHERE is_ghost = FALSE"
    ]
    
    for index_sql in indexes:
        await session.execute(text(index_sql))
    
    await session.commit()
```

### Profile Integration Update
```python
# Update bot/cogs/player.py
class PlayerCog(commands.Cog):
    def __init__(self, bot):
        # ... existing init ...
        # Import and wrap calculator
        from bot.operations.elo_hierarchy import EloHierarchyCalculator
        base_calculator = EloHierarchyCalculator(bot.db)
        self.elo_hierarchy_service = CachedEloHierarchyService(
            base_calculator, 
            bot.config_service
        )
    
    def _build_profile_embed(self, profile_data: ProfileData, member: discord.Member) -> discord.Embed:
        """Build main profile embed with hierarchy data."""
        # Determine embed color
        if profile_data.server_rank == 1:
            color = discord.Color.gold()
        else:
            color = profile_data.profile_color or discord.Color.blue()
        
        embed = discord.Embed(
            title=f"Culling Games Profile: {profile_data.display_name}",
            color=color
        )
        
        # Set thumbnail to user avatar
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Main stats row
        embed.add_field(
            name="🏆 Final Score",
            value=f"{profile_data.final_score}",
            inline=True
        )
        embed.add_field(
            name="< Server Rank",
            value=f"#{profile_data.server_rank}/{profile_data.total_players}",
            inline=True
        )
        embed.add_field(
            name="<� Tickets",
            value=f"{profile_data.ticket_balance}",
            inline=True
        )
        
        # Elo ratings row
        embed.add_field(
            name="🎯 Overall Scoring Elo",
            value=f"{profile_data.overall_scoring_elo}",
            inline=True
        )
        embed.add_field(
            name="📈 Overall Raw Elo",
            value=f"{profile_data.overall_raw_elo}",
            inline=True
        )
        embed.add_field(
            name="� Match Record",
            value=f"W:{profile_data.wins} L:{profile_data.losses} D:{profile_data.draws} ({profile_data.win_rate:.1f}%)",
            inline=True
        )
        
        # Current streak if applicable
        if profile_data.current_streak and profile_data.current_streak >= 3:
            embed.add_field(
                name="=% Current Streak",
                value=f"W{profile_data.current_streak}",
                inline=False
            )
        
        # Top clusters
        if profile_data.top_clusters:
            top_text = "\n".join([
                f"{i}. {c.cluster_name} ({c.scoring_elo})"
                for i, c in enumerate(profile_data.top_clusters, 1)
            ])
            embed.add_field(
                name="=Q Top 3 Clusters",
                value=top_text,
                inline=True
            )
        
        # Bottom clusters
        if profile_data.bottom_clusters:
            bottom_text = "\n".join([
                f"{18 + i}. {c.cluster_name} ({c.scoring_elo})"
                for i, c in enumerate(profile_data.bottom_clusters, 1)
            ])
            embed.add_field(
                name="=� Areas for Improvement",
                value=bottom_text,
                inline=True
            )
        
        return embed
```

**Testing Checklist:**
- [ ] EloHierarchyCalculator properly integrated
- [ ] Cache respects TTL configuration
- [ ] Cache invalidation on match results
- [ ] Performance indexes improve query speed
- [ ] Memory usage stays within limits

---

## Phase 2.5: Special Policies & Features (~50 lines)

### Ghost Player Support
```python
# Note: Ghost status checking has been moved to the command layer
# per architectural principles - services should not access Discord API
```

### Draw Policy Implementation
```python
# In match reporting, add validation
if result == "draw":
    embed = discord.Embed(
        title="Draw Not Supported",
        description="Draws are explicitly not handled. Please cancel this match and replay.",
        color=discord.Color.red()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)
    return
```

### Loading States
```python
# Standard pattern for all commands
async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
    # Always defer first for commands that hit database
    await interaction.response.defer()
    
    # For very long operations (> 3 seconds)
    await interaction.followup.send("= Calculating rankings...", ephemeral=True)
    
    # Then edit with final result
    await interaction.edit_original_response(embed=final_embed, view=view)
```

### Error Handling
```python
# Graceful error embeds
class ErrorEmbeds:
    @staticmethod
    def player_not_found(member: discord.Member) -> discord.Embed:
        return discord.Embed(
            title="Player Not Found",
            description=f"{member.mention} hasn't joined the tournament yet!\n\n"
                       f"Use `/challenge` to start playing!",
            color=discord.Color.red()
        )
    
    @staticmethod
    def no_match_history() -> discord.Embed:
        return discord.Embed(
            title="No Match History",
            description="This player hasn't completed any matches yet.",
            color=discord.Color.orange()
        )
    
    @staticmethod
    def command_error(error: str) -> discord.Embed:
        return discord.Embed(
            title="Command Error",
            description=f"An error occurred: {error}\n\n"
                       f"Please try again or contact an administrator.",
            color=discord.Color.red()
        )
```

**Testing Checklist:**
- [ ] Ghost players display properly
- [ ] Draw attempts show error message
- [ ] Loading states prevent timeout
- [ ] Errors show helpful messages
- [ ] All edge cases handled gracefully

---

## Testing Strategy

### Unit Tests (~200 lines)
```python
# tests/test_profile_service.py
import pytest
from bot.services.profile import ProfileService, PlayerNotFoundError

@pytest.mark.asyncio
async def test_profile_aggregation(db_session):
    """Test profile data aggregation efficiency."""
    service = ProfileService(db_session)
    
    # Create test player with stats
    # ...
    
    # Fetch profile
    profile = await service.get_profile_data(user_id=123)
    
    # Verify all fields populated
    assert profile.final_score > 0
    assert len(profile.top_clusters) <= 3
    assert profile.win_rate == profile.wins / profile.total_matches * 100

@pytest.mark.asyncio
async def test_ghost_player_handling(db_session):
    """Test ghost player detection and display."""
    # Test implementation
    pass

# tests/test_leaderboard_service.py
@pytest.mark.asyncio
async def test_ranking_accuracy(db_session):
    """Test window function ranking."""
    service = LeaderboardService(db_session)
    
    # Create players with known scores
    # ...
    
    # Get leaderboard
    page = await service.get_page(sort_by="final_score")
    
    # Verify ranking order
    for i in range(len(page.entries) - 1):
        assert page.entries[i].final_score >= page.entries[i+1].final_score
        assert page.entries[i].rank < page.entries[i+1].rank
```

### Integration Tests
```python
# tests/test_slash_commands.py
@pytest.mark.asyncio
async def test_profile_command_flow(bot, interaction_mock):
    """Test complete profile command flow."""
    # Mock interaction
    interaction = create_interaction_mock(user_id=123)
    
    # Call command
    cog = bot.get_cog("PlayerCog")
    await cog.profile(interaction)
    
    # Verify defer called
    interaction.response.defer.assert_called_once()
    
    # Verify embed sent
    interaction.followup.send.assert_called_once()
    embed = interaction.followup.send.call_args[1]['embed']
    assert "Culling Games Profile" in embed.title
```

### Performance Tests
```python
# tests/test_performance.py
@pytest.mark.asyncio
async def test_leaderboard_query_performance(db_session, benchmark):
    """Benchmark leaderboard query performance."""
    service = LeaderboardService(db_session)
    
    # Create 10,000 test players
    # ...
    
    # Benchmark query
    result = await benchmark(service.get_page, page=50, page_size=10)
    
    # Should complete in under 100ms with indexes
    assert benchmark.stats['mean'] < 0.1
```

---

## Implementation Notes

### Key Performance Optimizations
1. **Single Query Aggregation**: Profile data fetched in one complex query vs N+1
2. **Window Functions**: Database handles ranking, not Python
3. **Indexed Queries**: All sort columns have covering indexes
4. **Smart Caching**: Only cache expensive calculations (hierarchy)
5. **Deferred Responses**: Prevent Discord timeouts on all DB operations

### Security Considerations
1. **Permission Checks**: Inherit from Phase 1's RBAC
2. **Ghost Player Privacy**: No detailed stats for left users
3. **Rate Limiting**: Reuse Phase 1's decorators
4. **Input Validation**: Autocomplete prevents invalid cluster/event names

### Error Recovery
1. **Graceful Degradation**: Missing data shows placeholders
2. **Transaction Rollback**: Inherited from BaseService
3. **User-Friendly Messages**: Clear error embeds
4. **Audit Trail**: Configuration service logs all changes

---

## Timeline & Deliverables

**Total Estimated Time:** 5-7 days

### Day 1-2: Command Migration & Basic Implementation
- [ ] Migrate slash commands (2.1.1)
- [ ] Create data models and DTOs
- [ ] Implement ProfileService
- [ ] Basic profile embed display

### Day 3-4: Interactive Components
- [ ] ProfileView with navigation (2.2)
- [ ] LeaderboardService with pagination
- [ ] LeaderboardView with sorting (2.3)
- [ ] Testing and debugging

### Day 5-6: Integration & Optimization
- [ ] EloHierarchyCalculator integration (2.4)
- [ ] Caching implementation
- [ ] Database indexes
- [ ] Performance testing

### Day 7: Polish & Edge Cases
- [ ] Ghost player handling (2.5)
- [ ] Draw policy
- [ ] Error messages
- [ ] Final testing

---

## Summary

Phase 2 delivers a modern, interactive UI for the tournament bot:

** Complete Implementation:**
- Modern slash commands with auto-completion
- Rich interactive profiles with drill-down views
- Sortable, paginated leaderboards with strategic insights
- Efficient data aggregation with performance optimization
- Comprehensive error handling and edge cases

**<� Key Success Factors:**
- Leverages Phase 1's service architecture
- Uses Discord.py 2.0+ features effectively
- Optimizes database queries from the start
- Provides responsive, intuitive user experience

**=� Metrics:**
- ~1,100 lines of new code
- All responses < 2 seconds
- 5-7 day implementation
- Full test coverage

The implementation follows the same practical approach as Phase 1, delivering production-ready features with clean architecture and room for future enhancements.