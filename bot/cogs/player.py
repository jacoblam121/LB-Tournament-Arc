"""
Player management commands for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides modern slash commands for player profiles and leaderboards with interactive UI.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
from dataclasses import replace
import asyncio
from sqlalchemy import select

from bot.database.models import Player, Event, Cluster
from bot.services.profile import ProfileService, PlayerNotFoundError
from bot.services.leaderboard import LeaderboardService
from bot.services.match_history_service import MatchHistoryService
from bot.views.profile import ProfileView
# NOTE: LeaderboardService restored for ProfileView navigation - services are shared utilities
from bot.utils.embeds import build_profile_embed
from bot.utils.error_embeds import ErrorEmbeds
from bot.operations.elo_hierarchy import EloHierarchyCalculator
from bot.services.elo_hierarchy_cache import CachedEloHierarchyService
from bot.config import Config
import logging

logger = logging.getLogger(__name__)


class PlayerCog(commands.Cog):
    """Player management commands with modern slash command support."""
    
    def __init__(self, bot):
        self.bot = bot
        # Phase 2.4: Initialize EloHierarchyCalculator with caching wrapper
        self.elo_hierarchy_service = CachedEloHierarchyService(bot.db.session_factory, bot.config_service)
        
        # Initialize profile service with hierarchy service
        self.profile_service = ProfileService(
            bot.db.session_factory, 
            bot.config_service,
            self.elo_hierarchy_service
        )
        self.leaderboard_service = LeaderboardService(bot.db.session_factory, bot.config_service)
        # NOTE: leaderboard_service restored - ProfileView needs it for "View on Leaderboard" functionality
        
        # Phase 3.5: Initialize match history service
        self.match_history_service = MatchHistoryService(bot.db.session_factory)
        
    @app_commands.command(name="profile", description="View a player's profile and statistics")
    @app_commands.describe(member="The player whose profile you want to view (defaults to you)")
    @app_commands.checks.cooldown(rate=1, per=15.0, key=lambda i: i.user.id)
    async def profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Display interactive player profile with stats and navigation."""
        # Defer immediately to secure interaction within 3-second window
        await interaction.response.defer()
        
        target_member = member or interaction.user
        
        try:
            # Check if player has left the server (ghost status)
            is_ghost = interaction.guild.get_member(target_member.id) is None if interaction.guild else False
            
            # Fetch profile data with timeout protection
            try:
                profile_data = await asyncio.wait_for(
                    self.profile_service.get_profile_data(target_member.id),
                    timeout=15.0  # 15 second timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"Profile generation for {target_member.id} timed out.")
                await interaction.followup.send(
                    "⏰ Your profile is taking too long to generate. Please try again in a moment.",
                    ephemeral=True
                )
                return
            
            # Update ghost status in profile data if needed
            if is_ghost and not profile_data.is_ghost:
                profile_data = replace(profile_data, 
                                       is_ghost=True, 
                                       display_name=f"{profile_data.display_name} (Left Server)")
            
            # Build main profile embed using shared utility
            embed = build_profile_embed(profile_data, target_member)
            
            # Create interactive view
            view = ProfileView(
                target_user_id=target_member.id,
                profile_service=self.profile_service,
                leaderboard_service=self.leaderboard_service,
                bot=self.bot
            )
            
            await interaction.followup.send(embed=embed, view=view)
            
        except PlayerNotFoundError:
            await interaction.followup.send(embed=ErrorEmbeds.player_not_found(target_member), ephemeral=True)
        except ValueError as e:
            await interaction.followup.send(embed=ErrorEmbeds.invalid_input(str(e)), ephemeral=True)
        except Exception as e:
            logger.error(f"Error in profile command: {e}")
            await interaction.followup.send(embed=ErrorEmbeds.command_error("An error occurred while fetching profile data. Please try again later."), ephemeral=True)
    
    @profile.error
    async def profile_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle errors for the profile command, including cooldown."""
        if isinstance(error, app_commands.CommandOnCooldown):
            # Check if bot owner should bypass cooldown
            if interaction.user.id == Config.OWNER_DISCORD_ID:
                # Retry the command for bot owner
                await self.profile.callback(self, interaction, interaction.namespace.member)
            else:
                # Send cooldown message
                await interaction.response.send_message(
                    f"⏰ Rate limit exceeded. Please wait {error.retry_after:.0f} seconds before using `/profile` again.",
                    ephemeral=True
                )
        else:
            # Let other errors propagate
            raise error
    
    # MOVED: /leaderboard command moved to LeaderboardCog for Phase 2.3 Implementation Coordination
    
    # Legacy prefix commands - keep for backward compatibility during transition
    @commands.command(name='register', aliases=['signup'])
    async def register_player(self, ctx):
        """Register as a new player in the tournament system"""
        
        # Check if player already exists
        existing_player = await self.bot.db.get_player_by_discord_id(ctx.author.id)
        if existing_player:
            embed = discord.Embed(
                title="Already Registered",
                description=f"You're already registered with **{existing_player.elo_rating}** Elo rating.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        # Create new player
        try:
            player = await self.bot.db.create_player(
                discord_id=ctx.author.id,
                username=ctx.author.name,
                display_name=ctx.author.display_name
            )
            
            embed = discord.Embed(
                title="🎮 Registration Successful!",
                description=f"Welcome to the Tournament Arc, {ctx.author.mention}!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Starting Stats",
                value=f"**Elo Rating:** {player.elo_rating}\n"
                      f"**Tickets:** {player.tickets}\n"
                      f"**Matches Played:** {player.matches_played}",
                inline=False
            )
            embed.add_field(
                name="Next Steps",
                value="• Use `/profile` to view your stats\n"
                      "• Use `/leaderboard` to see rankings\n"
                      "• Use `!challenge @player [game]` to start playing!",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            self.bot.logger.error(f"Error registering player {ctx.author.id}: {e}")
            await ctx.send("❌ An error occurred during registration. Please try again.")

    # ========================================================================
    # Phase 3.5: Enhanced Match History Commands
    # ========================================================================
    
    @app_commands.command(name="match-history-player", description="View detailed match history for a player")
    @app_commands.describe(
        player="The player whose match history you want to view (defaults to you)",
        page_size="Number of matches to show per page (max 24, default 6)"
    )
    @app_commands.checks.cooldown(rate=1, per=10.0, key=lambda i: i.user.id)
    async def match_history_player(self, interaction: discord.Interaction, 
                                 player: Optional[discord.Member] = None, 
                                 page_size: Optional[int] = 6):
        """Display paginated match history for a specific player."""
        await interaction.response.defer()
        
        target_user = player or interaction.user
        page_size = max(1, min(page_size or 6, 24))  # Clamp between 1-24
        
        try:
            # Get player from database
            async with self.profile_service.get_session() as session:
                result = await session.execute(
                    select(Player).where(Player.discord_id == target_user.id)
                )
                player_record = result.scalar_one_or_none()
                
                if not player_record:
                    embed = ErrorEmbeds.player_not_found(target_user.display_name)
                    await interaction.followup.send(embed=embed)
                    return
                
                # Get match history
                history_page = await self.match_history_service.get_player_history(
                    player_record.id, page_size=page_size
                )
                
                if not history_page.entries:
                    embed = discord.Embed(
                        title=f"📜 Match History - {target_user.display_name}",
                        description="No match history found.",
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Create match history view
                from bot.views.match_history import MatchHistoryView
                view = MatchHistoryView(
                    self.match_history_service, 
                    player_record.id, 
                    target_user.display_name,
                    page_size,
                    history_page
                )
                
                embed = view.build_embed()
                await interaction.followup.send(embed=embed, view=view)
                
        except Exception as e:
            logger.error(f"Error in match_history_player for {target_user.id}: {e}")
            embed = ErrorEmbeds.command_error("Failed to load match history. Please try again.")
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="match-history-cluster", description="View match history for all players in a cluster")
    @app_commands.describe(
        cluster="The cluster to view history for",
        page_size="Number of matches to show per page (max 20, default 6)"
    )
    @app_commands.checks.cooldown(rate=1, per=15.0, key=lambda i: i.user.id)
    async def match_history_cluster(self, interaction: discord.Interaction, 
                                  cluster: str, 
                                  page_size: Optional[int] = 6):
        """Display paginated match history for all players in a cluster."""
        await interaction.response.defer()
        
        page_size = max(1, min(page_size or 6, 20))  # Clamp between 1-20
        
        try:
            # Get cluster by ID (following challenge command pattern)
            async with self.profile_service.get_session() as session:
                try:
                    cluster_id = int(cluster)
                    cluster_record = await session.get(Cluster, cluster_id)
                except ValueError:
                    cluster_record = None
                
                if not cluster_record or not cluster_record.is_active:
                    embed = discord.Embed(
                        title="❌ Cluster Not Found",
                        description=f"No active cluster found with the specified ID.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Get cluster match history
                history_page = await self.match_history_service.get_cluster_history(
                    cluster_record.id, page_size=page_size
                )
                
                if not history_page.entries:
                    embed = discord.Embed(
                        title=f"📜 Cluster History - {cluster_record.name}",
                        description="No match history found for this cluster.",
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Create cluster history view
                from bot.views.match_history import ClusterHistoryView
                view = ClusterHistoryView(
                    self.match_history_service,
                    cluster_record.id,
                    cluster_record.name,
                    page_size,
                    history_page
                )
                
                embed = view.build_embed()
                await interaction.followup.send(embed=embed, view=view)
                
        except Exception as e:
            logger.error(f"Error in match_history_cluster for {cluster}: {e}")
            embed = ErrorEmbeds.command_error("Failed to load cluster history. Please try again.")
            await interaction.followup.send(embed=embed)
    
    @match_history_cluster.autocomplete('cluster')
    async def cluster_autocomplete_for_cluster_history(
        self, 
        interaction: discord.Interaction, 
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for cluster selection in cluster match history"""
        try:
            # Get active clusters
            async with self.profile_service.get_session() as session:
                from sqlalchemy import select
                stmt = select(Cluster.id, Cluster.name).where(
                    Cluster.is_active == True
                ).order_by(Cluster.name)
                
                if current:
                    stmt = stmt.where(Cluster.name.ilike(f"%{current}%"))
                
                result = await session.execute(stmt.limit(25))
                clusters = result.all()
            
            # Return choices - using cluster ID for robustness (following challenge command pattern)
            return [
                app_commands.Choice(name=name, value=str(cluster_id))
                for cluster_id, name in clusters
            ]
        except Exception as e:
            logger.error(f"Cluster autocomplete error: {e}")
            return []
    
    @app_commands.command(name="match-history-event", description="View match history for all players in an event")
    @app_commands.describe(
        cluster="The cluster name or number",
        event="The event name",
        page_size="Number of matches to show per page (max 20, default 6)"
    )
    @app_commands.checks.cooldown(rate=1, per=15.0, key=lambda i: i.user.id)
    async def match_history_event(self, interaction: discord.Interaction, 
                                cluster: str, 
                                event: str,
                                page_size: Optional[int] = 6):
        """Display paginated match history for all players in an event (auto-sorted by cluster)."""
        await interaction.response.defer()
        
        page_size = max(1, min(page_size or 6, 20))  # Clamp between 1-20
        
        try:
            # Find cluster and event
            async with self.profile_service.get_session() as session:
                # Find cluster
                cluster_query = select(Cluster)
                try:
                    cluster_number = int(cluster)
                    cluster_query = cluster_query.where(Cluster.number == cluster_number)
                except ValueError:
                    cluster_query = cluster_query.where(Cluster.name.ilike(f"%{cluster}%"))
                
                cluster_result = await session.execute(cluster_query)
                cluster_record = cluster_result.scalar_one_or_none()
                
                if not cluster_record:
                    embed = discord.Embed(
                        title="❌ Cluster Not Found",
                        description=f"No cluster found matching '{cluster}'.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Find event in cluster
                event_query = select(Event).where(
                    Event.cluster_id == cluster_record.id,
                    Event.name.ilike(f"%{event}%")
                )
                event_result = await session.execute(event_query)
                event_record = event_result.scalar_one_or_none()
                
                if not event_record:
                    embed = discord.Embed(
                        title="❌ Event Not Found",
                        description=f"No event found matching '{event}' in cluster {cluster_record.name}.",
                        color=discord.Color.red()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Get event match history
                history_page = await self.match_history_service.get_event_history(
                    event_record.id, page_size=page_size
                )
                
                if not history_page.entries:
                    embed = discord.Embed(
                        title=f"📜 Event History - {cluster_record.name}: {event_record.name}",
                        description="No match history found for this event.",
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Create event history view
                from bot.views.match_history import EventHistoryView
                view = EventHistoryView(
                    self.match_history_service,
                    event_record.id,
                    f"{cluster_record.name}: {event_record.name}",
                    page_size,
                    history_page
                )
                
                embed = view.build_embed()
                await interaction.followup.send(embed=embed, view=view)
                
        except Exception as e:
            logger.error(f"Error in match_history_event for {cluster}:{event}: {e}")
            embed = ErrorEmbeds.command_error("Failed to load event history. Please try again.")
            await interaction.followup.send(embed=embed)
    
    @match_history_event.autocomplete('cluster')
    async def cluster_autocomplete_for_event_history(
        self, 
        interaction: discord.Interaction, 
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for cluster selection in event match history"""
        try:
            # Get active clusters
            async with self.profile_service.get_session() as session:
                from sqlalchemy import select
                stmt = select(Cluster).where(
                    Cluster.is_active == True
                ).order_by(Cluster.name)
                
                if current:
                    stmt = stmt.where(Cluster.name.ilike(f"%{current}%"))
                
                result = await session.execute(stmt.limit(25))
                clusters = result.scalars().all()
            
            # Return choices - using cluster name as both name and value for simplicity
            return [
                app_commands.Choice(name=c.name, value=c.name)
                for c in clusters
            ]
        except Exception as e:
            logger.error(f"Cluster autocomplete error: {e}")
            return []

    @match_history_event.autocomplete('event')
    async def event_autocomplete_for_event_history(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for event selection, filtered by chosen cluster"""
        try:
            # Get selected cluster from interaction
            cluster_name = interaction.namespace.cluster
            if not cluster_name:
                return []
            
            # Find cluster first
            async with self.profile_service.get_session() as session:
                from sqlalchemy import select
                
                # Find cluster by name
                cluster_query = select(Cluster).where(Cluster.name.ilike(f"%{cluster_name}%"))
                cluster_result = await session.execute(cluster_query)
                cluster_record = cluster_result.scalar_one_or_none()
                
                if not cluster_record:
                    return []
                
                # Get events for selected cluster
                event_query = select(Event).where(Event.cluster_id == cluster_record.id)
                if current:
                    event_query = event_query.where(Event.name.ilike(f"%{current}%"))
                
                event_result = await session.execute(event_query.limit(25))
                events = event_result.scalars().all()
            
            # Return event choices
            return [
                app_commands.Choice(name=event.name, value=event.name)
                for event in events
            ]
        except Exception as e:
            logger.error(f"Event autocomplete error: {e}")
            return []


async def setup(bot):
    await bot.add_cog(PlayerCog(bot))