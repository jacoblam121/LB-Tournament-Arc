"""
LeaderboardCommands cog for Phase 3.2 - Score Submission System

Provides score submission functionality for leaderboard events.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import logging

from bot.services.leaderboard import LeaderboardService
from bot.database.models import Event, Cluster, ScoreDirection
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from bot.utils.error_embeds import ErrorEmbeds
from bot.utils.leaderboard_exceptions import (
    EventNotFoundError, InvalidEventError, ScoreValidationError,
    DatabaseError, GuildSecurityError, TransactionError
)
from bot.config import Config
from bot.utils.time_parser import parse_time_to_seconds, format_seconds_to_time

logger = logging.getLogger(__name__)

class LeaderboardCommands(commands.Cog):
    """Score submission commands for leaderboard events."""
    
    def __init__(self, bot):
        self.bot = bot
        self.leaderboard_service = LeaderboardService(bot.db.session_factory, bot.config_service)
    
    @app_commands.command(name="submit-event-score", description="Submit a score for a leaderboard event")
    @app_commands.describe(
        cluster="Select the tournament cluster",
        event="Select the leaderboard event",
        score="Your score (e.g., 12345 or for time events: 8:30 or 1:23:45)"
    )
    @app_commands.checks.cooldown(rate=1, per=60.0, key=lambda i: i.user.id)
    async def submit_event_score(self, interaction: discord.Interaction, cluster: str, event: str, score: str):
        """Submit a score for a leaderboard event."""
        # Defer immediately to secure interaction
        await interaction.response.defer()
        
        try:
            # Guild security check
            if not interaction.guild:
                raise GuildSecurityError()
            
            # Validate and convert cluster ID
            try:
                cluster_id = int(cluster)
            except ValueError:
                raise InvalidEventError(f"Invalid cluster selection: {cluster}")
            
            # Get event with guild and cluster context first (need score_direction for parsing)
            event_obj = await self._get_event_by_name(event, interaction.guild.id, cluster_id)
            
            if not event_obj:
                raise EventNotFoundError(event)
                
            if not event_obj.score_direction:
                raise InvalidEventError(event)
            
            # Parse score based on event type
            try:
                if event_obj.score_direction == ScoreDirection.LOW and ':' in score:
                    # Parse time format for LOW events
                    parsed_score = parse_time_to_seconds(score)
                else:
                    # Parse as regular number
                    parsed_score = float(score)
            except ValueError as e:
                raise ScoreValidationError(score, "Invalid score format. Use a number or time format (MM:SS or HH:MM:SS)")
            
            # Enhanced validation on parsed score
            max_score_limit = self.leaderboard_service.config_service.get('leaderboard_system.max_score_limit', 1000000000)
            if not (0 < parsed_score < max_score_limit):
                raise ScoreValidationError(parsed_score, f"Score must be between 0 and {max_score_limit:,}!")
            
            # Check for NaN or infinite values
            if not (isinstance(parsed_score, (int, float)) and parsed_score == parsed_score and parsed_score != float('inf') and parsed_score != float('-inf')):
                raise ScoreValidationError(parsed_score, "Invalid score value!")
                
            # Submit score with retry logic (pass guild context)
            result = await self.leaderboard_service.submit_score(
                interaction.user.id, interaction.user.display_name, 
                event_obj.id, parsed_score, interaction.guild.id
            )
            
            # Format score display based on event type
            def format_score_display(score_value):
                if event_obj.score_direction == ScoreDirection.LOW:
                    return format_seconds_to_time(score_value)
                else:
                    return f"{score_value:g} points"
            
            def format_improvement(new_score, old_score):
                if event_obj.score_direction == ScoreDirection.LOW:
                    # For time events, improvement means reduction
                    diff = old_score - new_score
                    if diff > 0:
                        return f"-{format_seconds_to_time(diff)} faster"
                    else:
                        return f"+{format_seconds_to_time(-diff)} slower"
                else:
                    # For point events, improvement means increase
                    diff = new_score - old_score
                    return f"+{diff:g} points"
            
            # Enhanced response message
            if result['is_personal_best']:
                embed = discord.Embed(
                    title="🎉 New Personal Best!",
                    description=f"**{format_score_display(parsed_score)}**",
                    color=0x00ff00
                )
                if result['previous_best']:
                    embed.add_field(
                        name="Previous Best",
                        value=format_score_display(result['previous_best']),
                        inline=True
                    )
                    embed.add_field(
                        name="Improvement",
                        value=format_improvement(parsed_score, result['previous_best']),
                        inline=True
                    )
            else:
                embed = discord.Embed(
                    title="Score Submitted",
                    description=f"**{format_score_display(parsed_score)}**",
                    color=0x0099ff
                )
                embed.add_field(
                    name="Personal Best",
                    value=format_score_display(result['personal_best']),
                    inline=True
                )
                
            # Get cluster name safely
            cluster_name = getattr(event_obj.cluster, 'name', 'Unknown') if event_obj.cluster else 'Unknown'
            embed.add_field(
                name="Event",
                value=f"{cluster_name}: {event_obj.name}",
                inline=True
            )
            
            await interaction.followup.send(embed=embed)
            
        except (EventNotFoundError, InvalidEventError, ScoreValidationError, GuildSecurityError) as e:
            # User-friendly errors that should be shown to the user
            await interaction.followup.send(e.user_message, ephemeral=True)
            
        except TransactionError as e:
            # Transaction-specific errors
            logger.error(f"Transaction error for user {interaction.user.id}: {e}")
            await interaction.followup.send(e.user_message, ephemeral=True)
            
        except DatabaseError as e:
            # Database-related errors
            logger.error(f"Database error for user {interaction.user.id}: {e}")
            await interaction.followup.send(e.user_message, ephemeral=True)
            
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected error in score submission for user {interaction.user.id}: {e}")
            await interaction.followup.send(
                "❌ An unexpected error occurred. Please try again later.", 
                ephemeral=True
            )
    
    async def _get_event_by_name(self, event_name: str, guild_id: int, cluster_id: int) -> Optional[Event]:
        """Get event by name with guild and cluster context validation."""
        async with self.leaderboard_service.get_session() as session:
            # Get event with guild and cluster validation (eager load cluster for embed display)
            stmt = select(Event).options(selectinload(Event.cluster)).join(Cluster).where(
                Event.name.ilike(event_name),
                Event.cluster_id == cluster_id,
                # Allow events from clusters with matching guild_id or no guild_id (legacy support)
                (Cluster.guild_id == guild_id) | (Cluster.guild_id.is_(None))
            )
            event = await session.scalar(stmt)
            
            return event
    
    @submit_event_score.error
    async def submit_event_score_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle errors for the submit-event-score command, including cooldown."""
        if isinstance(error, app_commands.CommandOnCooldown):
            # Check if bot owner should bypass cooldown
            if interaction.user.id == Config.OWNER_DISCORD_ID:
                # Retry the command for bot owner
                await self.submit_event_score.callback(self, interaction, 
                                                      interaction.namespace.cluster,
                                                      interaction.namespace.event,
                                                      interaction.namespace.score)
            else:
                # Send cooldown message
                await interaction.response.send_message(
                    f"⏰ You're on cooldown! Please wait {error.retry_after:.0f} seconds before submitting another score.",
                    ephemeral=True
                )
        else:
            # Let other errors propagate
            raise error
    
    @submit_event_score.autocomplete('cluster')
    async def cluster_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete for clusters (guild-specific)."""
        try:
            # Only show clusters if in a guild
            if not interaction.guild:
                return []
            
            # Get active clusters for this guild
            async with self.leaderboard_service.get_session() as session:
                stmt = select(Cluster.id, Cluster.name).where(
                    Cluster.is_active == True,
                    Cluster.name.ilike(f"%{current}%"),
                    # Allow clusters with matching guild_id or no guild_id (legacy support)
                    (Cluster.guild_id == interaction.guild.id) | (Cluster.guild_id.is_(None))
                ).order_by(Cluster.name).limit(25)
                
                result = await session.execute(stmt)
                clusters = result.all()
                
                return [
                    app_commands.Choice(name=cluster.name, value=str(cluster.id))
                    for cluster in clusters
                ]
        except Exception as e:
            logger.error(f"Cluster autocomplete error: {e}")
            return []
    
    @submit_event_score.autocomplete('event')
    async def event_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """Autocomplete for leaderboard events (cluster-specific)."""
        try:
            # Only show events if in a guild
            if not interaction.guild:
                return []
            
            # Get selected cluster from interaction
            cluster_id = interaction.namespace.cluster
            if not cluster_id:
                return [app_commands.Choice(name="<Please select a cluster first>", value="")]
            
            # Validate cluster ID
            try:
                cluster_id_int = int(cluster_id)
            except ValueError:
                logger.error(f"Invalid cluster ID in autocomplete: {cluster_id}")
                return [app_commands.Choice(name="<Invalid cluster selection>", value="")]
            
            # Get events with score_direction (leaderboard events) filtered by cluster
            async with self.leaderboard_service.get_session() as session:
                stmt = select(Event.name).join(Cluster).where(
                    Event.score_direction.isnot(None),
                    Event.cluster_id == cluster_id_int,
                    Event.name.ilike(f"%{current}%"),
                    # Allow events from clusters with matching guild_id or no guild_id (legacy support)
                    (Cluster.guild_id == interaction.guild.id) | (Cluster.guild_id.is_(None))
                ).order_by(Event.name).limit(25)
                
                result = await session.execute(stmt)
                events = result.scalars().all()
                
                return [
                    app_commands.Choice(name=event, value=event)
                    for event in events
                ]
        except Exception as e:
            logger.error(f"Event autocomplete error: {e}")
            return []
    
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle application command errors for this cog."""
        # Handle any command errors specific to this cog
        logger.error(f"App command error in LeaderboardCommands: {error}")
        await interaction.response.send_message(
            "❌ An unexpected error occurred. Please try again later.",
            ephemeral=True
        )

async def setup(bot):
    await bot.add_cog(LeaderboardCommands(bot))