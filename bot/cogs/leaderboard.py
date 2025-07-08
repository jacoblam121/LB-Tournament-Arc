import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
from bot.services.leaderboard import LeaderboardService
from bot.views.leaderboard import LeaderboardView
from bot.services.rate_limiter import rate_limit
from bot.utils.error_embeds import ErrorEmbeds
import logging

logger = logging.getLogger(__name__)

class LeaderboardCog(commands.Cog):
    """Enhanced leaderboard and ranking commands for Phase 2.3"""
    
    def __init__(self, bot):
        self.bot = bot
        self.leaderboard_service = LeaderboardService(bot.db.session_factory, bot.config_service)
    
    @app_commands.command(name="leaderboard", description="View overall tournament leaderboard")
    @rate_limit("leaderboard", limit=5, window=60)
    async def leaderboard(
        self, 
        interaction: discord.Interaction
    ):
        """Display overall tournament leaderboard."""
        await interaction.response.defer()
        
        try:
            # Get first page of overall leaderboard
            leaderboard_data = await self.leaderboard_service.get_page(
                leaderboard_type="overall",
                sort_by="final_score",
                cluster_name=None,
                event_name=None,
                page=1,
                page_size=10
            )
            
            # Build embed
            embed = self._build_leaderboard_embed(leaderboard_data)
            
            # Create paginated view
            view = LeaderboardView(
                leaderboard_service=self.leaderboard_service,
                leaderboard_type="overall",
                sort_by="final_score",
                cluster_name=None,
                event_name=None,
                current_page=1,
                total_pages=leaderboard_data.total_pages
            )
            
            await interaction.followup.send(embed=embed, view=view)
            
        except ValueError as e:
            await interaction.followup.send(embed=ErrorEmbeds.invalid_input(str(e)))
        except Exception as e:
            logger.error(f"Error in leaderboard command: {e}")
            await interaction.followup.send(embed=ErrorEmbeds.command_error("An error occurred while fetching leaderboard data. Please try again later."))
    
    @app_commands.command(name="leaderboard-cluster", description="View cluster-specific leaderboard")
    @app_commands.describe(cluster="Select the cluster to view")
    @rate_limit("leaderboard", limit=5, window=60)
    async def leaderboard_cluster(
        self,
        interaction: discord.Interaction,
        cluster: str
    ):
        """Display cluster-specific leaderboard."""
        await interaction.response.defer()
        
        try:
            # Get first page of cluster leaderboard
            leaderboard_data = await self.leaderboard_service.get_page(
                leaderboard_type="cluster",
                sort_by="raw_elo",
                cluster_name=cluster,
                event_name=None,
                page=1,
                page_size=10
            )
            
            # Build embed
            embed = self._build_leaderboard_embed(leaderboard_data)
            
            # Create paginated view
            view = LeaderboardView(
                leaderboard_service=self.leaderboard_service,
                leaderboard_type="cluster",
                sort_by="raw_elo",
                cluster_name=cluster,
                event_name=None,
                current_page=1,
                total_pages=leaderboard_data.total_pages
            )
            
            await interaction.followup.send(embed=embed, view=view)
            
        except ValueError as e:
            await interaction.followup.send(embed=ErrorEmbeds.invalid_input(str(e)))
        except Exception as e:
            logger.error(f"Error in cluster leaderboard command: {e}")
            await interaction.followup.send(embed=ErrorEmbeds.command_error("An error occurred while fetching cluster leaderboard data. Please try again later."))

    @app_commands.command(name="leaderboard-event", description="View event-specific leaderboard")
    @app_commands.describe(event="Select the event to view")
    @rate_limit("leaderboard", limit=5, window=60)
    async def leaderboard_event(
        self,
        interaction: discord.Interaction,
        event: str
    ):
        """Display event-specific leaderboard."""
        await interaction.response.defer()
        
        try:
            # Get first page of event leaderboard
            leaderboard_data = await self.leaderboard_service.get_page(
                leaderboard_type="event",
                sort_by="raw_elo",
                cluster_name=None,
                event_name=event,
                page=1,
                page_size=10
            )
            
            # Build embed
            embed = self._build_leaderboard_embed(leaderboard_data)
            
            # Create paginated view
            view = LeaderboardView(
                leaderboard_service=self.leaderboard_service,
                leaderboard_type="event",
                sort_by="raw_elo",
                cluster_name=None,
                event_name=event,
                current_page=1,
                total_pages=leaderboard_data.total_pages
            )
            
            await interaction.followup.send(embed=embed, view=view)
            
        except ValueError as e:
            await interaction.followup.send(embed=ErrorEmbeds.invalid_input(str(e)))
        except Exception as e:
            logger.error(f"Error in event leaderboard command: {e}")
            await interaction.followup.send(embed=ErrorEmbeds.command_error("An error occurred while fetching event leaderboard data. Please try again later."))

    @leaderboard_cluster.autocomplete('cluster')
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

    @leaderboard_event.autocomplete('event')
    async def event_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Provide event name suggestions."""
        try:
            events = await self.leaderboard_service.get_event_names()
            return [
                app_commands.Choice(name=event, value=event)
                for event in events
                if current.lower() in event.lower()
            ][:25]
        except Exception as e:
            logger.error(f"Error in event autocomplete: {e}")
            return []
    
    def _build_leaderboard_embed(self, leaderboard_data) -> discord.Embed:
        """Build formatted leaderboard embed with Phase 2.3 enhancements."""
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
        
        # Compact table formatting for Discord constraints
        lines = ["```"]
        
        # Different headers based on leaderboard type
        if leaderboard_data.leaderboard_type in ("cluster", "event"):
            # Cluster/Event leaderboards show only raw elo
            lines.append(f"{'#':<4} {'Player':<20} {'Raw Elo':<8}")
            lines.append("-" * 35)
        else:
            # Overall leaderboard shows all columns
            lines.append(f"{'#':<4} {'Player':<16} {'Score':<6} {'S.Elo':<6} {'R.Elo':<6} {'Shd':<4} {'Shp':<4}")
            lines.append("-" * 52)
        
        # Table rows with enhanced formatting
        for entry in leaderboard_data.entries:
            # Use regular rank display
            rank_display = entry.rank
            
            if leaderboard_data.leaderboard_type in ("cluster", "event"):
                # Cluster/Event: Show only rank, name, and raw elo
                player_name = entry.display_name[:18]  # More space for names
                lines.append(
                    f"{rank_display:<4} {player_name:<20} {entry.overall_raw_elo:<8.1f}"
                )
            else:
                # Overall: Show all columns
                lines.append(
                    f"{rank_display:<4} {entry.display_name[:14]:<16} "
                    f"{entry.final_score:<6} {entry.overall_scoring_elo:<6} "
                    f"{entry.overall_raw_elo:<6} {entry.shard_bonus:<4} "
                    f"{entry.shop_bonus:<4}"
                )
        
        lines.append("```")
        embed.description += "\n" + "\n".join(lines)
        
        # Enhanced footer with additional info
        embed.set_footer(
            text=f"Page {leaderboard_data.current_page}/{leaderboard_data.total_pages} | "
                 f"Total Players: {leaderboard_data.total_players} | "
                 f"Phase 2.3 Enhanced"
        )
        
        return embed
    
    @commands.command(name='ranks')
    async def show_ranks(self, ctx):
        """Show ranking system info (legacy command)"""
        embed = discord.Embed(
            title="📈 Ranking System - Phase 2.3",
            description="Use `/leaderboard` for enhanced leaderboards with sorting and pagination!\n\n"
                       "**Available Features:**\n"
                       "• Multiple sort options (Final Score, Elo, Bonuses)\n"
                       "• Cluster and event-specific leaderboards\n"
                       "• Interactive pagination\n"
                       "• Real-time ranking with CTE optimization",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Quick Commands",
            value="`/leaderboard` - View overall rankings\n"
                  "`/leaderboard type:cluster` - View cluster rankings\n"
                  "`/leaderboard sort:raw_elo` - Sort by raw Elo",
            inline=False
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(LeaderboardCog(bot))