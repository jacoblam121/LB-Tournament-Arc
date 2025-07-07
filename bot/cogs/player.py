"""
Player management commands for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides modern slash commands for player profiles and leaderboards with interactive UI.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from dataclasses import replace

from bot.database.models import Player
from bot.services.profile import ProfileService, PlayerNotFoundError
from bot.services.leaderboard import LeaderboardService
from bot.views.profile import ProfileView
from bot.views.leaderboard import LeaderboardView
from bot.services.rate_limiter import rate_limit
from bot.utils.embeds import build_profile_embed, build_leaderboard_table_embed
import logging

logger = logging.getLogger(__name__)


class PlayerCog(commands.Cog):
    """Player management commands with modern slash command support."""
    
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
            is_ghost = interaction.guild.get_member(target_member.id) is None if interaction.guild else False
            
            # Fetch profile data through service
            profile_data = await self.profile_service.get_profile_data(target_member.id)
            
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
            embed = discord.Embed(
                title="Player Not Found",
                description=f"{target_member.mention} hasn't joined the tournament yet!\n\nUse `/register` to get started!",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except ValueError as e:
            embed = discord.Embed(
                title="Invalid Input",
                description=str(e),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in profile command: {e}")
            embed = discord.Embed(
                title="Error",
                description="An error occurred while fetching profile data. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    
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
        
        try:
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
            
        except ValueError as e:
            embed = discord.Embed(
                title="Invalid Parameters",
                description=str(e),
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Error in leaderboard command: {e}")
            embed = discord.Embed(
                title="Error",
                description="An error occurred while fetching leaderboard data. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @leaderboard.autocomplete('cluster')
    async def cluster_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Provide cluster name suggestions."""
        try:
            clusters = await self.leaderboard_service.get_cluster_names()
            return [
                app_commands.Choice(name=cluster, value=cluster)
                for cluster in clusters 
                if current.lower() in cluster.lower()
            ][:25]  # Discord limit
        except Exception as e:
            logger.error(f"Error in cluster autocomplete: {e}")
            return []

    @leaderboard.autocomplete('event')
    async def event_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Provide event name suggestions."""
        try:
            # Get cluster context if provided
            cluster = getattr(interaction.namespace, 'cluster', None)
            events = await self.leaderboard_service.get_event_names(cluster)
            return [
                app_commands.Choice(name=event, value=event)
                for event in events
                if current.lower() in event.lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in event autocomplete: {e}")
            return []
    
    def _build_leaderboard_embed(self, leaderboard_data) -> discord.Embed:
        """Build the initial leaderboard embed using shared utility."""
        # Build title suffix for cluster/event specific leaderboards
        title_suffix = ""
        if leaderboard_data.cluster_name:
            title_suffix += f" - {leaderboard_data.cluster_name}"
        if leaderboard_data.event_name:
            title_suffix += f" - {leaderboard_data.event_name}"
        
        return build_leaderboard_table_embed(
            leaderboard_data,
            title_suffix=title_suffix,
            empty_message="The leaderboard is empty for this category."
        )
    
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


async def setup(bot):
    await bot.add_cog(PlayerCog(bot))