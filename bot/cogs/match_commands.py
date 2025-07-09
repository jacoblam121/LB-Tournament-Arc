"""
Match Commands Cog - Phase 2A2.5 Subphase 1: Discord Command Foundation

This cog provides Discord commands for N-player match functionality,
integrating with the MatchOperations backend from Phase 2A2.4.

Foundation implementation with test command and stubs for future development.
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
from sqlalchemy import text
import asyncio
import shlex
import re
import random
import json

from bot.database.match_operations import MatchOperations, MatchOperationError, MatchStateError
from bot.operations.player_operations import PlayerOperations, PlayerOperationError
from bot.database.models import Match, MatchParticipant, MatchStatus, ConfirmationStatus, Player, Event
from bot.services.profile import ProfileService
from bot.services.elo_hierarchy_cache import CachedEloHierarchyService
from bot.utils.error_embeds import ErrorEmbeds
from bot.utils.logger import setup_logger
from bot.config import Config


def format_match_context(match: Match) -> str:
    """Format match context for consistent display across all embeds"""
    if not match or not match.event:
        return "🎮 Unknown Event"
    
    cluster_name = match.event.cluster.name if match.event.cluster else "Unknown"
    event_name = match.event.name
    match_type = match.scoring_type.upper()
    
    return f"🎮 {cluster_name} • {event_name} • {match_type}"


def is_bot_owner(interaction: discord.Interaction) -> bool:
    """
    Securely checks if the interaction user is the bot owner.
    
    Args:
        interaction: Discord interaction to check permissions for
        
    Returns:
        bool: True if user is bot owner, False otherwise
    """
    return interaction.user.id == Config.OWNER_DISCORD_ID


def is_user_bot_owner(user: discord.User | discord.Member) -> bool:
    """
    Checks if a user is the bot owner.
    
    Args:
        user: Discord User or Member object to check
        
    Returns:
        bool: True if user is bot owner, False otherwise
    """
    return user.id == Config.OWNER_DISCORD_ID


# ============================================================================
# Phase 2.2a: Modal Infrastructure for Dynamic Placement Entry
# ============================================================================

class PlacementModal(discord.ui.Modal):
    """
    Dynamic modal for placement entry in matches with ≤5 players.
    
    Creates TextInput fields for each participant, allowing intuitive
    form-based placement entry instead of string parsing.
    """
    
    def __init__(self, cog: 'MatchCommandsCog', match_id: int, participants: List[MatchParticipant], match_ops: MatchOperations, force: bool = False):
        """
        Initialize modal with dynamic fields based on participants.
        
        Args:
            cog: MatchCommandsCog instance for accessing business logic methods
            match_id: ID of the match being reported
            participants: List of MatchParticipant objects (max 5)
            match_ops: MatchOperations instance for result recording
        """
        # Title must be ≤45 characters for Discord
        title = f"Match {match_id} Results"
        if len(title) > 45:
            title = f"Match {match_id}"
        
        super().__init__(title=title, timeout=900)  # 15 minute timeout
        
        self.cog = cog
        self.match_id = match_id
        self.participants = participants
        self.match_ops = match_ops
        self.force = force
        self.logger = setup_logger(f"{__name__}.PlacementModal")
        
        # Validate participant count (Discord limit: 5 components)
        if len(participants) > 5:
            raise ValueError(f"Modal supports maximum 5 participants, got {len(participants)}")
        
        # Dynamic field generation for each participant
        for participant in participants:
            player_name = participant.player.display_name
            # Truncate long names to fit in label (max 45 chars)
            if len(player_name) > 35:
                player_name = player_name[:32] + "..."
            
            text_input = discord.ui.TextInput(
                label=f"{player_name} placement",
                placeholder="Enter 1, 2, 3, etc.",
                required=True,
                min_length=1,
                max_length=2,
                style=discord.TextStyle.short,
                custom_id=f"placement_{participant.player.id}"
            )
            self.add_item(text_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """
        Process modal submission and record match results.
        
        Validates placement data and integrates with Phase B confirmation workflow.
        """
        try:
            await interaction.response.defer()
            
            # Extract placements from modal inputs
            placements = {}
            for item in self.children:
                if isinstance(item, discord.ui.TextInput):
                    # Extract player_id from custom_id
                    player_id = int(item.custom_id.split("_")[1])
                    
                    # Parse and validate placement value
                    try:
                        placement = int(item.value.strip())
                        if placement < 1:
                            raise ValueError(f"Placement must be positive, got {placement}")
                        placements[player_id] = placement
                    except ValueError as e:
                        await interaction.followup.send(
                            f"❌ Invalid placement for player ID {player_id}: {item.value}. Must be a positive number.",
                            ephemeral=True
                        )
                        return
            
            # Validate placements are unique and sequential
            await self._validate_modal_placements(placements, interaction)
            
            # Convert to format expected by match completion API
            results_list = [
                {"player_id": player_id, "placement": placement}
                for player_id, placement in placements.items()
            ]
            
            # ============================================================================
            # Phase B Integration: Owner can choose force completion or normal workflow
            # ============================================================================
            
            # Check if user is bot owner (only owner can force complete)
            is_owner = is_bot_owner(interaction)
            
            # Permission check: Only owner can use force parameter
            if self.force and not is_owner:
                embed = discord.Embed(
                    title="❌ Insufficient Permissions",
                    description="Only the bot owner can use the `force` parameter.",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Simplified logic: Owner force completion or normal workflow
            if is_owner and self.force:
                # Owner force completion - bypass confirmation (if force is chosen)
                match = await self.match_ops.complete_match_with_results(
                    match_id=self.match_id,
                    results=results_list
                )
                
                # Update streaks for all participants
                await self.cog._update_participant_streaks(match)
                
                # Create success embed with owner indication
                embed = await self._create_success_embed(match, interaction, force_completion=True)
                await interaction.followup.send(embed=embed)
                
            else:
                # Normal flow: Create proposal for confirmation
                player_ops = PlayerOperations(self.match_ops.db)
                
                # Get the proposer (modal submitter)
                proposer_player = await player_ops.get_or_create_player(interaction.user)
                
                # Create result proposal
                proposal = await self.match_ops.create_result_proposal(
                    match_id=self.match_id,
                    proposer_id=proposer_player.id,
                    results=results_list,
                    expires_in_hours=24,  # 24 hour expiration
                    discord_channel_id=interaction.channel_id,
                    discord_message_id=None  # Will be set after message creation
                )
                
                # Create confirmation view with buttons
                view = MatchConfirmationView(proposal.id, self.match_ops, self.cog)
                
                # Get current confirmation status (proposer is auto-confirmed)
                _, confirmations = await self.match_ops.check_all_confirmed(self.match_id)
                
                # Build unified embed showing both results and confirmation status
                embed = view._create_unified_embed(proposal, confirmations, results_list)
                
                # Send proposal with confirmation buttons
                await interaction.followup.send(embed=embed, view=view)
            
            if is_owner and self.force:
                self.logger.info(
                    f"Modal: Owner force-completed Match {self.match_id} "
                    f"with {len(placements)} participants by {interaction.user.id}"
                )
            else:
                self.logger.info(
                    f"Modal: Created proposal for Match {self.match_id} "
                    f"with {len(placements)} participants by {interaction.user.id}"
                )
            
        except MatchOperationError as e:
            self.logger.error(f"Modal: Match operation failed for Match {self.match_id}: {e}")
            await interaction.followup.send(embed=ErrorEmbeds.command_error(str(e)), ephemeral=True)
            
        except Exception as e:
            self.logger.error(f"Modal: Unexpected error for Match {self.match_id}: {e}")
            await interaction.followup.send(embed=ErrorEmbeds.command_error("An unexpected error occurred while recording results."), ephemeral=True)
    
    async def on_timeout(self):
        """
        Handle modal timeout (15 minutes).
        
        Note: Cannot edit original interaction after timeout due to Discord limitations.
        """
        self.logger.warning(f"Modal timeout for Match {self.match_id} after 15 minutes")
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """
        Handle modal submission errors.
        """
        self.logger.error(f"Modal error for Match {self.match_id}: {error}")
        try:
            embed = discord.Embed(
                title="❌ Modal Error",
                description="An error occurred while processing your submission.",
                color=discord.Color.red()
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except:
            # Fallback if interaction is no longer valid
            pass
    
    async def _validate_modal_placements(self, placements: dict, interaction: discord.Interaction):
        """
        Validate that modal placements form a valid competition ranking sequence, allowing for ties.
        
        Args:
            placements: Dict of player_id -> placement
            interaction: Discord interaction for error reporting
            
        Raises:
            ValueError: If placements are invalid
        """
        if not placements:
            await interaction.followup.send(
                "❌ No placements provided. Please fill in all fields.",
                ephemeral=True
            )
            raise ValueError("No placements provided")
        
        placement_values = list(placements.values())
        
        # Validate that placements start at 1
        if min(placement_values) != 1:
            await interaction.followup.send(
                "❌ Invalid placements: Placements must start from 1.",
                ephemeral=True
            )
            raise ValueError("Placements must start from 1")

        # Validate standard competition ranking (e.g., 1, 2, 2, 4 is valid)
        placement_counts = {}
        for p in placement_values:
            placement_counts[p] = placement_counts.get(p, 0) + 1
        
        current_position = 1
        for placement in sorted(placement_counts.keys()):
            if placement < current_position:
                error_msg = (
                    f"❌ Invalid placement sequence. After position {current_position - 1}, "
                    f"the next placement should be {current_position} or higher, but got {placement}."
                )
                await interaction.followup.send(error_msg, ephemeral=True)
                raise ValueError(f"Invalid placement sequence: {placement} used after position {current_position}")
            current_position += placement_counts[placement]
    
    async def _create_success_embed(self, match: Match, interaction: discord.Interaction, force_completion: bool = False) -> discord.Embed:
        """
        Create success embed showing match results.
        
        Args:
            match: Completed Match object with results
            interaction: Discord interaction for user context
            
        Returns:
            Discord embed with formatted results
        """
        embed = discord.Embed(
            title="✅ Match Results Recorded!",
            description=f"**Match ID:** {match.id}",
            color=discord.Color.green()
        )
        
        # Sort participants by placement
        sorted_participants = sorted(match.participants, key=lambda p: p.placement)
        
        # Build results display with both event and cluster ELO
        results_text = []
        for participant in sorted_participants:
            # Format event ELO change
            if participant.elo_change != 0:
                event_elo_text = f"{participant.elo_before} → {participant.elo_after} ("
                if participant.elo_change > 0:
                    event_elo_text += f"+{participant.elo_change})"
                else:
                    event_elo_text += f"{participant.elo_change})"
            else:
                event_elo_text = f"{participant.elo_before} → {participant.elo_after}"
            
            # Format cluster ELO change if available
            cluster_elo_text = ""
            if participant.cluster_elo_before is not None and participant.cluster_elo_after is not None:
                if participant.cluster_elo_change != 0:
                    cluster_elo_text = f"{participant.cluster_elo_before} → {participant.cluster_elo_after} ("
                    if participant.cluster_elo_change > 0:
                        cluster_elo_text += f"+{participant.cluster_elo_change})"
                    else:
                        cluster_elo_text += f"{participant.cluster_elo_change})"
                else:
                    cluster_elo_text = f"{participant.cluster_elo_before} → {participant.cluster_elo_after}"
            
            # Build the result line
            if cluster_elo_text:
                results_text.append(
                    f"**#{participant.placement}** - {participant.player.display_name}\n"
                    f"  Event ELO: {event_elo_text}\n"
                    f"  Cluster ELO: {cluster_elo_text}"
                )
            else:
                # Fallback to original format if cluster ELO not available
                results_text.append(
                    f"**#{participant.placement}** - {participant.player.display_name} ({event_elo_text})"
                )
        
        embed.add_field(
            name="Final Standings",
            value="\n".join(results_text),
            inline=False
        )
        
        embed.add_field(
            name="Match Format",
            value=match.match_format.value,
            inline=True
        )
        
        embed.add_field(
            name="Event",
            value=match.event.name,
            inline=True
        )
        
        if force_completion:
            embed.set_footer(text="🛡️ Recorded via Owner Force - Event and Cluster ELO ratings have been updated")
        else:
            embed.set_footer(text="✨ Recorded via Modal UI - Event and Cluster ELO ratings have been updated")
        
        return embed


# ============================================================================
# Phase B: Match Confirmation UI System
# ============================================================================

class MatchConfirmationView(discord.ui.View):
    """
    Confirmation view for proposed match results requiring participant approval.
    
    Displays confirmation buttons for all participants to approve or reject
    proposed match results before they become final.
    """
    
    def __init__(self, proposal_id: int, match_ops: MatchOperations, cog=None, timeout: float = 86400.0):
        """
        Initialize confirmation view.
        
        Args:
            proposal_id: ID of the MatchResultProposal to confirm
            match_ops: MatchOperations instance for database operations
            cog: Optional MatchCommandsCog instance for streak updates
            timeout: View timeout in seconds (default 24 hours)
        """
        super().__init__(timeout=timeout)
        self.proposal_id = proposal_id
        self.match_ops = match_ops
        self.cog = cog
        self.logger = setup_logger(f"{__name__}.MatchConfirmationView")
    
    @discord.ui.button(label="✅ Confirm", style=discord.ButtonStyle.green, custom_id="confirm_results")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle confirmation button click"""
        await self._handle_confirmation(interaction, ConfirmationStatus.CONFIRMED)
    
    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.red, custom_id="reject_results")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle rejection button click"""
        await self._handle_confirmation(interaction, ConfirmationStatus.REJECTED)
    
    async def _handle_confirmation(self, interaction: discord.Interaction, status: ConfirmationStatus):
        """Handle confirmation or rejection response"""
        try:
            # Defer response to prevent timeout
            await interaction.response.defer()
            
            # Get proposal directly by ID with all relationships loaded
            proposal = await self.match_ops.get_proposal_by_id(self.proposal_id)
            if not proposal:
                await interaction.followup.send("❌ This proposal is no longer active or has expired.", ephemeral=True)
                self.stop()  # Stop the view since proposal is invalid
                return
            
            # Validate user is a participant
            user_discord_id = interaction.user.id
            match = proposal.match
            participant_discord_ids = [p.player.discord_id for p in match.participants]
            
            if user_discord_id not in participant_discord_ids:
                await interaction.followup.send("❌ You are not a participant in this match.", ephemeral=True)
                return
            
            # Record confirmation with defensive participant lookup
            player_id = next(
                (p.player.id for p in match.participants if p.player.discord_id == user_discord_id), 
                None
            )
            if player_id is None:
                self.logger.error(f"Could not find player_id for Discord user {user_discord_id} in match {match.id}")
                await interaction.followup.send("❌ Error identifying you as a participant.", ephemeral=True)
                return
            
            # Race condition protection: Handle duplicate button clicks gracefully
            try:
                await self.match_ops.record_confirmation(
                    match_id=match.id,
                    player_id=player_id,
                    status=status,
                    discord_user_id=user_discord_id,
                    discord_message_id=interaction.message.id
                )
                
                # Send confirmation to user
                action = "confirmed" if status == ConfirmationStatus.CONFIRMED else "rejected"
                await interaction.followup.send(f"✅ You have {action} the match results.", ephemeral=True)
                
            except MatchStateError as e:
                if "already responded" in str(e):
                    # Extract actual status from error message
                    if "status: confirmed" in str(e):
                        actual_status = "confirmed"
                    elif "status: rejected" in str(e):
                        actual_status = "rejected"
                    else:
                        actual_status = "responded to"  # Fallback
                    
                    await interaction.followup.send(f"✅ You have already {actual_status} the match results.", ephemeral=True)
                    self.logger.info(f"Handled duplicate button click from user {user_discord_id} for match {match.id}")
                    return
                else:
                    # Other match state errors should still be treated as errors
                    raise
            
            # Check confirmation status (only if we successfully recorded)
            all_confirmed, confirmations = await self.match_ops.check_all_confirmed(match.id)
            
            # Check if any participant has rejected the proposal
            rejection = next((c for c in confirmations if c.status == ConfirmationStatus.REJECTED), None)

            if rejection:
                # A player has rejected. Terminate the proposal.
                rejecting_player = rejection.player
                reason = rejection.rejection_reason or "No reason provided"
                
                await self.match_ops.terminate_proposal(
                    match.id, 
                    f"Rejected by {rejecting_player.display_name}: {reason}"
                )
                
                # Show termination message
                embed = self._create_termination_embed(proposal, rejecting_player, reason)
                self.clear_items()  # Remove buttons
                await interaction.edit_original_response(embed=embed, view=self)
                self.stop()  # Stop the view since proposal is terminated
                return
            
            if all_confirmed:
                # Finalize results
                completed_match = await self.match_ops.finalize_confirmed_results(match.id)
                
                # Update streaks for all participants
                if self.cog:
                    await self.cog._update_participant_streaks(completed_match)
                
                # Update message with final results
                embed = await self._create_completed_embed(completed_match)
                self.clear_items()  # Remove buttons
                await interaction.edit_original_response(embed=embed, view=self)
                self.stop()  # Stop the view since match is finalized
                
            else:
                # Update message with current confirmation status using unified embed
                embed = self._create_unified_embed(proposal, confirmations)
                await interaction.edit_original_response(embed=embed, view=self)
            
        except Exception as e:
            self.logger.error(f"Error handling confirmation: {e}")
            await interaction.followup.send("❌ An error occurred. Please try again.", ephemeral=True)
    
    def _create_unified_embed(self, proposal, confirmations, results_data=None) -> discord.Embed:
        """Create unified embed showing both proposed results and confirmation status"""
        # Add match context for clarity
        match_context = format_match_context(proposal.match)
        
        embed = discord.Embed(
            title="📋 Match Results - Awaiting Confirmation",
            description=f"{match_context}\n**Match ID:** {proposal.match_id}",
            color=discord.Color.orange()
        )
        
        # Add proposer info
        if hasattr(proposal, 'proposer') and proposal.proposer:
            embed.description += f"\n**Proposer:** <@{proposal.proposer.discord_id}>"
        
        # Show proposed results (placements)
        if results_data:
            # Use the original results data from initial creation
            sorted_results = sorted(results_data, key=lambda r: r["placement"])
            results_text = []
            for result in sorted_results:
                # Find the player from match participants
                player = next(
                    (p.player for p in proposal.match.participants if p.player.id == result["player_id"]), 
                    None
                )
                if player:
                    results_text.append(f"{result['placement']}. {player.display_name}")
                else:
                    results_text.append(f"{result['placement']}. Player ID {result['player_id']}")
            
            embed.add_field(
                name="Proposed Results",
                value="\n".join(results_text),
                inline=False
            )
        else:
            # Fallback: extract from proposal JSON if results_data not available
            try:
                results = json.loads(proposal.proposed_results)
                sorted_results = sorted(results, key=lambda r: r["placement"])
                results_text = []
                for result in sorted_results:
                    # Find the player from match participants
                    player = next(
                        (p.player for p in proposal.match.participants if p.player.id == result["player_id"]), 
                        None
                    )
                    if player:
                        results_text.append(f"{result['placement']}. {player.display_name}")
                    else:
                        results_text.append(f"{result['placement']}. Player ID {result['player_id']}")
                
                embed.add_field(
                    name="Proposed Results",
                    value="\n".join(results_text),
                    inline=False
                )
            except Exception as e:
                self.logger.warning(f"Could not parse proposed_results for proposal {proposal.id}: {e}")
        
        # Show confirmation status
        status_lines = []
        for confirmation in confirmations:
            player_name = confirmation.player.display_name
            if confirmation.status == ConfirmationStatus.CONFIRMED:
                if confirmation.player_id == proposal.proposer_id:
                    status_lines.append(f"✅ {player_name} (Proposer)")
                else:
                    status_lines.append(f"✅ {player_name}")
            elif confirmation.status == ConfirmationStatus.REJECTED:
                status_lines.append(f"❌ {player_name}")
            else:
                status_lines.append(f"⏳ {player_name}")
        
        embed.add_field(
            name="Confirmation Status",
            value="\n".join(status_lines),
            inline=False
        )
        
        # Add footer with expiration info
        embed.add_field(
            name="⏰ Waiting for Confirmation",
            value="All participants must confirm or reject these results.\n"
                  "Proposal expires in 24 hours if not all players respond.",
            inline=False
        )
        
        embed.set_footer(text=f"Proposal ID: {proposal.id}")
        
        return embed
    
    async def _create_completed_embed(self, match: Match) -> discord.Embed:
        """Create embed for completed match"""
        # Add match context for clarity
        match_context = format_match_context(match)
        
        embed = discord.Embed(
            title="✅ Match Results Confirmed!",
            description=f"{match_context}\n**Match ID:** {match.id}",
            color=discord.Color.green()
        )
        
        # Sort results by placement
        sorted_results = sorted(match.participants, key=lambda r: r.placement)
        
        # Build results display with both event and cluster ELO
        results_text = []
        for result in sorted_results:
            # Format event ELO change
            if result.elo_change != 0:
                event_elo_text = f"{result.elo_before} → {result.elo_after} ("
                if result.elo_change > 0:
                    event_elo_text += f"+{result.elo_change})"
                else:
                    event_elo_text += f"{result.elo_change})"
            else:
                event_elo_text = f"{result.elo_before} → {result.elo_after}"
            
            # Format cluster ELO change if available
            cluster_elo_text = ""
            if result.cluster_elo_before is not None and result.cluster_elo_after is not None:
                if result.cluster_elo_change != 0:
                    cluster_elo_text = f"{result.cluster_elo_before} → {result.cluster_elo_after} ("
                    if result.cluster_elo_change > 0:
                        cluster_elo_text += f"+{result.cluster_elo_change})"
                    else:
                        cluster_elo_text += f"{result.cluster_elo_change})"
                else:
                    cluster_elo_text = f"{result.cluster_elo_before} → {result.cluster_elo_after}"
            
            # Build the result line
            if cluster_elo_text:
                results_text.append(
                    f"**#{result.placement}** - {result.player.display_name}\n"
                    f"  Event ELO: {event_elo_text}\n"
                    f"  Cluster ELO: {cluster_elo_text}"
                )
            else:
                # Fallback to original format if cluster ELO not available
                results_text.append(
                    f"**#{result.placement}** - {result.player.display_name} ({event_elo_text})"
                )
        
        embed.add_field(
            name="Final Standings",
            value="\n".join(results_text),
            inline=False
        )
        
        embed.set_footer(text="✨ Results confirmed by all participants - Event and Cluster ELO ratings updated")
        return embed
    
    def _create_termination_embed(self, proposal, rejecting_player: Optional[Player], reason: Optional[str]) -> discord.Embed:
        """Create embed for a rejected and terminated proposal"""
        embed = discord.Embed(
            title="❌ Match Proposal Rejected",
            description=f"The results proposal for **Match ID: {proposal.match_id}** has been rejected and is now void.",
            color=discord.Color.red()
        )
        
        if rejecting_player:
            embed.add_field(
                name="Rejected By",
                value=f"{rejecting_player.display_name}",
                inline=True
            )
        

        embed.add_field(
            name="Next Steps",
            value=(
                "The match status has been reset to **Pending**.\n"
                "A new result proposal can be submitted using the `/match-report` command."
            ),
            inline=False
        )
        embed.set_footer(text="This proposal is no longer active.")
        return embed
    
    async def on_timeout(self):
        """Handle view timeout"""
        try:
            # Clean up expired proposal
            await self.match_ops.cleanup_expired_proposals()
            self.logger.info(f"Cleaned up expired proposal {self.proposal_id}")
        except Exception as e:
            self.logger.error(f"Error cleaning up expired proposal {self.proposal_id}: {e}")


class MatchCommandsCog(commands.Cog):
    """Commands for N-player match functionality - use /challenge for all match types"""
    
    def __init__(self, bot):
        self.bot = bot
        self.logger = setup_logger(__name__)
        # Dependency injection: Operations will be initialized when database is ready
        self.match_ops = None
        self.player_ops = None
        self.profile_service = None
        

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize all operations after bot and database are ready"""
        print(f"MatchCommandsCog: on_ready() called! bot.db = {self.bot.db}")
        if self.bot.db:
            self.match_ops = MatchOperations(self.bot.db, self.bot.config_service)
            self.player_ops = PlayerOperations(self.bot.db)
            # Initialize EloHierarchyService with caching wrapper
            self.elo_hierarchy_service = CachedEloHierarchyService(self.bot.db.session_factory, self.bot.config_service)
            # Initialize profile service with hierarchy service
            self.profile_service = ProfileService(self.bot.db.session_factory, self.bot.config_service, self.elo_hierarchy_service)
            print("MatchCommandsCog: All operations initialized successfully")
        else:
            print("MatchCommandsCog: Warning - Database not available")
    
    async def _update_participant_streaks(self, match: Match):
        """Update current streaks for all match participants and invalidate caches."""
        if not self.profile_service:
            self.logger.warning("ProfileService not available for streak updates")
            return
        
        # Use a new session for streak updates
        async with self.bot.db.get_session() as session:
            for participant in match.participants:
                try:
                    await self.profile_service.update_player_streak(participant.player_id, session)
                except Exception as e:
                    self.logger.error(f"Failed to update streak for player {participant.player_id}: {e}")
            
            # Commit all streak updates
            await session.commit()
        
        # Phase 2.4: Invalidate profile and hierarchy caches for all participants
        for participant in match.participants:
            self.profile_service.invalidate_cache(participant.player.discord_id)
            self.logger.debug(f"Invalidated cache for player {participant.player.discord_id}")
    
    def _check_match_permissions(self, match: Match, user: discord.User | discord.Member) -> tuple[bool, Optional[discord.Embed]]:
        """
        Check if user has permission to report match results.
        
        Args:
            match: Match object with participants loaded
            user: Discord user attempting to report results
            
        Returns:
            tuple: (is_authorized, error_embed_if_unauthorized)
        """
        # Get participant Discord IDs
        participant_ids = {p.player.discord_id for p in match.participants}
        
        # Check if user is bot owner (only owner has admin privileges)
        is_owner = is_user_bot_owner(user)
        
        # Check if user is a participant or owner
        if user.id in participant_ids or is_owner:
            return True, None
        
        # Create unauthorized error embed
        embed = discord.Embed(
            title="❌ Unauthorized",
            description="Only match participants or bot owner can report results.",
            color=discord.Color.red()
        )
        embed.add_field(
            name="Who can report?",
            value="• Players participating in this match\n• Bot owner",
            inline=False
        )
        
        return False, embed
    
    async def _parse_members_from_string(self, ctx, text: str) -> List[discord.Member]:
        """
        Robust member parsing for hybrid commands.
        
        Handles:
        - Discord mentions (@user)
        - User IDs (123456789) 
        - Usernames (JohnDoe)
        - Names with spaces ("John Doe")
        """
        if not text.strip():
            return []
        
        members = []
        converter = commands.MemberConverter()
        
        try:
            # Use shlex for robust splitting (handles quotes)
            potential_members = shlex.split(text)
        except ValueError:
            # Fallback for unmatched quotes
            potential_members = text.split()
        
        for arg in potential_members:
            try:
                member = await converter.convert(ctx, arg)
                if member not in members:  # Avoid duplicates
                    members.append(member)
            except commands.MemberNotFound:
                # Skip non-member arguments
                continue
        
        return members
    
    async def _parse_placements_from_string(self, ctx, text: str) -> dict[discord.Member, int]:
        """
        Parses a placement string like "@user1:1 @user2:2" into a dict.
        Handles mentions, IDs, and usernames for hybrid command compatibility.
        
        Supports flexible spacing around colons:
        - "@user:1" (standard format)
        - "@user :1" (space before colon)  
        - "@user: 1" (space after colon)
        - "@user : 1" (spaces around colon)
        """
        if not text.strip():
            return {}

        placements = {}
        converter = commands.MemberConverter()
        
        # Normalize spacing around colons to handle natural user input
        # Pattern handles: Discord mentions, quoted names with spaces, and regular usernames
        user_pattern = r'(<@!?\d+>|"[^"]+"|\'[^\']+\'|\S+)'
        full_pattern = rf'{user_pattern}\s*:\s*(\d+)'
        normalized_text = re.sub(full_pattern, r'\1:\2', text)
        
        try:
            potential_placements = shlex.split(normalized_text)
        except ValueError:
            # Fallback for unmatched quotes
            potential_placements = normalized_text.split()

        if not potential_placements:
            raise ValueError("No placement data provided. Please specify player placements.")

        for arg in potential_placements:
            parts = arg.rsplit(':', 1)
            if len(parts) != 2:
                raise ValueError(f"Invalid format for '{arg}'. Expected format is `player:placement`.")
            
            user_str, placement_str = parts
            
            try:
                member = await converter.convert(ctx, user_str.strip())
            except commands.MemberNotFound:
                raise ValueError(f"Could not find player: '{user_str.strip()}'")

            if member in placements:
                raise ValueError(f"Duplicate user: {member.display_name}")

            try:
                placement = int(placement_str)
                if placement < 1:
                    raise ValueError(f"Invalid placement number for {member.display_name}: '{placement_str}'. Must be a whole number > 0.")
            except (ValueError, TypeError):
                raise ValueError(f"Invalid placement number for {member.display_name}: '{placement_str}'. Must be a whole number > 0.")
            
            placements[member] = placement
        
        return placements
    
    async def _generate_placement_template(self, participants: List[MatchParticipant]) -> str:
        """
        Generate copy-paste template with participant names and underscores for placements.
        
        Creates a template like: "@Alice:_ @Bob:_ @Charlie:_" that users can easily
        copy and modify by replacing underscores with placement numbers.
        
        Args:
            participants: List of MatchParticipant objects
            
        Returns:
            String template ready for copying
            
        Raises:
            ValueError: If participants list is empty
        """
        if not participants:
            raise ValueError("No participants provided for template generation")
        
        template_parts = []
        for participant in participants:
            # Use Discord user ID for reliable parsing (works regardless of nicknames)
            user_id = participant.player.discord_id
            template_parts.append(f"<@{user_id}>:_")
        return " ".join(template_parts)
    
    async def _generate_example_placements(self, participants: List[MatchParticipant]) -> str:
        """
        Generate realistic example of filled placements using actual participant names.
        
        Creates a realistic example by shuffling placements to show users that
        order doesn't matter and demonstrate the final format.
        
        Args:
            participants: List of MatchParticipant objects
            
        Returns:
            String showing example filled placements
            
        Raises:
            ValueError: If participants list is empty
        """
        if not participants:
            raise ValueError("No participants provided for example generation")
        
        # Create shuffled placements to show order doesn't matter
        placements = list(range(1, len(participants) + 1))
        random.shuffle(placements)
        
        example_parts = []
        for i, participant in enumerate(participants):
            # Use Discord user ID for reliable parsing (works regardless of nicknames)
            user_id = participant.player.discord_id
            example_parts.append(f"<@{user_id}>:{placements[i]}")
        
        return " ".join(example_parts)
    
    @commands.command(name='match-test', aliases=['mtest'])
    async def test_match_integration(self, ctx):
        """Test command to validate cog loading and backend integration"""
        
        if not self.match_ops:
            embed = discord.Embed(
                title="❌ Integration Test Failed",
                description="MatchOperations backend not available",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
            
        try:
            # Test basic database connection through MatchOperations
            # This will verify that our integration works
            async with self.match_ops.db.get_session() as session:
                # Simple query to verify database connectivity
                result = await session.execute(text("SELECT 1"))
                test_value = result.scalar()
                
            embed = discord.Embed(
                title="✅ Integration Test Successful",
                description=f"MatchOperations backend is working correctly!\n"
                           f"Database connection verified (test value: {test_value})",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Backend Status",
                value="MatchOperations connected and operational",
                inline=False
            )
            embed.add_field(
                name="Next Steps",
                value="Ready for match reporting - use /challenge to create matches",
                inline=False
            )
            await ctx.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Integration Test Failed",
                description=f"Backend integration error: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            # Log the full error for debugging
            self.logger.error(f"MatchCommandsCog test error: {e}", exc_info=True)
    
    @commands.hybrid_command(name="ping", description="Test slash command infrastructure")
    async def ping(self, ctx):
        """Test command to verify slash command infrastructure is working"""
        embed = discord.Embed(
            title="🏓 Pong!",
            description="Slash commands are working correctly!",
            color=discord.Color.green()
        )
        embed.add_field(
            name="Command Type",
            value="✅ Hybrid Command (works as !ping and /ping)",
            inline=False
        )
        embed.add_field(
            name="Infrastructure Status", 
            value="✅ app_commands integration successful",
            inline=False
        )
        await ctx.send(embed=embed)
    
    
    @commands.hybrid_command(name='match-report', description="Report match results with placements")
    @app_commands.describe(
        match_id="Match ID to report results for",
        placements="Player placements (format: @user1:1 @user2:2 @user3:3) - Optional for slash commands with ≤5 players",
        force="Owner only: Skip confirmation and complete match immediately"
    )
    async def report_match_results(self, ctx, match_id: int, *, placements: str = "", force: bool = False):
        """
        Report match results with placement for each player
        
        Usage:
        - Prefix: !match-report <match_id> @user1:1 @user2:2 @user3:3 ...
        - Slash: /match-report match_id:42 placements:@user1:1 @user2:2 @user3:3 ...
        
        Example: !match-report 42 @Alice:1 @Bob:2 @Charlie:3
        """
        
        # Validate match operations available
        if not self.match_ops:
            embed = discord.Embed(
                title="❌ Match System Unavailable",
                description="Match operations are not initialized. Please try again later.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # ============================================================================
        # Phase 2.2a: Modal Logic for Slash Commands with Empty Placements
        # ============================================================================
        
        # Check if this is a slash command with empty placements (modal opportunity)
        if not placements and ctx.interaction:
            try:
                # Query match with participants for modal generation
                match = await self.match_ops.get_match_with_participants(match_id)
                
                if not match:
                    embed = discord.Embed(
                        title="❌ Match Not Found",
                        description=f"Match {match_id} could not be found.",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
                
                # Validate match status
                if match.status != MatchStatus.PENDING:
                    embed = discord.Embed(
                        title="❌ Match Already Completed",
                        description=f"Match {match_id} has already been completed or cancelled.",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=embed)
                    return
                
                # ============================================================================
                # Phase A: Permission Check - Only participants or admin can report
                # ============================================================================
                is_authorized, permission_error = self._check_match_permissions(match, ctx.author)
                if not is_authorized:
                    await ctx.send(embed=permission_error)
                    return
                
                # Check participant count for modal eligibility
                participant_count = len(match.participants)
                
                if participant_count <= 5:
                    # ============================================================================
                    # Phase 2.2a: Show Modal for ≤5 Players
                    # ============================================================================
                    try:
                        modal = PlacementModal(self, match_id, match.participants, self.match_ops, force)
                        await ctx.interaction.response.send_modal(modal)
                        self.logger.info(f"Modal: Displayed placement modal for Match {match_id} with {participant_count} participants")
                        return  # Modal handles the rest
                    except Exception as e:
                        self.logger.error(f"Modal: Failed to display modal for Match {match_id}: {e}")
                        embed = discord.Embed(
                            title="❌ Modal Error",
                            description="Failed to display placement form. Please use string format instead.",
                            color=discord.Color.red()
                        )
                        embed.add_field(
                            name="Format",
                            value=f"`/match-report match_id:{match_id} placements:@user1:1 @user2:2 ...`",
                            inline=False
                        )
                        await ctx.send(embed=embed)
                        return
                
                elif participant_count <= 10:
                    # ============================================================================
                    # Phase 2.2b: Enhanced Guidance for 6-8 Players
                    # ============================================================================
                    
                    # Generate dynamic template and example using actual participant names
                    template = await self._generate_placement_template(match.participants)
                    example = await self._generate_example_placements(match.participants)
                    
                    # Create player reference list with raw UIDs
                    player_list = []
                    for participant in match.participants:
                        player_name = participant.player.display_name
                        user_id = participant.player.discord_id
                        player_list.append(f"`<@{user_id}>` = {player_name}")
                    
                    # Create clean guidance embed with step-by-step instructions
                    embed = discord.Embed(
                        title=f"Match {match_id} - Report Placements",
                        description=f"This match has **{participant_count} players**. Use the template below to report results.",
                        color=discord.Color.blue()
                    )
                    
                    # Player reference with raw UIDs
                    embed.add_field(
                        name="Players in this Match",
                        value="\n".join(player_list),
                        inline=False
                    )
                    
                    # Step 1: Copy-ready template
                    embed.add_field(
                        name="1. Copy This Template",
                        value=f"```\n{template}\n```",
                        inline=False
                    )
                    
                    # Step 2: Instructions for editing
                    embed.add_field(
                        name="2. Edit & Paste",
                        value=(
                            f"Replace each `_` with the player's placement (e.g., 1, 2, 3...).\n"
                            f"Then, paste it into the `placements` option of the command:\n"
                            f"`/match-report match_id:{match_id} placements:[your edited text]`"
                        ),
                        inline=False
                    )
                    
                    # Step 3: Realistic example
                    embed.add_field(
                        name="Example",
                        value=f"Your final command might look like this:\n```\n/match-report match_id:{match_id} placements:{example}\n```",
                        inline=False
                    )
                    
                    # Helpful tips
                    embed.add_field(
                        name="Tips",
                        value=(
                            "• Player order doesn't matter - use any sequence\n"
                            "• Spaces around colons are OK: `<@123456> : 1`\n"
                            "• You can also just ping the players instead of using the UIDs\n"
                            "• Example: /match-report match_id: ## placements: @Alex:1 @Jacob:2 @Charlie:3 @Clinston:4 @Ryan:5 @Michael:6"
                        ),
                        inline=False
                    )
                    
                    embed.set_footer(
                        text="Tip: The template uses Discord mentions for reliable parsing."
                    )
                    
                    await ctx.send(embed=embed)
                    return
                
                else:
                    # ============================================================================
                    # Standard Help for 9+ Players
                    # ============================================================================
                    embed = discord.Embed(
                        title="📝 Large Match Format",
                        description=f"This match has {participant_count} players. Use string format:",
                        color=discord.Color.blue()
                    )
                    embed.add_field(
                        name="Format",
                        value=f"`/match-report match_id:{match_id} placements:@user1:1 @user2:2 @user3:3 ...`",
                        inline=False
                    )
                    await ctx.send(embed=embed)
                    return
                    
            except Exception as e:
                self.logger.error(f"Modal: Failed to process match {match_id} for modal logic: {e}")
                # Fall through to string parsing logic
        
        # ============================================================================
        # Phase 2.1: String Parsing Logic (Existing + Improved)
        # ============================================================================
        
        # Load match and check permissions for string parsing path
        # Note: This covers cases where placements are provided directly (prefix commands 
        # or slash commands with placements parameter), bypassing the modal logic above
        match = await self.match_ops.get_match_with_participants(match_id)
        
        if not match:
            embed = discord.Embed(
                title="❌ Match Not Found",
                description=f"Match {match_id} could not be found.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Validate match status
        if match.status != MatchStatus.PENDING:
            embed = discord.Embed(
                title="❌ Match Already Completed",
                description=f"Match {match_id} has already been completed or cancelled.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Check permissions
        is_authorized, permission_error = self._check_match_permissions(match, ctx.author)
        if not is_authorized:
            await ctx.send(embed=permission_error)
            return
        
        # Parse placement data using the robust helper
        try:
            placement_data_by_member = await self._parse_placements_from_string(ctx, placements)
            
            if not placement_data_by_member:
                raise ValueError("No users mentioned. Please specify their placements in the format `player:placement`.")

            mentioned_users = list(placement_data_by_member.keys())
            placement_data = {user.id: placement for user, placement in placement_data_by_member.items()}

        except ValueError as e:
            # Enhanced error handling with smart recovery suggestions
            embed = discord.Embed(
                title="❌ Invalid Placement Data",
                description=str(e),
                color=discord.Color.red()
            )
            
            # Try to provide helpful template if we can get match info
            try:
                error_match = await self.match_ops.get_match_with_participants(match_id)
                if error_match and len(error_match.participants) <= 8:
                    # Generate corrected template for the user
                    corrected_template = await self._generate_placement_template(error_match.participants)
                    
                    embed.add_field(
                        name="Try This Template",
                        value=f"```\n{corrected_template}\n```",
                        inline=False
                    )
                    embed.add_field(
                        name="Instructions",
                        value="Copy the template above and replace each `_` with placement numbers (1, 2, 3, etc.)",
                        inline=False
                    )
                else:
                    # Fallback for larger matches
                    embed.add_field(
                        name="Format",
                        value="Use format: `@user:placement` (spaces around : are OK)\nExamples:\n• `!match-report 123 @Alice:1 @Bob :2`\n• `/match-report match_id:123 placements:@Alice:1 @Bob: 2`",
                        inline=False
                    )
            except Exception as secondary_error:
                # Fallback error handling - log the secondary error for debugging
                self.logger.warning(f"Failed to generate error template for match {match_id}: {secondary_error}")
                embed.add_field(
                    name="Format",
                    value="Use format: `@user:placement` (spaces around : are OK)\nExamples:\n• `!match-report 123 @Alice:1 @Bob :2`\n• `/match-report match_id:123 placements:@Alice:1 @Bob: 2`",
                    inline=False
                )
            
            await ctx.send(embed=embed)
            return
        
        # Validate all placements are unique
        placements_list = list(placement_data.values())
        if len(set(placements_list)) != len(placements_list):
            embed = discord.Embed(
                title="❌ Duplicate Placements",
                description="Each player must have a unique placement.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Send processing message
        processing_embed = discord.Embed(
            title="🔄 Processing Match Results...",
            description=f"Recording results for Match {match_id}...",
            color=discord.Color.blue()
        )
        processing_message = await ctx.send(embed=processing_embed)
        
        try:
            # Convert Discord users to Player IDs
            players = await self.player_ops.bulk_get_or_create_players(mentioned_users)
            
            # Build results list with correct API structure
            results_list = []
            for i, user in enumerate(mentioned_users):
                player_id = players[i].id
                placement = placement_data[user.id]
                results_list.append({
                    "player_id": player_id,
                    "placement": placement
                })
            
            # Branch logic: Force completion vs Proposal workflow
            if force:
                # Owner force completion - check permissions (bot owner only)
                if not is_user_bot_owner(ctx.author):
                    embed = discord.Embed(
                        title="❌ Insufficient Permissions",
                        description="Only the bot owner can use the `force` parameter.",
                        color=discord.Color.red()
                    )
                    await processing_message.edit(embed=embed)
                    return
                
                # Direct completion for admin override
                match = await self.match_ops.complete_match_with_results(
                    match_id=match_id,
                    results=results_list
                )
                
                # Update streaks for all participants
                await self._update_participant_streaks(match)
                
                # Success response will be handled below with admin indication
                
            else:
                # Normal flow: Create proposal for confirmation
                # Get the proposer (command author)
                proposer_player = await self.player_ops.get_or_create_player(ctx.author)
                
                # Create result proposal
                proposal = await self.match_ops.create_result_proposal(
                    match_id=match_id,
                    proposer_id=proposer_player.id,
                    results=results_list,
                    expires_in_hours=24  # 24 hour expiration
                )
                
                # Create confirmation view with buttons
                view = MatchConfirmationView(proposal.id, self.match_ops, self)
                
                # Get current confirmation status (proposer is auto-confirmed)
                _, confirmations = await self.match_ops.check_all_confirmed(match_id)
                
                # Build unified embed showing both results and confirmation status
                embed = view._create_unified_embed(proposal, confirmations, results_list)
                
                # Send proposal with confirmation buttons
                await processing_message.edit(embed=embed, view=view)
                return  # Exit early for proposal flow
            
            # Build success response (for force=True path only)
            title = "✅ Match Results Recorded!"
            if force:
                title += " (Owner Override)"
            
            embed = discord.Embed(
                title=title,
                description=f"**Match ID:** {match.id}",
                color=discord.Color.green()
            )
            
            # Sort results by placement
            sorted_results = sorted(match.participants, key=lambda r: r.placement)
            
            # Create lookup dictionary for O(1) user access 
            discord_id_to_user = {user.id: user for user in mentioned_users}
            
            # Build results display
            results_text = []
            for result in sorted_results:
                user = discord_id_to_user.get(result.player.discord_id)
                
                if result.elo_change != 0:
                    elo_text = f" ({result.elo_before} → {result.elo_after}, "
                    if result.elo_change > 0:
                        elo_text += f"+{result.elo_change})"
                    else:
                        elo_text += f"{result.elo_change})"
                else:
                    elo_text = f" ({result.elo_before} → {result.elo_after})"
                
                results_text.append(
                    f"**#{result.placement}** - {user.display_name if user else result.player.display_name}{elo_text}"
                )
            
            embed.add_field(
                name="Final Standings",
                value="\n".join(results_text),
                inline=False
            )
            
            embed.add_field(
                name="Match Format",
                value=match.match_format.value,
                inline=True
            )
            
            embed.add_field(
                name="Event",
                value=f"{match.event.name}",
                inline=True
            )
            
            embed.set_footer(text="Event and Cluster ELO ratings have been updated")
            
            await processing_message.edit(embed=embed)
            
        except MatchOperationError as e:
            self.logger.error(f"Failed to record match results: {e}")
            embed = discord.Embed(
                title="❌ Failed to Record Results",
                description=str(e),
                color=discord.Color.red()
            )
            await processing_message.edit(embed=embed)
            # Auto-delete error message after 10 seconds
            await asyncio.sleep(10)
            await processing_message.delete()
            
        except Exception as e:
            self.logger.error(f"Unexpected error recording match results: {e}")
            embed = discord.Embed(
                title="❌ Unexpected Error",
                description="An unexpected error occurred while recording results.",
                color=discord.Color.red()
            )
            await processing_message.edit(embed=embed)
            # Auto-delete error message after 10 seconds
            await asyncio.sleep(10)
            await processing_message.delete()
    
    @commands.hybrid_command(name='active-matches', description="View your ongoing matches")
    async def active_matches(self, ctx):
        """
        Display all active matches where you are a participant.
        
        Shows matches with status:
        - PENDING: Match created, waiting to start
        - ACTIVE: Match in progress
        - AWAITING_CONFIRMATION: Results submitted, awaiting confirmation
        
        Phase 2.4.4 Implementation with performance optimizations
        """
        
        # Handle both slash and prefix commands
        if isinstance(ctx, discord.Interaction):
            # Slash command - defer response since we'll be doing database queries
            await ctx.response.defer()
            user = ctx.user
            send_func = ctx.followup.send
        else:
            # Prefix command (Context)
            user = ctx.author
            send_func = ctx.send
        
        # Validate match operations available
        if not self.match_ops:
            embed = discord.Embed(
                title="❌ Match System Unavailable",
                description="Match operations are not initialized. Please try again later.",
                color=discord.Color.red()
            )
            await send_func(embed=embed, ephemeral=True if isinstance(ctx, discord.Interaction) else False)
            return
        
        try:
            # Query active matches with Discord embed limit (25 fields max)
            matches = await self.match_ops.get_active_matches_for_player(
                player_discord_id=user.id,
                limit=25  # Discord embed field limit
            )
            
            # Create response embed
            embed = self._create_active_matches_embed(matches, user)
            await send_func(embed=embed)
            
        except Exception as e:
            self.logger.error(f"Error in active-matches command: {e}", exc_info=True)
            
            error_embed = discord.Embed(
                title="❌ Error Loading Active Matches",
                description="An error occurred while retrieving your active matches. Please try again later.",
                color=discord.Color.red()
            )
            await send_func(embed=error_embed, ephemeral=True if isinstance(ctx, discord.Interaction) else False)
    
    def _create_active_matches_embed(self, matches: List[Match], user: discord.User) -> discord.Embed:
        """
        Create an embed displaying active matches with expert-validated UX design.
        
        Handles Discord's 25-field embed limit and provides status-specific action hints.
        
        Args:
            matches: List of active Match objects (already limited to ≤25)
            user: Discord user to highlight in participant lists
            
        Returns:
            Formatted Discord embed
        """
        embed = discord.Embed(
            title="🎮 Your Active Matches",
            color=discord.Color.blue()
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        
        if not matches:
            embed.description = "You have no active matches at the moment."
            embed.add_field(
                name="💡 Start a Match",
                value="Use `/challenge` to invite players to a new match!",
                inline=False
            )
            embed.color = discord.Color.greyple()
            return embed
        
        # Show match count
        embed.description = f"You have {len(matches)} active match{'es' if len(matches) != 1 else ''}."
        
        for match in matches:
            # Get status emoji
            status_emoji = {
                MatchStatus.PENDING: "⏳",
                MatchStatus.ACTIVE: "⚔️", 
                MatchStatus.AWAITING_CONFIRMATION: "⚖️"
            }.get(match.status, "❓")
            
            # Build compact participant list
            participant_names = []
            for p in match.participants[:3]:  # Show first 3 participants
                if p.player is None:
                    participant_names.append("Unknown")
                    continue
                name = p.player.username or p.player.display_name or f"Player{p.player.id}"
                if p.player.discord_id == user.id:
                    name = f"**{name}**"  # Bold the current user
                participant_names.append(name)
            
            if len(match.participants) > 3:
                participant_names.append(f"+{len(match.participants)-3} more")
            
            participants_text = ", ".join(participant_names)
            
            # Build compact location
            if match.event and match.event.cluster:
                location = f"{match.event.cluster.name} → {match.event.name}"
            elif match.event:
                location = match.event.name
            else:
                location = "Unknown Event"
            
            # Simple field format
            embed.add_field(
                name=f"{status_emoji} Match {match.id} • {match.match_format.value.upper()}",
                value=f"**{location}**\n{participants_text}",
                inline=False
            )
        
        embed.set_footer(text="💡 Match IDs are needed for reporting results")
        return embed
    
    @commands.command(name='match-help')
    async def match_help(self, ctx):
        """Show available match commands and their status"""
        
        embed = discord.Embed(
            title="🎯 Match Commands",
            description="N-Player match functionality - use /challenge to create matches",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🧪 Testing",
            value="`!match-test` - Test backend integration",
            inline=False
        )
        
        embed.add_field(
            name="✅ Available Commands",
            value=(
                "`!match-report <id> @user1:1 @user2:2 ...` - Record match results\n"
                "Use `/challenge` command to create all match types (1v1, FFA, Team)"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📈 Development Status",
            value="**Phase 2A2.5 Subphase 1**: Foundation ✅\n"
                  "**Phase 2A2.5 Subphase 2**: Match Integration ✅\n"
                  "**Phase 2A2.5 Subphase 3**: Testing & Polish 🚧",
            inline=False
        )
        
        embed.add_field(
            name="💡 Tips",
            value="• Players are auto-registered when mentioned\n"
                  "• Use /challenge command to create all match types\n"
                  "• Match IDs are provided for result reporting",
            inline=False
        )
        
        await ctx.send(embed=embed)


async def setup(bot):
    """Setup function to load the cog"""
    await bot.add_cog(MatchCommandsCog(bot))