"""
Housekeeping Cog - Background Tasks & Admin Commands

Handles background maintenance tasks including challenge cleanup,
database optimization, and periodic health checks.
Also provides admin commands for challenge management.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional
from datetime import datetime, timezone

from bot.database.database import Database
from bot.database.models import Challenge, ChallengeStatus, Match, MatchStatus
from bot.operations.challenge_operations import ChallengeOperations
from bot.database.match_operations import MatchOperations
from bot.ui.admin_confirmation_modal import AdminConfirmationModal
from bot.utils.logger import setup_logger
from bot.config import Config

logger = setup_logger(__name__)


class HousekeepingCog(commands.Cog):
    """Background maintenance and cleanup tasks"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db: Database = bot.db
        self.challenge_ops: Optional[ChallengeOperations] = None
        self.match_ops: Optional[MatchOperations] = None
        self.logger = logger
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize operations and start background tasks after bot is ready"""
        if self.bot.db:
            self.challenge_ops = ChallengeOperations(self.bot.db)
            self.match_ops = MatchOperations(self.bot.db, self.bot.config_service)
            self.cleanup_expired_challenges.start()
            self.logger.info("HousekeepingCog: Background tasks started")
        else:
            self.logger.error("HousekeepingCog: Database not available")
    
    def cog_unload(self):
        """Stop background tasks when cog is unloaded"""
        self.cleanup_expired_challenges.cancel()
        self.logger.info("HousekeepingCog: Background tasks stopped")
    
    @tasks.loop(hours=1)
    async def cleanup_expired_challenges(self):
        """Background task to clean up expired challenges every hour"""
        try:
            if not self.challenge_ops:
                return
            
            count = await self.challenge_ops.cleanup_expired_challenges()
            if count > 0:
                self.logger.info(f"Cleaned up {count} expired challenges")
                
        except Exception as e:
            self.logger.error(f"Error in challenge cleanup task: {e}", exc_info=True)
    
    @cleanup_expired_challenges.before_loop
    async def before_cleanup_task(self):
        """Wait for bot to be ready before starting cleanup task"""
        await self.bot.wait_until_ready()
    
    @commands.command(name="cleanup_challenges")
    @commands.is_owner()
    async def manual_cleanup(self, ctx):
        """Manual command to trigger challenge cleanup (owner only)"""
        try:
            if not self.challenge_ops:
                await ctx.send("❌ Challenge operations not available.")
                return
            
            count = await self.challenge_ops.cleanup_expired_challenges()
            await ctx.send(f"✅ Cleaned up {count} expired challenges.")
            
        except Exception as e:
            self.logger.error(f"Manual cleanup error: {e}", exc_info=True)
            await ctx.send(f"❌ Cleanup failed: {str(e)}")
    
    @app_commands.command(
        name="admin-cleanup-challenges",
        description="Clean up expired challenges (Owner only)"
    )
    async def admin_cleanup_challenges(self, interaction: discord.Interaction):
        """Slash command to clean up expired challenges"""
        # Check if user is bot owner
        if interaction.user.id != Config.OWNER_DISCORD_ID:
            await interaction.response.send_message(
                "❌ **Access Denied**\nThis command is restricted to the bot owner.",
                ephemeral=True
            )
            return
        
        try:
            if not self.challenge_ops:
                await interaction.response.send_message(
                    "❌ Challenge operations not available.",
                    ephemeral=True
                )
                return
            
            await interaction.response.defer(ephemeral=True)
            
            count = await self.challenge_ops.cleanup_expired_challenges()
            
            embed = discord.Embed(
                title="✅ Cleanup Complete",
                description=f"Successfully cleaned up **{count}** expired challenges.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            
            if count == 0:
                embed.description = "No expired challenges found to clean up."
                embed.color = discord.Color.blue()
            
            await interaction.followup.send(embed=embed)
            
            # Log admin action
            self.logger.info(
                f"Admin cleanup executed by {interaction.user.id} ({interaction.user.name}): "
                f"{count} challenges cleaned"
            )
            
        except Exception as e:
            self.logger.error(f"Admin cleanup error: {e}", exc_info=True)
            
            error_embed = discord.Embed(
                title="❌ Cleanup Failed",
                description=f"An error occurred during cleanup: {str(e)}",
                color=discord.Color.red()
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
    @app_commands.command(
        name="admin-clear-challenges",
        description="Clear ALL active challenges (Owner only - DESTRUCTIVE)"
    )
    async def admin_clear_challenges(self, interaction: discord.Interaction):
        """Slash command to clear all active challenges with confirmation"""
        # Check if user is bot owner
        if interaction.user.id != Config.OWNER_DISCORD_ID:
            await interaction.response.send_message(
                "❌ **Access Denied**\nThis command is restricted to the bot owner.",
                ephemeral=True
            )
            return
        
        try:
            if not self.challenge_ops:
                await interaction.response.send_message(
                    "❌ Challenge operations not available.",
                    ephemeral=True
                )
                return
            
            # Get current counts for preview
            async with self.db.get_session() as session:
                from sqlalchemy import select, func
                
                # Count active challenges by status
                pending_count = await session.scalar(
                    select(func.count(Challenge.id)).where(
                        Challenge.status == ChallengeStatus.PENDING
                    )
                )
                accepted_count = await session.scalar(
                    select(func.count(Challenge.id)).where(
                        Challenge.status == ChallengeStatus.ACCEPTED
                    )
                )
            
            total_count = (pending_count or 0) + (accepted_count or 0)
            
            if total_count == 0:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="ℹ️ No Active Challenges",
                        description="There are no active challenges to clear.",
                        color=discord.Color.blue()
                    ),
                    ephemeral=True
                )
                return
            
            # Create warning embed with confirmation button
            warning_embed = discord.Embed(
                title="⚠️ **DESTRUCTIVE OPERATION WARNING**",
                description=(
                    f"You are about to **permanently delete** {total_count} active challenges:\n\n"
                    f"• **{pending_count or 0}** PENDING challenges\n"
                    f"• **{accepted_count or 0}** ACCEPTED challenges\n\n"
                    f"**This action cannot be undone!**\n"
                    f"All challenge participants and data will be permanently removed."
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            
            warning_embed.set_footer(text="Click 'Proceed' to continue with confirmation")
            
            # Create confirmation view with button
            view = AdminClearConfirmationView(self.challenge_ops, total_count)
            
            await interaction.response.send_message(
                embed=warning_embed,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Admin clear challenges error: {e}", exc_info=True)
            
            error_embed = discord.Embed(
                title="❌ Command Failed",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
    # ============================================================================
    # Admin Match Management Commands
    # ============================================================================
    
    @app_commands.command(
        name="admin-clear-matches",
        description="Clear ALL active matches (Owner only - DESTRUCTIVE)"
    )
    async def admin_clear_matches(self, interaction: discord.Interaction):
        """Slash command to clear all active matches with confirmation"""
        # Check if user is bot owner
        if interaction.user.id != Config.OWNER_DISCORD_ID:
            await interaction.response.send_message(
                "❌ **Access Denied**\nThis command is restricted to the bot owner.",
                ephemeral=True
            )
            return
        
        try:
            if not self.match_ops:
                await interaction.response.send_message(
                    "❌ Match operations not available.",
                    ephemeral=True
                )
                return
            
            # Get current counts for preview
            async with self.db.get_session() as session:
                from sqlalchemy import select, func
                
                # Count active matches by status
                pending_count = await session.scalar(
                    select(func.count(Match.id)).where(
                        Match.status == MatchStatus.PENDING
                    )
                )
                active_count = await session.scalar(
                    select(func.count(Match.id)).where(
                        Match.status == MatchStatus.ACTIVE
                    )
                )
                awaiting_count = await session.scalar(
                    select(func.count(Match.id)).where(
                        Match.status == MatchStatus.AWAITING_CONFIRMATION
                    )
                )
            
            total_count = (pending_count or 0) + (active_count or 0) + (awaiting_count or 0)
            
            if total_count == 0:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="ℹ️ No Active Matches",
                        description="There are no active matches to clear.",
                        color=discord.Color.blue()
                    ),
                    ephemeral=True
                )
                return
            
            # Create warning embed with confirmation button
            warning_embed = discord.Embed(
                title="⚠️ **DESTRUCTIVE OPERATION WARNING**",
                description=(
                    f"You are about to **permanently delete** {total_count} active matches:\n\n"
                    f"• **{pending_count or 0}** PENDING matches\n"
                    f"• **{active_count or 0}** ACTIVE matches\n"
                    f"• **{awaiting_count or 0}** AWAITING_CONFIRMATION matches\n\n"
                    f"**This action cannot be undone!**\n"
                    f"All match participants and data will be permanently removed."
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            
            warning_embed.set_footer(text="Click 'Proceed' to continue with confirmation")
            
            # Create confirmation view with button
            view = AdminClearMatchesConfirmationView(self.match_ops, total_count)
            
            await interaction.response.send_message(
                embed=warning_embed,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Admin clear matches error: {e}", exc_info=True)
            
            error_embed = discord.Embed(
                title="❌ Clear Matches Failed",
                description=f"An error occurred during setup: {str(e)}",
                color=discord.Color.red()
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
    @app_commands.command(
        name="admin-clear-match",
        description="Clear a specific match by ID (Owner only - DESTRUCTIVE)"
    )
    @app_commands.describe(match_id="ID of the match to delete")
    async def admin_clear_match(self, interaction: discord.Interaction, match_id: int):
        """Slash command to clear a specific match by ID with confirmation"""
        # Check if user is bot owner
        if interaction.user.id != Config.OWNER_DISCORD_ID:
            await interaction.response.send_message(
                "❌ **Access Denied**\nThis command is restricted to the bot owner.",
                ephemeral=True
            )
            return
        
        try:
            if not self.match_ops:
                await interaction.response.send_message(
                    "❌ Match operations not available.",
                    ephemeral=True
                )
                return
            
            # Check if match exists
            async with self.db.get_session() as session:
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                
                match_stmt = (
                    select(Match)
                    .options(
                        selectinload(Match.event),
                        selectinload(Match.participants)
                    )
                    .where(Match.id == match_id)
                )
                match_result = await session.execute(match_stmt)
                match = match_result.scalar_one_or_none()
                
                if not match:
                    await interaction.response.send_message(
                        embed=discord.Embed(
                            title="❌ Match Not Found",
                            description=f"No match found with ID: {match_id}",
                            color=discord.Color.red()
                        ),
                        ephemeral=True
                    )
                    return
            
            # Create warning embed with confirmation
            warning_embed = discord.Embed(
                title="⚠️ **DESTRUCTIVE OPERATION WARNING**",
                description=(
                    f"You are about to **permanently delete** Match ID {match_id}:\n\n"
                    f"• **Status:** {match.status.value.upper()}\n"
                    f"• **Event:** {match.event.name if match.event else 'Unknown'}\n"
                    f"• **Participants:** {len(match.participants) if match.participants else 0}\n\n"
                    f"**This action cannot be undone!**\n"
                    f"All match participants and data will be permanently removed."
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            
            warning_embed.set_footer(text="Click 'Proceed' to continue with confirmation")
            
            # Create confirmation view with button
            view = AdminClearSingleMatchConfirmationView(self.match_ops, match_id)
            
            await interaction.response.send_message(
                embed=warning_embed,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            self.logger.error(f"Admin clear match error: {e}", exc_info=True)
            
            error_embed = discord.Embed(
                title="❌ Clear Match Failed",
                description=f"An error occurred during setup: {str(e)}",
                color=discord.Color.red()
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)


class AdminClearConfirmationView(discord.ui.View):
    """Confirmation view for the clear challenges command"""
    
    def __init__(self, challenge_ops: ChallengeOperations, total_count: int):
        super().__init__(timeout=300)
        self.challenge_ops = challenge_ops
        self.total_count = total_count
    
    @discord.ui.button(
        label="Proceed with Deletion",
        style=discord.ButtonStyle.danger,
        emoji="🗑️"
    )
    async def proceed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle proceed button click"""
        
        async def execute_clear(confirmation_interaction: discord.Interaction):
            """Execute the clear operation after modal confirmation"""
            await confirmation_interaction.response.defer(ephemeral=True)
            
            try:
                # Execute the clear operation
                results = await self.challenge_ops.clear_active_challenges()
                
                # Create results embed
                results_embed = discord.Embed(
                    title="✅ Clear Operation Complete",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                if results['total_deleted'] > 0:
                    description_parts = [
                        f"**Successfully deleted {results['total_deleted']} challenges:**\n"
                    ]
                    
                    if results.get('pending_count', 0) > 0:
                        description_parts.append(f"• {results.get('pending_count', 0)} PENDING challenges")
                    if results.get('accepted_count', 0) > 0:
                        description_parts.append(f"• {results.get('accepted_count', 0)} ACCEPTED challenges")
                    
                    if results.get('errors', 0) > 0:
                        description_parts.append(f"\n⚠️ {results['errors']} errors occurred during deletion")
                    
                    results_embed.description = "\n".join(description_parts)
                else:
                    results_embed.description = "No challenges were found to delete."
                    results_embed.color = discord.Color.blue()
                
                await confirmation_interaction.followup.send(embed=results_embed)
                
                # Log admin action
                logger.info(
                    f"Admin clear executed by {confirmation_interaction.user.id} "
                    f"({confirmation_interaction.user.name}): {results}"
                )
                
            except Exception as e:
                logger.error(f"Clear operation error: {e}", exc_info=True)
                
                error_embed = discord.Embed(
                    title="❌ Clear Operation Failed",
                    description=f"An error occurred during the clear operation: {str(e)}",
                    color=discord.Color.red()
                )
                
                await confirmation_interaction.followup.send(embed=error_embed)
        
        # Show confirmation modal
        modal = AdminConfirmationModal(
            title="Final Confirmation Required",
            confirmation_text="CONFIRM DELETE",
            callback=execute_clear
        )
        
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.gray,
        emoji="❌"
    )
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancel button click"""
        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Operation Cancelled",
                description="Challenge clear operation was cancelled safely.",
                color=discord.Color.blue()
            ),
            ephemeral=True
        )
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.edit_original_response(view=self)


class AdminClearMatchesConfirmationView(discord.ui.View):
    """Confirmation view for the clear matches command"""
    
    def __init__(self, match_ops: MatchOperations, total_count: int):
        super().__init__(timeout=300)
        self.match_ops = match_ops
        self.total_count = total_count
    
    @discord.ui.button(
        label="Proceed with Deletion",
        style=discord.ButtonStyle.danger,
        emoji="🗑️"
    )
    async def proceed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle proceed button click"""
        
        async def execute_clear(confirmation_interaction: discord.Interaction):
            """Execute the clear operation after modal confirmation"""
            await confirmation_interaction.response.defer(ephemeral=True)
            
            try:
                # Execute the clear operation
                results = await self.match_ops.clear_active_matches()
                
                # Create results embed
                results_embed = discord.Embed(
                    title="✅ Clear Operation Complete",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                
                if results['total_deleted'] > 0:
                    description_parts = [
                        f"**Successfully deleted {results['total_deleted']} matches:**\n"
                    ]
                    
                    if results.get('pending_count', 0) > 0:
                        description_parts.append(f"• {results.get('pending_count', 0)} PENDING matches")
                    if results.get('active_count', 0) > 0:
                        description_parts.append(f"• {results.get('active_count', 0)} ACTIVE matches")
                    if results.get('awaiting_confirmation_count', 0) > 0:
                        description_parts.append(f"• {results.get('awaiting_confirmation_count', 0)} AWAITING_CONFIRMATION matches")
                    
                    if results.get('errors', 0) > 0:
                        description_parts.append(f"\n⚠️ {results['errors']} errors occurred during deletion")
                    
                    results_embed.description = "\n".join(description_parts)
                else:
                    results_embed.description = "No matches were found to delete."
                    results_embed.color = discord.Color.blue()
                
                await confirmation_interaction.followup.send(embed=results_embed)
                
                # Log admin action
                logger.info(
                    f"Admin clear matches executed by {confirmation_interaction.user.id} "
                    f"({confirmation_interaction.user.name}): {results}"
                )
                
            except Exception as e:
                logger.error(f"Clear matches operation error: {e}", exc_info=True)
                
                error_embed = discord.Embed(
                    title="❌ Clear Operation Failed",
                    description=f"An error occurred during deletion: {str(e)}",
                    color=discord.Color.red()
                )
                
                await confirmation_interaction.followup.send(embed=error_embed)
        
        # Show confirmation modal
        modal = AdminConfirmationModal(
            title="Confirm Match Deletion",
            confirmation_text="CONFIRM DELETE",
            callback=execute_clear
        )
        
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.gray,
        emoji="❌"
    )
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancel button click"""
        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Operation Cancelled",
                description="Match clear operation was cancelled safely.",
                color=discord.Color.blue()
            ),
            ephemeral=True
        )
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.edit_original_response(view=self)


class AdminClearSingleMatchConfirmationView(discord.ui.View):
    """Confirmation view for the clear single match command"""
    
    def __init__(self, match_ops: MatchOperations, match_id: int):
        super().__init__(timeout=300)
        self.match_ops = match_ops
        self.match_id = match_id
    
    @discord.ui.button(
        label="Proceed with Deletion",
        style=discord.ButtonStyle.danger,
        emoji="🗑️"
    )
    async def proceed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle proceed button click"""
        
        async def execute_delete(confirmation_interaction: discord.Interaction):
            """Execute the delete operation after modal confirmation"""
            await confirmation_interaction.response.defer(ephemeral=True)
            
            try:
                # Execute the delete operation
                success = await self.match_ops.delete_match_by_id(self.match_id)
                
                if success:
                    results_embed = discord.Embed(
                        title="✅ Match Deleted",
                        description=f"Successfully deleted Match ID {self.match_id}.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                else:
                    results_embed = discord.Embed(
                        title="❌ Match Not Found",
                        description=f"Match ID {self.match_id} was not found or already deleted.",
                        color=discord.Color.orange(),
                        timestamp=datetime.now(timezone.utc)
                    )
                
                await confirmation_interaction.followup.send(embed=results_embed)
                
                # Log admin action
                logger.info(
                    f"Admin delete match executed by {confirmation_interaction.user.id} "
                    f"({confirmation_interaction.user.name}): Match {self.match_id}, Success: {success}"
                )
                
            except Exception as e:
                logger.error(f"Delete match operation error: {e}", exc_info=True)
                
                error_embed = discord.Embed(
                    title="❌ Delete Operation Failed",
                    description=f"An error occurred during deletion: {str(e)}",
                    color=discord.Color.red()
                )
                
                await confirmation_interaction.followup.send(embed=error_embed)
        
        # Show confirmation modal
        modal = AdminConfirmationModal(
            title=f"Confirm Match {self.match_id} Deletion",
            confirmation_text="CONFIRM DELETE",
            callback=execute_delete
        )
        
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.gray,
        emoji="❌"
    )
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancel button click"""
        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Operation Cancelled",
                description=f"Match {self.match_id} deletion was cancelled safely.",
                color=discord.Color.blue()
            ),
            ephemeral=True
        )
        
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        
        await interaction.edit_original_response(view=self)


async def setup(bot):
    await bot.add_cog(HousekeepingCog(bot))