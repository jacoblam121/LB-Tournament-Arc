"""
Challenge System Commands - Phase 2.2 Implementation

Hierarchical challenge system supporting N-player matches with proper
cluster→event→match_type selection flow and autocomplete functionality.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict
from datetime import datetime, timedelta, timezone
import shlex

from bot.database.models import (
    Challenge, ChallengeStatus, ChallengeParticipant,
    ConfirmationStatus, ChallengeRole, Cluster, Event, Player
)
from bot.database.database import Database
from bot.operations.challenge_operations import (
    ChallengeOperations, ChallengeOperationError, 
    DuplicateChallengeError, InvalidPlayerCountError,
    ChallengeAcceptanceResult
)
from bot.operations.player_operations import PlayerOperations
from bot.ui.team_formation_modal import TeamFormationModal
from bot.ui.challenge_pagination import ChallengePaginationView
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
            
            # Find the unified event by base name (Phase 2.4.1: Unified Elo)
            events = await self.db.get_all_events(cluster_id=cluster_id, active_only=True)
            
            # Map match_type to scoring_type for validation
            scoring_type_map = {
                "1v1": "1v1",
                "ffa": "FFA", 
                "team": "Team"
            }
            scoring_type = scoring_type_map.get(match_type)
            
            # Find the unified event by base name
            matching_event = None
            for e in events:
                event_base_name = e.base_event_name or e.name
                if event_base_name == base_event_name:
                    # Check if this unified event supports the requested scoring type
                    if e.supported_scoring_types:
                        supported_types = [t.strip() for t in e.supported_scoring_types.split(',')]
                        if scoring_type in supported_types:
                            matching_event = e
                            break
                    else:
                        # Fallback for events without supported_scoring_types field
                        # (legacy events that haven't been migrated yet)
                        if e.scoring_type == scoring_type:
                            matching_event = e
                            break
            
            if not matching_event:
                await interaction.response.send_message(
                    embed=self._create_error_embed(
                        "Event Not Found",
                        f"Could not find {base_event_name} event that supports {match_type} match type."
                    ),
                    ephemeral=True
                )
                return
            
            event_id = matching_event.id
            
            # BIFURCATED FLOW: Team vs Non-Team
            if match_type == "team":
                # For team matches: Use FAST mention parsing to avoid timeout
                # Only @mentions are supported for team challenges to prevent Discord timeout
                mentioned_users = self._fast_parse_mentions(interaction, players)
                
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
                
                # Create and send modal as IMMEDIATE response (required by Discord API)
                team_modal = TeamFormationModal(
                    challenge_cog=self,
                    cluster_id=cluster_id,
                    event_id=event_id,
                    participants=mentioned_users,
                    match_type=match_type
                )
                await interaction.response.send_modal(team_modal)
            else:
                # For 1v1/FFA matches: Parse first (faster), then defer
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
                
                # Use traditional defer flow
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
        """Autocomplete for cluster selection (guild-specific)"""
        try:
            # Only show clusters if in a guild
            if not interaction.guild:
                return []
            
            # Get active clusters filtered by guild
            async with self.db.get_session() as session:
                from sqlalchemy import select
                stmt = select(Cluster).where(
                    Cluster.is_active == True,
                    # Allow clusters with matching guild_id or no guild_id (legacy support)
                    (Cluster.guild_id == interaction.guild.id) | (Cluster.guild_id.is_(None))
                ).order_by(Cluster.name)
                
                if current:
                    stmt = stmt.where(Cluster.name.ilike(f"%{current}%"))
                
                result = await session.execute(stmt.limit(25))
                clusters = result.scalars().all()
            
            # Return max 25 choices (Discord limit)
            return [
                app_commands.Choice(name=c.name, value=str(c.id))
                for c in clusters
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
    
    @challenge.autocomplete('match_type')
    async def match_type_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete for match type selection, filtered by chosen event's supported scoring types"""
        try:
            # Get selected cluster and event from interaction
            cluster_id = interaction.namespace.cluster
            event_name = interaction.namespace.event
            if not cluster_id or not event_name:
                return []
            
            # Get events for selected cluster and event name
            events = await self.db.get_all_events(
                cluster_id=int(cluster_id), 
                active_only=True
            )
            
            # Find the unified event by base name
            matching_events = []
            for event in events:
                base_name = event.base_event_name or event.name
                if base_name == event_name:
                    matching_events.append(event)
            
            if not matching_events:
                return []
            
            # Collect all supported scoring types from matching events
            supported_types = set()
            for event in matching_events:
                if event.supported_scoring_types:
                    # Parse comma-separated supported types
                    types = [t.strip() for t in event.supported_scoring_types.split(',')]
                    supported_types.update(types)
            
            # Map scoring types to display names and command values
            type_mapping = {
                "1v1": {"display": "1v1", "value": "1v1"},
                "FFA": {"display": "Free for All", "value": "ffa"},
                "Team": {"display": "Team", "value": "team"},
            }
            
            # Create choices for supported types
            choices = []
            for scoring_type in supported_types:
                if scoring_type in type_mapping:
                    mapping = type_mapping[scoring_type]
                    choices.append(
                        app_commands.Choice(
                            name=mapping["display"], 
                            value=mapping["value"]
                        )
                    )
            
            # Filter by current input
            if current:
                choices = [
                    choice for choice in choices 
                    if current.lower() in choice.name.lower()
                ]
            
            return choices[:25]  # Discord limit
            
        except Exception as e:
            self.logger.error(f"Match type autocomplete error: {e}")
            return []
    
    @app_commands.command(
        name="accept",
        description="Accept a pending challenge invitation"
    )
    @app_commands.describe(
        challenge_id="Challenge ID to accept (optional - will auto-detect if you have only one pending)"
    )
    async def accept_challenge(
        self,
        interaction: discord.Interaction,
        challenge_id: Optional[int] = None
    ):
        """Accept a challenge invitation"""
        try:
            # Auto-discovery if no challenge_id provided
            if challenge_id is None:
                pending_challenges = await self.challenge_ops.get_pending_challenges_for_player(
                    interaction.user.id
                )
                
                if len(pending_challenges) == 0:
                    await interaction.response.send_message(
                        embed=self._create_error_embed(
                            "No Pending Challenges",
                            "You have no pending challenge invitations. Use `/challenge` to create new challenges."
                        ),
                        ephemeral=True
                    )
                    return
                elif len(pending_challenges) > 1:
                    # Multiple pending challenges - require explicit ID
                    challenge_list = "\n".join([
                        f"• Challenge #{c.id} - {c.event.name}"
                        for c in pending_challenges[:5]  # Show first 5
                    ])
                    if len(pending_challenges) > 5:
                        challenge_list += f"\n... and {len(pending_challenges) - 5} more"
                    
                    await interaction.response.send_message(
                        embed=self._create_error_embed(
                            "Multiple Pending Challenges",
                            f"You have {len(pending_challenges)} pending challenges. "
                            f"Please specify the challenge ID to accept:\n\n{challenge_list}\n\n"
                            f"Use `/incoming-challenges` to see all pending invitations."
                        ),
                        ephemeral=True
                    )
                    return
                else:
                    # Exactly one pending challenge - use it
                    challenge_id = pending_challenges[0].id
            
            await interaction.response.defer()
            
            # Process acceptance
            result = await self.challenge_ops.accept_challenge(
                challenge_id=challenge_id,
                player_discord_id=interaction.user.id
            )
            
            if result.success:
                if result.match_created:
                    # All participants accepted - match created
                    embed = self._create_match_ready_embed(result.match, result.challenge)
                    await interaction.followup.send(embed=embed)
                else:
                    # Partial acceptance - update status
                    embed = self._create_updated_challenge_embed(result.challenge)
                    await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(
                    embed=self._create_error_embed("Cannot Accept", result.error_message),
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"Accept challenge error: {e}", exc_info=True)
            
            # Handle error response based on interaction state
            error_embed = self._create_error_embed(
                "Accept Failed",
                "An unexpected error occurred. Please try again."
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
    @app_commands.command(
        name="decline", 
        description="Decline a pending challenge invitation"
    )
    @app_commands.describe(
        challenge_id="Challenge ID to decline (optional - will auto-detect if you have only one pending)",
        reason="Optional reason for declining"
    )
    async def decline_challenge(
        self,
        interaction: discord.Interaction,
        challenge_id: Optional[int] = None,
        reason: Optional[str] = None
    ):
        """Decline a challenge invitation"""
        try:
            # Auto-discovery if no challenge_id provided
            if challenge_id is None:
                pending_challenges = await self.challenge_ops.get_pending_challenges_for_player(
                    interaction.user.id
                )
                
                if len(pending_challenges) == 0:
                    await interaction.response.send_message(
                        embed=self._create_error_embed(
                            "No Pending Challenges",
                            "You have no pending challenge invitations."
                        ),
                        ephemeral=True
                    )
                    return
                elif len(pending_challenges) > 1:
                    # Multiple pending challenges - require explicit ID
                    challenge_list = "\n".join([
                        f"• Challenge #{c.id} - {c.event.name}"
                        for c in pending_challenges[:5]  # Show first 5
                    ])
                    if len(pending_challenges) > 5:
                        challenge_list += f"\n... and {len(pending_challenges) - 5} more"
                    
                    await interaction.response.send_message(
                        embed=self._create_error_embed(
                            "Multiple Pending Challenges",
                            f"You have {len(pending_challenges)} pending challenges. "
                            f"Please specify the challenge ID to decline:\n\n{challenge_list}\n\n"
                            f"Use `/incoming-challenges` to see all pending invitations."
                        ),
                        ephemeral=True
                    )
                    return
                else:
                    # Exactly one pending challenge - use it
                    challenge_id = pending_challenges[0].id
            
            await interaction.response.defer()
            
            # Process decline
            result = await self.challenge_ops.decline_challenge(
                challenge_id=challenge_id,
                player_discord_id=interaction.user.id,
                reason=reason
            )
            
            if result.success:
                # Challenge cancelled - create cancellation embed
                embed = self._create_challenge_cancelled_embed(result.challenge, interaction.user, reason)
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(
                    embed=self._create_error_embed("Cannot Decline", result.error_message),
                    ephemeral=True
                )
                
        except Exception as e:
            self.logger.error(f"Decline challenge error: {e}", exc_info=True)
            
            # Handle error response based on interaction state
            error_embed = self._create_error_embed(
                "Decline Failed",
                "An unexpected error occurred. Please try again."
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
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
    
    
    def _create_updated_challenge_embed(self, challenge: Challenge) -> discord.Embed:
        """Create embed showing current acceptance status"""
        embed = discord.Embed(
            title="⏳ Challenge Status Update",
            description=f"Challenge #{challenge.id} acceptance in progress",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc)
        )
        
        # Show acceptance progress
        total_participants = len(challenge.participants)
        accepted_count = sum(1 for p in challenge.participants 
                            if p.status == ConfirmationStatus.CONFIRMED)
        
        embed.add_field(
            name="Progress",
            value=f"{accepted_count}/{total_participants} participants accepted",
            inline=True
        )
        
        # Event info
        embed.add_field(
            name="Event",
            value=f"{challenge.event.name}",
            inline=True
        )
        
        # Empty field for layout
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        # List participant status with emojis
        status_list = []
        for participant in challenge.participants:
            emoji = {
                ConfirmationStatus.PENDING: "⏳",
                ConfirmationStatus.CONFIRMED: "✅", 
                ConfirmationStatus.REJECTED: "❌"
            }.get(participant.status, "❓")
            
            status_list.append(f"{emoji} <@{participant.player.discord_id}>")
        
        embed.add_field(
            name="Participants",
            value="\n".join(status_list),
            inline=False
        )
        
        return embed
    
    def _create_match_ready_embed(self, match, challenge: Challenge) -> discord.Embed:
        """Create embed when all participants accept and match is created"""
        # Format match context for clarity
        cluster_name = challenge.event.cluster.name if challenge.event.cluster else "Unknown"
        event_name = challenge.event.name
        match_type = match.scoring_type.upper()
        match_context = f"🎮 {cluster_name} • {event_name} • {match_type}"
        
        embed = discord.Embed(
            title="Match Ready!",
            description=f"{match_context}\nAll participants accepted - Match #{match.id} created",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Match ID",
            value=f"#{match.id}",
            inline=True
        )
        
        # Participants list
        participant_list = []
        for participant in challenge.participants:
            player_mention = f"<@{participant.player.discord_id}>"
            if participant.team_id:
                participant_list.append(f"👥 {player_mention} (Team {participant.team_id})")
            else:
                participant_list.append(f"⚔️ {player_mention}")
        
        embed.add_field(
            name="Participants",
            value="\n".join(participant_list),
            inline=False
        )
        
        embed.add_field(
            name="Next Steps",
            value="Play your match and report results using `/match-report`",
            inline=False
        )
        
        return embed
    
    def _create_challenge_cancelled_embed(self, challenge: Challenge, declining_user: discord.User, reason: Optional[str]) -> discord.Embed:
        """Create embed when challenge is cancelled due to decline"""
        embed = discord.Embed(
            title="❌ Challenge Cancelled",
            description=f"Challenge #{challenge.id} has been cancelled",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc)
        )
        
        embed.add_field(
            name="Event",
            value=challenge.event.name,
            inline=True
        )
        
        embed.add_field(
            name="Declined by",
            value=f"<@{declining_user.id}>",
            inline=True
        )
        
        if reason:
            embed.add_field(
                name="Reason",
                value=reason,
                inline=False
            )
        
        embed.add_field(
            name="Note",
            value="When any participant declines, the entire challenge is cancelled.",
            inline=False
        )
        
        return embed
    
    def _fast_parse_mentions(
        self,
        interaction: discord.Interaction,
        players_str: str
    ) -> List[discord.Member]:
        """
        Fast parsing of Discord @mentions only for team challenges.
        
        This method completes in ~1ms vs 3000ms+ for full parsing,
        preventing Discord interaction timeout.
        
        Only supports @mentions, not username strings.
        """
        import re
        
        if not players_str.strip():
            return []
        
        # Extract Discord mention IDs using regex: <@userid> or <@!userid>
        mention_pattern = r'<@!?(\d+)>'
        user_ids = re.findall(mention_pattern, players_str)
        
        members = []
        for user_id in user_ids:
            member = interaction.guild.get_member(int(user_id))
            if member and member not in members:
                members.append(member)
        
        return members

    async def _parse_players(
        self, 
        interaction: discord.Interaction, 
        players_str: str
    ) -> List[discord.Member]:
        """
        Full parsing of player mentions/names from string input.
        
        Handles:
        - Discord mentions (@user)
        - User IDs (123456789)
        - Usernames (JohnDoe)
        - Names with spaces ("John Doe")
        
        WARNING: This method can take 3+ seconds and cause Discord timeouts.
        Use _fast_parse_mentions() for team challenges.
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
            title="Challenge Created!",
            description=f"A new {match_type.upper()} challenge has been created.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
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
                # Challengers are auto-confirmed, so always show ✅
                participant_list.append(f"✅ {player_mention} (Challenger)")
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
            title="Team Challenge Created!",
            description="A new TEAM challenge has been created.",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
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
        
        # Empty field to ensure teams appear on same line
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        # Team assignments
        teams = {}
        for member in participants:
            team_id = team_assignments.get(member.id, "Unassigned")
            if team_id not in teams:
                teams[team_id] = []
            teams[team_id].append(f"<@{member.id}>")
        
        # Add team fields with letter mapping (both on same line)
        team_letter_map = {"Team_0": "A", "Team_1": "B"}
        for team_id, members in sorted(teams.items()):
            if team_id in team_letter_map:
                team_name = f"Team {team_letter_map[team_id]}"
            else:
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
    
    # Phase 2.4.3: Challenge Management Commands
    
    @app_commands.command(
        name="outgoing-challenges",
        description="View all challenges you've created"
    )
    async def outgoing_challenges(
        self,
        interaction: discord.Interaction,
        show_cancelled: bool = False,
        show_completed: bool = False
    ):
        """View all challenges created by the user"""
        try:
            await interaction.response.defer()
            
            # Get challenges where user is the challenger
            challenges = await self.challenge_ops.get_outgoing_challenges(
                interaction.user.id,
                include_expired=True,
                show_cancelled=show_cancelled,
                show_completed=show_completed
            )
            
            if not challenges:
                embed = discord.Embed(
                    title="📤 Outgoing Challenges",
                    description="You have no outgoing challenges.",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Create embed for challenges
            embeds = self._create_challenge_list_embeds(
                challenges, 
                "📤 Outgoing Challenges",
                interaction.user
            )
            
            # Send with pagination if multiple pages
            if len(embeds) > 1:
                view = ChallengePaginationView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)
            else:
                await interaction.followup.send(embed=embeds[0])
                
        except Exception as e:
            self.logger.error(f"Error in outgoing_challenges: {e}", exc_info=True)
            await interaction.followup.send(
                embed=self._create_error_embed(
                    "Failed to retrieve challenges",
                    "An unexpected error occurred. Please try again."
                ),
                ephemeral=True
            )
    
    @app_commands.command(
        name="incoming-challenges",
        description="View pending challenges sent to you"
    )
    async def incoming_challenges(
        self,
        interaction: discord.Interaction,
        show_cancelled: bool = False,
        show_completed: bool = False
    ):
        """View pending challenges where user needs to respond"""
        try:
            await interaction.response.defer()
            
            # Get pending challenges where user is challenged
            challenges = await self.challenge_ops.get_incoming_challenges(
                interaction.user.id,
                show_cancelled=show_cancelled,
                show_completed=show_completed
            )
            
            if not challenges:
                embed = discord.Embed(
                    title="📥 Incoming Challenges",
                    description="You have no pending challenge invitations.",
                    color=discord.Color.blue()
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Create embed for challenges
            embeds = self._create_challenge_list_embeds(
                challenges,
                "📥 Incoming Challenges", 
                interaction.user,
                show_accept_hint=True
            )
            
            # Send with pagination if multiple pages
            if len(embeds) > 1:
                view = ChallengePaginationView(embeds)
                await interaction.followup.send(embed=embeds[0], view=view)
            else:
                await interaction.followup.send(embed=embeds[0])
                
        except Exception as e:
            self.logger.error(f"Error in incoming_challenges: {e}", exc_info=True)
            await interaction.followup.send(
                embed=self._create_error_embed(
                    "Failed to retrieve challenges",
                    "An unexpected error occurred. Please try again."
                ),
                ephemeral=True
            )
    
    # DEPRECATED 2025-01-01 - ACTIVE CHALLENGES COMMAND
    # This command conflated Challenge (invitation system) with Match (game tracking system).
    # Use /incoming-challenges and /outgoing-challenges with show_completed=true for challenge history.
    # Future /active-matches command will properly track ongoing games via Match table.
    # 
    # @app_commands.command(
    #     name="active-challenges",
    #     description="View your ongoing accepted challenges and matches"
    # )
    # async def active_challenges(
    #     self,
    #     interaction: discord.Interaction,
    #     show_cancelled: bool = False
    # ):
    #     """View accepted challenges that are ready to play"""
    #     try:
    #         await interaction.response.defer()
    #         
    #         # Get accepted challenges where user is a participant
    #         challenges = await self.challenge_ops.get_active_challenges(
    #             interaction.user.id,
    #             show_cancelled=show_cancelled
    #         )
    #         
    #         if not challenges:
    #             embed = discord.Embed(
    #                 title="🎮 Active Challenges",
    #                 description="You have no active challenges or matches.",
    #                 color=discord.Color.green()
    #             )
    #             await interaction.followup.send(embed=embed)
    #             return
    #         
    #         # Create embed for challenges
    #         embeds = self._create_challenge_list_embeds(
    #             challenges,
    #             "🎮 Active Challenges",
    #             interaction.user,
    #             show_match_hint=True
    #         )
    #         
    #         # Send with pagination if multiple pages
    #         if len(embeds) > 1:
    #             view = ChallengePaginationView(embeds)
    #             await interaction.followup.send(embed=embeds[0], view=view)
    #         else:
    #             await interaction.followup.send(embed=embeds[0])
    #             
    #     except Exception as e:
    #         self.logger.error(f"Error in active_challenges: {e}", exc_info=True)
    #         await interaction.followup.send(
    #             embed=self._create_error_embed(
    #                 "Failed to retrieve challenges",
    #                 "An unexpected error occurred. Please try again."
    #             ),
    #             ephemeral=True
    #         )
    
    @app_commands.command(
        name="cancel-challenge",
        description="Cancel a pending challenge you created"
    )
    @app_commands.describe(
        challenge_id="Challenge ID to cancel (optional - will auto-cancel latest if not provided)"
    )
    async def cancel_challenge(
        self,
        interaction: discord.Interaction,
        challenge_id: Optional[int] = None
    ):
        """Cancel a pending challenge created by the user"""
        try:
            await interaction.response.defer()
            
            if challenge_id is None:
                # Auto-cancel latest pending challenge
                cancelled = await self.challenge_ops.cancel_latest_pending_challenge(
                    interaction.user.id
                )
                
                if not cancelled:
                    await interaction.followup.send(
                        embed=self._create_error_embed(
                            "No Pending Challenges",
                            "You have no pending challenges to cancel."
                        ),
                        ephemeral=True
                    )
                    return
            else:
                # Cancel specific challenge
                try:
                    cancelled = await self.challenge_ops.cancel_challenge(
                        challenge_id,
                        interaction.user.id
                    )
                except ChallengeOperationError as e:
                    await interaction.followup.send(
                        embed=self._create_error_embed(
                            "Cannot Cancel Challenge",
                            str(e)
                        ),
                        ephemeral=True
                    )
                    return
            
            # Create success embed
            embed = self._create_challenge_cancelled_embed(
                cancelled,
                interaction.user,
                "Challenge cancelled by creator"
            )
            await interaction.followup.send(embed=embed)
            
            # Try to notify other participants
            await self._notify_challenge_cancellation(cancelled, interaction.user)
            
        except Exception as e:
            self.logger.error(f"Error in cancel_challenge: {e}", exc_info=True)
            await interaction.followup.send(
                embed=self._create_error_embed(
                    "Failed to cancel challenge",
                    "An unexpected error occurred. Please try again."
                ),
                ephemeral=True
            )
    
    def _create_challenge_list_embeds(
        self,
        challenges: List[Challenge],
        title: str,
        user: discord.User,
        show_accept_hint: bool = False,
        show_match_hint: bool = False,
        items_per_page: int = 10
    ) -> List[discord.Embed]:
        """Create paginated embeds for challenge lists"""
        embeds = []
        total_pages = (len(challenges) + items_per_page - 1) // items_per_page
        
        for page_num in range(total_pages):
            start_idx = page_num * items_per_page
            end_idx = min(start_idx + items_per_page, len(challenges))
            page_challenges = challenges[start_idx:end_idx]
            
            embed = discord.Embed(
                title=title,
                color=discord.Color.blue(),
                timestamp=datetime.now(timezone.utc)
            )
            
            # Add challenges to this page
            for challenge in page_challenges:
                field_value = self._format_challenge_summary(challenge, user)
                embed.add_field(
                    name=f"Challenge #{challenge.id}",
                    value=field_value,
                    inline=False
                )
            
            # Add footer with pagination info and hints
            footer_text = f"Page {page_num + 1}/{total_pages} | Total: {len(challenges)}"
            if show_accept_hint:
                footer_text += " | Use /accept to respond"
            elif show_match_hint:
                footer_text += " | Use /match-report to report results"
            
            embed.set_footer(text=footer_text)
            embeds.append(embed)
        
        return embeds
    
    def _format_challenge_summary(
        self,
        challenge: Challenge,
        viewer: discord.User
    ) -> str:
        """Format a challenge summary for list display"""
        lines = []
        
        # Determine match type from participants and team assignments
        participant_count = len(challenge.participants) if challenge.participants else 0
        has_teams = any(p.team_id for p in challenge.participants) if challenge.participants else False
        
        if participant_count == 2:
            match_type = "1V1"
        elif has_teams:
            match_type = "TEAM"
        elif participant_count > 2:
            match_type = "FFA"
        else:
            match_type = "UNKNOWN"  # Fallback for edge cases
        
        # Location info with inferred match type
        cluster_name = challenge.event.cluster.name if challenge.event and challenge.event.cluster else "Unknown"
        event_name = challenge.event.name if challenge.event else "Unknown"
        lines.append(f"**Location:** {cluster_name} → {event_name} → {match_type}")
        
        # Status with emoji
        status_emoji = {
            ChallengeStatus.PENDING: "⏳",
            ChallengeStatus.ACCEPTED: "✅",
            ChallengeStatus.DECLINED: "❌",
            ChallengeStatus.EXPIRED: "⏰",
            ChallengeStatus.COMPLETED: "🏁",
            ChallengeStatus.CANCELLED: "🚫"
        }.get(challenge.status, "❓")
        lines.append(f"**Status:** {status_emoji} {challenge.status.value.title()}")
        
        # Participants summary
        participant_mentions = []
        for p in challenge.participants:
            if p.player.discord_id == viewer.id:
                participant_mentions.append(f"**You**")
            else:
                participant_mentions.append(f"<@{p.player.discord_id}>")
        lines.append(f"**Players:** {', '.join(participant_mentions)}")
        
        # Time info
        if challenge.status == ChallengeStatus.PENDING and challenge.expires_at:
            lines.append(f"**Expires:** <t:{int(challenge.expires_at.timestamp())}:R>")
        elif challenge.status == ChallengeStatus.ACCEPTED and challenge.accepted_at:
            lines.append(f"**Accepted:** <t:{int(challenge.accepted_at.timestamp())}:R>")
        
        # Your role in the challenge
        your_participant = next(
            (p for p in challenge.participants if p.player.discord_id == viewer.id),
            None
        )
        if your_participant:
            role_text = "Challenger" if your_participant.role == ChallengeRole.CHALLENGER else "Challenged"
            lines.append(f"**Your Role:** {role_text}")
        
        return "\n".join(lines)
    
    async def _notify_challenge_cancellation(
        self,
        challenge: Challenge,
        canceller: discord.User
    ):
        """Send hybrid notifications about challenge cancellation"""
        
        # First, always try to send a channel notification (less intrusive)
        await self._send_channel_notification(challenge, canceller)
        
        # Then, send DMs only to users who have opted in
        await self._send_dm_notifications(challenge, canceller)
    
    async def _send_channel_notification(
        self,
        challenge: Challenge,
        canceller: discord.User
    ):
        """Send cancellation notification in the original challenge channel"""
        try:
            if challenge.discord_channel_id:
                channel = self.bot.get_channel(challenge.discord_channel_id)
                if channel:
                    # Get participant mentions (excluding canceller)
                    participants = [
                        f"<@{p.player.discord_id}>" 
                        for p in challenge.participants 
                        if p.player.discord_id != canceller.id
                    ]
                    
                    embed = discord.Embed(
                        title="❌ Challenge Cancelled",
                        description=(
                            f"Challenge #{challenge.id} for **{challenge.event.name}** "
                            f"has been cancelled by {canceller.mention}."
                        ),
                        color=discord.Color.red(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    
                    if participants:
                        embed.add_field(
                            name="Participants Notified",
                            value=", ".join(participants),
                            inline=False
                        )
                    
                    embed.set_footer(
                        text="Want DM notifications? Use /notification-preferences dm_cancellations:True"
                    )
                    
                    content = " ".join(participants) if participants else None
                    await channel.send(content=content, embed=embed)
                    
                    self.logger.info(
                        f"Sent channel notification for challenge {challenge.id} cancellation "
                        f"to channel {channel.name} ({channel.id})"
                    )
                    return True
                    
        except Exception as e:
            self.logger.error(
                f"Failed to send channel notification for challenge {challenge.id}: {e}",
                exc_info=True
            )
        
        return False
    
    async def _send_dm_notifications(
        self,
        challenge: Challenge,
        canceller: discord.User
    ):
        """Send DM notifications to opted-in participants"""
        
        # Get participants who want DM notifications (excluding canceller)
        async with self.db.get_session() as session:
            from sqlalchemy import select, and_
            from bot.database.models import Player
            
            participant_ids = [
                p.player.discord_id for p in challenge.participants 
                if p.player.discord_id != canceller.id
            ]
            
            if not participant_ids:
                return
            
            # Query for players who have opted in to DM notifications
            stmt = (
                select(Player)
                .where(
                    and_(
                        Player.discord_id.in_(participant_ids),
                        Player.dm_challenge_notifications == True
                    )
                )
            )
            
            result = await session.execute(stmt)
            opted_in_players = result.scalars().all()
            
            # Send DMs to opted-in users
            dm_count = 0
            for player in opted_in_players:
                try:
                    user = self.bot.get_user(player.discord_id)
                    if user:
                        embed = discord.Embed(
                            title="🔔 Challenge Cancelled",
                            description=(
                                f"Challenge #{challenge.id} for **{challenge.event.name}** "
                                f"has been cancelled by {canceller.mention}.\n\n"
                                f"This DM was sent because you have notifications enabled. "
                                f"Disable with `/notification-preferences dm_cancellations:False`"
                            ),
                            color=discord.Color.red(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        
                        await user.send(embed=embed)
                        dm_count += 1
                        
                except discord.Forbidden:
                    # User has DMs disabled - they'll see the channel notification
                    self.logger.info(
                        f"Could not DM user {player.discord_id} "
                        f"about challenge {challenge.id} cancellation (DMs disabled)"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Error sending DM to user {player.discord_id}: {e}",
                        exc_info=True
                    )
            
            if dm_count > 0:
                self.logger.info(
                    f"Sent DM notifications to {dm_count} opted-in users "
                    f"for challenge {challenge.id} cancellation"
                )
    
    @app_commands.command(
        name="notification-preferences",
        description="Configure your notification preferences for challenge events"
    )
    @app_commands.describe(
        dm_cancellations="Receive DMs when challenges you're in are cancelled (default: off)"
    )
    async def notification_preferences(
        self,
        interaction: discord.Interaction,
        dm_cancellations: bool
    ):
        """Configure notification preferences for challenge events"""
        try:
            async with self.db.transaction() as session:
                # Get or create player record
                player = await self.player_ops.get_or_create_player(
                    interaction.user, session=session
                )
                
                # Update notification preference
                old_preference = player.dm_challenge_notifications
                player.dm_challenge_notifications = dm_cancellations
                
                # Create response embed
                if dm_cancellations:
                    title = "🔔 DM Notifications Enabled"
                    description = (
                        "You will now receive direct messages when:\n"
                        "• Challenges you're participating in are cancelled\n\n"
                        "You can disable this anytime with `/notification-preferences dm_cancellations:False`"
                    )
                    color = discord.Color.green()
                    
                    # Send a test DM to confirm it works
                    try:
                        test_embed = discord.Embed(
                            title="✅ Notifications Enabled",
                            description="You'll receive DMs like this when challenges are cancelled.",
                            color=discord.Color.blue()
                        )
                        await interaction.user.send(embed=test_embed)
                    except discord.Forbidden:
                        # User has DMs disabled
                        description += "\n\n⚠️ **Warning**: Your DMs appear to be disabled. Enable DMs from server members to receive notifications."
                        color = discord.Color.orange()
                        
                else:
                    title = "🔕 DM Notifications Disabled"
                    description = (
                        "You will no longer receive direct messages for challenge cancellations.\n\n"
                        "You'll still see notifications in the original challenge channels.\n"
                        "Enable DMs anytime with `/notification-preferences dm_cancellations:True`"
                    )
                    color = discord.Color.orange()
                
                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=color,
                    timestamp=datetime.now(timezone.utc)
                )
                
                if old_preference != dm_cancellations:
                    embed.set_footer(text="Preference updated successfully")
                else:
                    embed.set_footer(text="No change to existing preference")
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
                self.logger.info(
                    f"User {interaction.user.id} ({interaction.user.name}) "
                    f"{'enabled' if dm_cancellations else 'disabled'} DM notifications"
                )
                
        except Exception as e:
            self.logger.error(f"Error updating notification preferences: {e}", exc_info=True)
            await interaction.response.send_message(
                embed=self._create_error_embed(
                    "Settings Update Failed",
                    "Failed to update your notification preferences. Please try again."
                ),
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(ChallengeCog(bot))