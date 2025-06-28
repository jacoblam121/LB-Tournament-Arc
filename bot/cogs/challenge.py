"""
Challenge System Commands - Phase 2.2 Implementation

Hierarchical challenge system supporting N-player matches with proper
cluster→event→match_type selection flow and autocomplete functionality.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import shlex

from bot.database.models import (
    Challenge, ChallengeStatus, ChallengeParticipant,
    ConfirmationStatus, ChallengeRole, Cluster, Event, Player
)
from bot.database.database import Database
from bot.operations.challenge_operations import (
    ChallengeOperations, ChallengeOperationError, 
    DuplicateChallengeError, InvalidPlayerCountError
)
from bot.operations.player_operations import PlayerOperations
from bot.ui.team_formation_modal import TeamFormationModal
from bot.utils.logger import setup_logger
from bot.config import Config

logger = setup_logger(__name__)


class ChallengeCog(commands.Cog):
    """Hierarchical challenge system for all match types"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db
        self.challenge_ops = None
        self.player_ops = None
        self.logger = logger
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize operations after bot and database are ready"""
        if self.bot.db:
            self.challenge_ops = ChallengeOperations(self.bot.db)
            self.player_ops = PlayerOperations(self.bot.db)
            self.logger.info("ChallengeCog operations initialized successfully")
        else:
            self.logger.error("ChallengeCog: Database not available")
    
    @app_commands.command(
        name="challenge",
        description="Create a match challenge through tournament hierarchy"
    )
    @app_commands.describe(
        cluster="Select tournament cluster",
        event="Select event within cluster",
        match_type="Match format (1v1, Team, FFA)",
        players="Players to challenge (space-separated @mentions or names)"
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
        
        try:
            # 1. Early validation before any response
            cluster_id = int(cluster)
            base_event_name = event  # Now using base event name
            
            # Find the specific event based on base name and match type
            events = await self.db.get_all_events(cluster_id=cluster_id, active_only=True)
            
            # Map match_type to scoring_type
            scoring_type_map = {
                "1v1": "1v1",
                "ffa": "FFA",
                "team": "Team"
            }
            scoring_type = scoring_type_map.get(match_type)
            
            # Find the event that matches both base name and scoring type
            matching_event = None
            for e in events:
                if (e.base_event_name or e.name) == base_event_name and e.scoring_type == scoring_type:
                    matching_event = e
                    break
            
            if not matching_event:
                await interaction.response.send_message(
                    embed=self._create_error_embed(
                        "Event Not Found",
                        f"Could not find {base_event_name} event with {match_type} match type."
                    ),
                    ephemeral=True
                )
                return
            
            event_id = matching_event.id
            
            # 2. Parse mentioned players
            mentioned_users = await self._parse_players(interaction, players)
            
            # 3. Auto-include challenger if not mentioned
            if interaction.user not in mentioned_users:
                mentioned_users.append(interaction.user)
            
            # 4. Validate player count for match type
            if not self._validate_player_count(match_type, len(mentioned_users)):
                await interaction.response.send_message(
                    embed=self._create_error_embed(
                        "Invalid Player Count",
                        self._get_player_count_requirements(match_type)
                    ),
                    ephemeral=True
                )
                return
            
            # BIFURCATED FLOW: Team vs Non-Team
            if match_type == "team":
                # For team matches: Send modal as IMMEDIATE response
                team_modal = TeamFormationModal(
                    challenge_cog=self,
                    cluster_id=cluster_id,
                    event_id=event_id,
                    participants=mentioned_users,
                    match_type=match_type
                )
                await interaction.response.send_modal(team_modal)
            else:
                # For 1v1/FFA matches: Use traditional defer flow
                await interaction.response.defer()
                
                # Create challenge with participants
                await self._create_non_team_challenge(
                    interaction=interaction,
                    cluster_id=cluster_id,
                    event_id=event_id,
                    match_type=match_type,
                    participants=mentioned_users
                )
        
        except ValueError as e:
            # Handle invalid cluster/event ID
            await interaction.response.send_message(
                embed=self._create_error_embed("Invalid Selection", str(e)),
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Challenge command error: {e}", exc_info=True)
            
            # Send error response based on interaction state
            error_embed = self._create_error_embed(
                "Challenge Creation Failed",
                "An unexpected error occurred. Please try again."
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
    @challenge.autocomplete('cluster')
    async def cluster_autocomplete(
        self, 
        interaction: discord.Interaction, 
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for cluster selection"""
        try:
            # Get all active clusters
            clusters = await self.db.get_all_clusters(active_only=True)
            
            # Filter by current input
            if current:
                clusters = [c for c in clusters if current.lower() in c.name.lower()]
            
            # Return max 25 choices (Discord limit)
            return [
                app_commands.Choice(name=c.name, value=str(c.id))
                for c in clusters[:25]
            ]
        except Exception as e:
            self.logger.error(f"Cluster autocomplete error: {e}")
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
            
            # Get events for selected cluster
            events = await self.db.get_all_events(
                cluster_id=int(cluster_id), 
                active_only=True
            )
            
            # Group events by base_event_name to show unified events
            event_groups = {}
            for event in events:
                base_name = event.base_event_name or event.name
                if base_name:  # Skip events with no name
                    if base_name not in event_groups:
                        event_groups[base_name] = []
                    event_groups[base_name].append(event)
            
            # Filter by current input
            if current:
                filtered_groups = {
                    name: events 
                    for name, events in event_groups.items() 
                    if current.lower() in name.lower()
                }
                event_groups = filtered_groups
            
            # Return max 25 unique base event names
            return [
                app_commands.Choice(name=base_name, value=base_name)
                for base_name in list(event_groups.keys())[:25]
            ]
        except Exception as e:
            self.logger.error(f"Event autocomplete error: {e}")
            return []
    
    async def _create_non_team_challenge(
        self,
        interaction: discord.Interaction,
        cluster_id: int,
        event_id: int,
        match_type: str,
        participants: List[discord.Member]
    ):
        """Create a challenge for 1v1 or FFA matches"""
        try:
            async with self.db.transaction() as session:
                # Get event details
                event = await self.db.get_event_by_id(event_id)
                if not event:
                    await interaction.followup.send(
                        embed=self._create_error_embed("Invalid Event", "Selected event not found."),
                        ephemeral=True
                    )
                    return
                
                # Get or create Player records
                player_records = []
                for member in participants:
                    player = await self.player_ops.get_or_create_player(member, session=session)
                    player_records.append(player)
                
                # Get challenger Player record
                challenger_player = await self.player_ops.get_or_create_player(
                    interaction.user, session=session
                )
                
                # Create challenge
                challenge = await self.challenge_ops.create_challenge(
                    event=event,
                    participants=player_records,
                    challenger=challenger_player,
                    match_type=match_type,
                    expires_in_hours=24,
                    session=session
                )
                
                # Create success embed
                embed = self._create_challenge_embed(challenge, event, match_type)
                await interaction.followup.send(embed=embed)
                
                # Log challenge creation
                self.logger.info(
                    f"Challenge {challenge.id} created by {interaction.user.id} "
                    f"for event {event.name} ({match_type})"
                )
        
        except DuplicateChallengeError:
            await interaction.followup.send(
                embed=self._create_error_embed(
                    "Duplicate Challenge",
                    "An active challenge already exists for these players in this event."
                ),
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error creating non-team challenge: {e}", exc_info=True)
            await interaction.followup.send(
                embed=self._create_error_embed(
                    "Challenge Creation Failed",
                    f"Failed to create challenge: {str(e)}"
                ),
                ephemeral=True
            )
    
    async def _complete_team_challenge_creation(
        self,
        interaction: discord.Interaction,
        cluster_id: int,
        event_id: int,
        participants: List[discord.Member],
        team_assignments: Dict[int, str]
    ):
        """Complete team challenge creation after modal submission"""
        try:
            # Defer since modal already responded
            await interaction.response.defer()
            
            async with self.db.transaction() as session:
                # Get event details
                event = await self.db.get_event_by_id(event_id)
                if not event:
                    await interaction.followup.send(
                        embed=self._create_error_embed("Invalid Event", "Selected event not found."),
                        ephemeral=True
                    )
                    return
                
                # Get or create Player records
                player_records = []
                for member in participants:
                    player = await self.player_ops.get_or_create_player(member, session=session)
                    player_records.append(player)
                
                # Get challenger Player record
                challenger_player = await self.player_ops.get_or_create_player(
                    interaction.user, session=session
                )
                
                # Create challenge with team assignments
                challenge = await self.challenge_ops.create_challenge(
                    event=event,
                    participants=player_records,
                    challenger=challenger_player,
                    match_type="team",
                    team_assignments=team_assignments,
                    expires_in_hours=24,
                    session=session
                )
                
                # Create success embed with team info
                embed = self._create_team_challenge_embed(
                    challenge, event, team_assignments, participants
                )
                await interaction.followup.send(embed=embed)
                
                self.logger.info(
                    f"Team challenge {challenge.id} created by {interaction.user.id} "
                    f"for event {event.name}"
                )
        
        except DuplicateChallengeError:
            await interaction.followup.send(
                embed=self._create_error_embed(
                    "Duplicate Challenge",
                    "An active challenge already exists for these players in this event."
                ),
                ephemeral=True
            )
        except Exception as e:
            self.logger.error(f"Error creating team challenge: {e}", exc_info=True)
            await interaction.followup.send(
                embed=self._create_error_embed(
                    "Challenge Creation Failed",
                    f"Failed to create team challenge: {str(e)}"
                ),
                ephemeral=True
            )
    
    async def _parse_players(
        self, 
        interaction: discord.Interaction, 
        players_str: str
    ) -> List[discord.Member]:
        """
        Parse player mentions/names from string input.
        
        Handles:
        - Discord mentions (@user)
        - User IDs (123456789)
        - Usernames (JohnDoe)
        - Names with spaces ("John Doe")
        """
        if not players_str.strip():
            return []
        
        members = []
        converter = commands.MemberConverter()
        ctx = await self.bot.get_context(interaction)
        
        try:
            # Use shlex for robust splitting (handles quotes)
            potential_members = shlex.split(players_str)
        except ValueError:
            # Fallback for unmatched quotes
            potential_members = players_str.split()
        
        for arg in potential_members:
            try:
                member = await converter.convert(ctx, arg)
                if member not in members:  # Avoid duplicates
                    members.append(member)
            except commands.MemberNotFound:
                # Try to find by display name or username
                member = discord.utils.find(
                    lambda m: m.display_name.lower() == arg.lower() or 
                             m.name.lower() == arg.lower(),
                    interaction.guild.members
                )
                if member and member not in members:
                    members.append(member)
        
        return members
    
    def _validate_player_count(self, match_type: str, player_count: int) -> bool:
        """Validate player count for match type"""
        match_type_lower = match_type.lower()
        
        if match_type_lower == "1v1":
            return player_count == 2
        elif match_type_lower == "ffa":
            return 3 <= player_count <= 8
        elif match_type_lower == "team":
            return player_count >= 2 and player_count <= 8
        else:
            return False
    
    def _get_player_count_requirements(self, match_type: str) -> str:
        """Get player count requirements message for match type"""
        match_type_lower = match_type.lower()
        
        if match_type_lower == "1v1":
            return "1v1 matches require exactly 2 players."
        elif match_type_lower == "ffa":
            return "Free-for-All matches require 3-8 players."
        elif match_type_lower == "team":
            return "Team matches require 2-8 players."
        else:
            return "Invalid match type."
    
    def _create_challenge_embed(
        self, 
        challenge: Challenge, 
        event: Event, 
        match_type: str
    ) -> discord.Embed:
        """Create embed for successful challenge creation"""
        embed = discord.Embed(
            title="⚔️ Challenge Created!",
            description=f"A new {match_type.upper()} challenge has been created.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Event info
        embed.add_field(
            name="Event",
            value=f"{event.name}\n(Cluster: {event.cluster.name})",
            inline=True
        )
        
        # Match info
        embed.add_field(
            name="Match Type",
            value=match_type.upper(),
            inline=True
        )
        
        # Challenge ID
        embed.add_field(
            name="Challenge ID",
            value=f"#{challenge.id}",
            inline=True
        )
        
        # Participants
        participant_list = []
        challenger_id = None
        
        for participant in challenge.participants:
            player_mention = f"<@{participant.player.discord_id}>"
            
            if participant.role == ChallengeRole.CHALLENGER:
                participant_list.append(f"{player_mention} (Challenger)")
                challenger_id = participant.player.discord_id
            else:
                status_emoji = "⏳" if participant.status == ConfirmationStatus.PENDING else "✅"
                participant_list.append(f"{status_emoji} {player_mention}")
        
        embed.add_field(
            name="Participants",
            value="\n".join(participant_list),
            inline=False
        )
        
        # Expiration
        embed.add_field(
            name="Expires",
            value=f"<t:{int(challenge.expires_at.timestamp())}:R>",
            inline=True
        )
        
        # Instructions
        embed.add_field(
            name="Next Steps",
            value="All participants must accept the challenge using `/accept` command.",
            inline=False
        )
        
        embed.set_footer(text=f"Created by user {challenger_id}")
        
        return embed
    
    def _create_team_challenge_embed(
        self,
        challenge: Challenge,
        event: Event,
        team_assignments: Dict[int, str],
        participants: List[discord.Member]
    ) -> discord.Embed:
        """Create embed for successful team challenge creation"""
        embed = discord.Embed(
            title="⚔️ Team Challenge Created!",
            description="A new TEAM challenge has been created.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Event info
        embed.add_field(
            name="Event",
            value=f"{event.name}\n(Cluster: {event.cluster.name})",
            inline=True
        )
        
        # Challenge ID
        embed.add_field(
            name="Challenge ID",
            value=f"#{challenge.id}",
            inline=True
        )
        
        # Team assignments
        teams = {}
        for member in participants:
            team_id = team_assignments.get(member.id, "Unassigned")
            if team_id not in teams:
                teams[team_id] = []
            teams[team_id].append(f"<@{member.id}>")
        
        # Add team fields
        for team_id, members in sorted(teams.items()):
            team_name = team_id.replace("_", " ").title()
            embed.add_field(
                name=team_name,
                value="\n".join(members),
                inline=True
            )
        
        # Expiration
        embed.add_field(
            name="Expires",
            value=f"<t:{int(challenge.expires_at.timestamp())}:R>",
            inline=False
        )
        
        # Instructions
        embed.add_field(
            name="Next Steps",
            value="All participants must accept the challenge using `/accept` command.",
            inline=False
        )
        
        return embed
    
    def _create_error_embed(self, title: str, description: str) -> discord.Embed:
        """Create a standardized error embed"""
        return discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=discord.Color.red()
        )


async def setup(bot):
    await bot.add_cog(ChallengeCog(bot))