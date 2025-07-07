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
    
    def _build_profile_embed(self, profile_data, target_member: discord.Member) -> discord.Embed:
        """Build the main profile embed with all stats."""
        # Create main embed
        embed = discord.Embed(
            title=f"🏆 Tournament Profile: {profile_data.display_name}",
            color=profile_data.profile_color or discord.Color.blue()
        )
        
        # Add user avatar
        if target_member:
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
        streak_text = f" ({profile_data.current_streak})" if profile_data.current_streak else ""
        embed.add_field(
            name="⚔️ Match History",
            value=(
                f"**Total Matches:** {profile_data.total_matches}\n"
                f"**Wins:** {profile_data.wins} | **Losses:** {profile_data.losses}\n"
                f"**Win Rate:** {profile_data.win_rate:.1%}{streak_text}"
            ),
            inline=True
        )
        
        # Tickets section
        embed.add_field(
            name="🎫 Tickets",
            value=f"**Balance:** {profile_data.ticket_balance:,}",
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
                inline=True
            )
        
        # Bottom clusters (Areas for Improvement)
        if profile_data.bottom_clusters:
            # Calculate proper ranking for bottom clusters
            total_clusters = len(profile_data.all_clusters)
            bottom_clusters_to_show = profile_data.bottom_clusters[-3:]  # Last 3 clusters
            bottom_cluster_text = "\n".join([
                f"{total_clusters - len(bottom_clusters_to_show) + i + 1}. {cluster.cluster_name}: {cluster.scoring_elo} elo"
                for i, cluster in enumerate(bottom_clusters_to_show)
            ])
            embed.add_field(
                name="💀 Areas for Improvement",
                value=bottom_cluster_text,
                inline=True
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
        """Build the initial leaderboard embed."""
        title = f"{leaderboard_data.leaderboard_type.title()} Leaderboard"
        if leaderboard_data.cluster_name:
            title += f" - {leaderboard_data.cluster_name}"
        if leaderboard_data.event_name:
            title += f" - {leaderboard_data.event_name}"
        
        embed = discord.Embed(
            title=title,
            description=f"Sorted by: **{leaderboard_data.sort_by.replace('_', ' ').title()}**",
            color=discord.Color.gold()
        )
        
        if not leaderboard_data.entries:
            embed.description += "\n\nThe leaderboard is empty for this category."
            return embed
        
        # Table header
        lines = ["```"]
        lines.append(f"{'Rank':<6} {'Player':<20} {'Score':<8} {'S.Elo':<8} {'R.Elo':<8}")
        lines.append("-" * 60)
        
        # Table rows
        for entry in leaderboard_data.entries:
            skull = "💀" if entry.overall_raw_elo < 1000 else "  "
            player_name = entry.display_name[:18]  # Truncate long names
            
            lines.append(
                f"{entry.rank:<6} {player_name:<20} "
                f"{entry.final_score:<8} {entry.overall_scoring_elo:<8} "
                f"{skull}{entry.overall_raw_elo:<6}"
            )
        
        lines.append("```")
        embed.description += "\n" + "\n".join(lines)
        
        # Footer with pagination info
        embed.set_footer(
            text=f"Page {leaderboard_data.current_page}/{leaderboard_data.total_pages} | Total Players: {leaderboard_data.total_players}"
        )
        
        return embed
    
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