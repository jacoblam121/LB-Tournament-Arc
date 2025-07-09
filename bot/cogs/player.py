"""
Player management commands for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides modern slash commands for player profiles and leaderboards with interactive UI.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from dataclasses import replace
import asyncio

from bot.database.models import Player
from bot.services.profile import ProfileService, PlayerNotFoundError
from bot.services.leaderboard import LeaderboardService
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


async def setup(bot):
    await bot.add_cog(PlayerCog(bot))