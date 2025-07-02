import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Union
import asyncio
from bot.config import Config
from bot.operations.admin_operations import AdminOperations, AdminOperationError, AdminPermissionError, AdminValidationError
# Removed AdminConfirmationModal import - replaced with button-based confirmation
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)

class AdminCog(commands.Cog):
    """Admin-only commands for managing the tournament system"""
    
    def __init__(self, bot):
        self.bot = bot
        self.admin_ops = AdminOperations(bot.db)
        self.logger = logger
    
    def cog_check(self, ctx):
        """Check if user is the bot owner"""
        return ctx.author.id == Config.OWNER_DISCORD_ID
    
    @commands.command(name='shutdown')
    async def shutdown_bot(self, ctx):
        """Shutdown the bot (Owner only)"""
        await ctx.send("🔴 Shutting down Tournament Bot...")
        await self.bot.close()
    
    @commands.command(name='reload')
    async def reload_cog(self, ctx, cog_name: str):
        """Reload a specific cog (Owner only)"""
        try:
            await self.bot.reload_extension(f'bot.cogs.{cog_name}')
            await ctx.send(f"✅ Reloaded `{cog_name}` cog successfully.")
        except Exception as e:
            await ctx.send(f"❌ Failed to reload `{cog_name}`: {e}")
    
    @commands.command(name='dbstats')
    async def database_stats(self, ctx):
        """Show database statistics (Owner only)"""
        try:
            async with self.bot.db.get_session() as session:
                # Get counts from each table
                from sqlalchemy import select, func
                from bot.database.models import Player, Game, Challenge
                
                player_count = await session.scalar(select(func.count(Player.id)))
                game_count = await session.scalar(select(func.count(Game.id)))
                challenge_count = await session.scalar(select(func.count(Challenge.id)))
                
                embed = discord.Embed(
                    title="📊 Database Statistics",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Players", value=player_count, inline=True)
                embed.add_field(name="Games", value=game_count, inline=True)
                embed.add_field(name="Challenges", value=challenge_count, inline=True)
                
                await ctx.send(embed=embed)
                
        except Exception as e:
            await ctx.send(f"❌ Error getting database stats: {e}")
    
    @commands.hybrid_command(name='admin-populate-data')
    async def populate_data(self, ctx):
        """Load/refresh clusters and events from CSV (Owner only)"""
        try:
            # Send initial response
            embed = discord.Embed(
                title="🔄 Starting CSV Data Population",
                description="Loading clusters and events from CSV file...",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            
            # Import and run population
            try:
                from populate_from_csv import populate_clusters_and_events
                results = await populate_clusters_and_events()
                
                # Success response
                embed = discord.Embed(
                    title="✅ CSV Population Completed",
                    color=discord.Color.green()
                )
                embed.add_field(name="Clusters Created", value=results['clusters_created'], inline=True)
                embed.add_field(name="Events Created", value=results['events_created'], inline=True)
                embed.add_field(name="Events Skipped", value=results['events_skipped'], inline=True)
                
                await ctx.send(embed=embed)
                
            except ImportError:
                # Fallback to database method if populate_from_csv.py not available
                async with self.bot.db.get_session() as session:
                    await self.bot.db.import_clusters_and_events_from_csv(session, clear_existing=True)
                
                embed = discord.Embed(
                    title="✅ CSV Import Completed (Basic)",
                    description="Used fallback import method. Check logs for details.",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=embed)
                
        except Exception as e:
            embed = discord.Embed(
                title="❌ CSV Population Failed",
                description=f"Error: {str(e)}",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
    
    # ============================================================================
    # Phase 5.3 Administrative Commands
    # ============================================================================
    
    class EloResetConfirmationView(discord.ui.View):
        """Confirmation view for single player Elo reset"""
        
        def __init__(self, admin_cog, admin_discord_id: int, player: discord.Member, event_name: Optional[str] = None, reason: Optional[str] = None):
            super().__init__(timeout=30.0)
            self.admin_cog = admin_cog
            self.admin_discord_id = admin_discord_id
            self.player = player
            self.event_name = event_name
            self.reason = reason
            self.confirmed = False
        
        @discord.ui.button(label="✅ Confirm Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
        async def confirm_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.admin_discord_id:
                await interaction.response.send_message("❌ Only the command author can confirm this action.", ephemeral=True)
                return
            
            self.confirmed = True
            self.stop()
            
            # Disable all buttons
            for child in self.children:
                child.disabled = True
            
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🔄 Processing Elo Reset...",
                    description=f"Resetting Elo for {self.player.mention}...",
                    color=discord.Color.orange()
                ),
                view=self
            )
        
        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.admin_discord_id:
                await interaction.response.send_message("❌ Only the command author can cancel this action.", ephemeral=True)
                return
            
            self.stop()
            
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="❌ Elo Reset Cancelled",
                    description="Operation cancelled by admin.",
                    color=discord.Color.red()
                ),
                view=None
            )
        
        async def on_timeout(self):
            """Handle timeout - disable buttons and show timeout message"""
            for child in self.children:
                child.disabled = True
    
    async def _resolve_player_changes_display(self, elo_changes: list, guild: discord.Guild) -> list[str]:
        """Helper method to resolve player IDs to display names and format changes"""
        if not elo_changes:
            return []
        
        # Extract all player IDs
        player_ids = [change['player_id'] for change in elo_changes]
        
        # Batch fetch all Player records
        async with self.bot.db.get_session() as session:
            from sqlalchemy import select
            from bot.database.models import Player
            
            result = await session.execute(
                select(Player).where(Player.id.in_(player_ids))
            )
            players = result.scalars().all()
            player_map = {p.id: p for p in players}
        
        # Format change strings with resolved names
        formatted_changes = []
        for change in elo_changes:
            player_id = change['player_id']
            player_record = player_map.get(player_id)
            
            if player_record:
                # Try to get current server member for up-to-date display name
                member = guild.get_member(player_record.discord_id) if guild else None
                if member:
                    player_name = f"**{member.display_name}** ({member.name})"
                else:
                    # Fallback to database display name and username
                    display_name = player_record.display_name or player_record.username
                    player_name = f"**{display_name}** ({player_record.username})"
            else:
                # Handle missing player record gracefully
                player_name = f"Unknown Player (ID: {player_id})"
            
            formatted_changes.append(
                f"{player_name}: {change['old_elo']} → {change['new_elo']} ({change['elo_change']:+})"
            )
        
        return formatted_changes

    class UndoMatchConfirmationView(discord.ui.View):
        """Confirmation view for match undo with dry-run preview and public announcement"""
        
        def __init__(self, admin_cog, admin_discord_id: int, match_id: int, ctx, reason: Optional[str] = None, player_changes_formatted: Optional[list[str]] = None):
            super().__init__(timeout=30.0)
            self.admin_cog = admin_cog
            self.admin_discord_id = admin_discord_id
            self.match_id = match_id
            self.ctx = ctx  # Store context for public announcement
            self.reason = reason
            self.confirmed = False
            self.dry_run_completed = False
            self.player_changes_formatted = player_changes_formatted or []
        
        @discord.ui.button(label="✅ Preview Undo", style=discord.ButtonStyle.primary, emoji="🔍")
        async def preview_undo(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.admin_discord_id:
                await interaction.response.send_message("❌ Only the command author can preview this action.", ephemeral=True)
                return
            
            try:
                # Perform dry run
                dry_run_result = await self.admin_cog.admin_ops.undo_match(
                    admin_discord_id=self.admin_discord_id,
                    match_id=self.match_id,
                    reason=self.reason,
                    dry_run=True
                )
                
                # Show dry run results
                dry_run_embed = discord.Embed(
                    title="🔍 Match Undo Preview",
                    color=discord.Color.blue()
                )
                dry_run_embed.add_field(name="Match ID", value=str(self.match_id), inline=True)
                dry_run_embed.add_field(name="Players Affected", value=dry_run_result['affected_players'], inline=True)
                
                # Use pre-formatted player changes if available, otherwise format them now
                if self.player_changes_formatted:
                    changes_display = self.player_changes_formatted[:5]  # Show first 5
                    if len(self.player_changes_formatted) > 5:
                        changes_display.append(f"... and {len(self.player_changes_formatted) - 5} more players")
                elif dry_run_result['elo_changes']:
                    changes_display = []
                    for change in dry_run_result['elo_changes'][:5]:  # Show first 5
                        changes_display.append(f"Player {change['player_id']}: {change['old_elo']} → {change['new_elo']} ({change['elo_change']:+})")
                    
                    if len(dry_run_result['elo_changes']) > 5:
                        changes_display.append(f"... and {len(dry_run_result['elo_changes']) - 5} more players")
                else:
                    changes_display = ["No Elo changes to display"]
                
                if changes_display:
                    dry_run_embed.add_field(
                        name="Elo Changes Preview",
                        value="\n".join(changes_display),
                        inline=False
                    )
                
                dry_run_embed.set_footer(text="This is a preview. Click ✅ Execute to proceed or ❌ Cancel to abort.")
                
                # Update view for final confirmation
                self.dry_run_completed = True
                for child in self.children:
                    child.disabled = True
                
                # Add final confirmation buttons
                execute_button = discord.ui.Button(label="✅ Execute Undo", style=discord.ButtonStyle.danger, emoji="⚠️")
                execute_button.callback = self.execute_undo
                cancel_button = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
                cancel_button.callback = self.cancel_from_preview
                
                final_view = discord.ui.View(timeout=30.0)
                final_view.add_item(execute_button)
                final_view.add_item(cancel_button)
                
                await interaction.response.edit_message(embed=dry_run_embed, view=final_view)
                
            except Exception as e:
                error_embed = discord.Embed(
                    title="❌ Preview Failed",
                    description=f"Could not preview match undo: {str(e)}",
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
        
        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_undo(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.admin_discord_id:
                await interaction.response.send_message("❌ Only the command author can cancel this action.", ephemeral=True)
                return
            
            self.stop()
            
            cancel_embed = discord.Embed(
                title="❌ Match Undo Cancelled",
                description="Operation cancelled by admin.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=cancel_embed, view=None)
        
        async def execute_undo(self, interaction: discord.Interaction):
            """Execute the actual match undo (called from dynamic button)"""
            if interaction.user.id != self.admin_discord_id:
                await interaction.response.send_message("❌ Only the command author can execute this action.", ephemeral=True)
                return
            
            try:
                # Execute the actual undo
                result = await self.admin_cog.admin_ops.undo_match(
                    admin_discord_id=self.admin_discord_id,
                    match_id=self.match_id,
                    reason=self.reason,
                    dry_run=False
                )
                
                # Admin success response (ephemeral)
                admin_embed = discord.Embed(
                    title="✅ Match Undo Completed",
                    description="The match has been successfully reverted.",
                    color=discord.Color.green()
                )
                admin_embed.add_field(name="Match ID", value=str(self.match_id), inline=True)
                admin_embed.add_field(name="Players Affected", value=result['affected_players'], inline=True)
                
                # Show the same player changes that were previewed for confirmation
                if self.player_changes_formatted:
                    admin_embed.add_field(
                        name="Player Changes Applied",
                        value="\n".join(self.player_changes_formatted),
                        inline=False
                    )
                
                admin_embed.set_footer(text="Elo changes have been reversed • Action logged for audit trail")
                
                self.confirmed = True
                self.stop()
                
                # Send ephemeral confirmation to admin
                await interaction.response.edit_message(embed=admin_embed, view=None)
                
                # Send public announcement to all members
                event_name = result.get('event_name', 'Unknown Event')
                cluster_name = result.get('cluster_name', 'Unknown Cluster') 
                event_context = f"{cluster_name}→{event_name}"
                
                public_embed = discord.Embed(
                    title="✅ Match Undo Completed",
                    description=f"A match in **{event_context}** has been undone by an administrator.",
                    color=discord.Color.green()
                )
                public_embed.add_field(name="Event", value=event_context, inline=True)
                public_embed.add_field(name="Players Affected", value=result['affected_players'], inline=True)
                public_embed.add_field(name="Match ID", value=str(self.match_id), inline=True)
                
                # Show detailed player Elo changes for transparency
                if self.player_changes_formatted:
                    # Display up to 6 players to respect Discord embed limits
                    changes_to_show = self.player_changes_formatted[:6]
                    if len(self.player_changes_formatted) > 6:
                        changes_to_show.append(f"... and {len(self.player_changes_formatted) - 6} more players")
                    
                    public_embed.add_field(
                        name="Elo Changes",
                        value="\n".join(changes_to_show),
                        inline=False
                    )
                
                if self.reason:
                    public_embed.add_field(name="Reason", value=self.reason, inline=False)
                
                public_embed.set_footer(text="Player ratings have been restored to their previous values")
                
                # Send public announcement (non-ephemeral)
                await interaction.followup.send(embed=public_embed, ephemeral=False)
                
            except Exception as e:
                error_embed = discord.Embed(
                    title="❌ Match Undo Failed",
                    description=str(e),
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)
        
        async def cancel_from_preview(self, interaction: discord.Interaction):
            """Cancel from the preview stage (called from dynamic button)"""
            if interaction.user.id != self.admin_discord_id:
                await interaction.response.send_message("❌ Only the command author can cancel this action.", ephemeral=True)
                return
            
            cancel_embed = discord.Embed(
                title="❌ Match Undo Cancelled",
                description="Operation cancelled after preview.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=cancel_embed, view=None)
        
        async def on_timeout(self):
            """Handle timeout - disable buttons and show timeout message"""
            for child in self.children:
                child.disabled = True
    
    class MassEloResetConfirmationView(discord.ui.View):
        """Confirmation view for mass Elo reset (replacement for broken modal workflow)"""
        
        def __init__(self, admin_cog, admin_discord_id: int, event_name: Optional[str] = None, reason: Optional[str] = None):
            super().__init__(timeout=60.0)  # Longer timeout for critical operation
            self.admin_cog = admin_cog
            self.admin_discord_id = admin_discord_id
            self.event_name = event_name
            self.reason = reason
            self.confirmed = False
        
        @discord.ui.button(label="🚨 CONFIRM MASS RESET", style=discord.ButtonStyle.danger, emoji="⚠️")
        async def confirm_mass_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.admin_discord_id:
                await interaction.response.send_message("❌ Only the command author can confirm this action.", ephemeral=True)
                return
            
            self.confirmed = True
            self.stop()
            
            # Disable all buttons
            for child in self.children:
                child.disabled = True
            
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🔄 Processing Mass Elo Reset...",
                    description="This may take a moment. Please wait...",
                    color=discord.Color.orange()
                ),
                view=self
            )
        
        @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
        async def cancel_mass_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
            if interaction.user.id != self.admin_discord_id:
                await interaction.response.send_message("❌ Only the command author can cancel this action.", ephemeral=True)
                return
            
            self.stop()
            
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="❌ Mass Elo Reset Cancelled",
                    description="Operation cancelled by admin.",
                    color=discord.Color.red()
                ),
                view=None
            )
        
        async def on_timeout(self):
            """Handle timeout - disable buttons and show timeout message"""
            for child in self.children:
                child.disabled = True
    
    # ============================================================================
    # Cluster->Event Parsing Helper Functions
    # ============================================================================
    
    async def _parse_cluster_event(self, ctx, event_string: str) -> tuple[Optional[int], Optional[str]]:
        """
        Parse cluster->event syntax with backward compatibility.
        
        Supports formats:
        - "event_name" (backward compatible, must be unambiguous)
        - "cluster_name->event_name" (explicit disambiguation)
        
        Args:
            ctx: Command context for error messages
            event_string: User input string
            
        Returns:
            Tuple of (event_id, event_name) or (None, None) if error sent to user
        """
        if not event_string:
            return None, None
            
        # Parse the input format
        cluster_part, separator, event_part = event_string.partition('->')
        cluster_name = cluster_part.strip() if separator else None
        event_name = event_part.strip() if separator else cluster_part.strip()
        
        async with self.bot.db.get_session() as session:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            from bot.database.models import Event, Cluster
            
            if cluster_name:
                # Explicit cluster->event format
                # First, find the cluster
                cluster_query = select(Cluster).where(Cluster.name.ilike(f"%{cluster_name}%"))
                cluster_result = await session.execute(cluster_query)
                cluster = cluster_result.scalar_one_or_none()
                
                if not cluster:
                    await ctx.send(embed=discord.Embed(
                        title="❌ Cluster Not Found",
                        description=f"Could not find cluster matching '{cluster_name}'",
                        color=discord.Color.red()
                    ))
                    return None, None
                
                # Then find the event within that cluster
                event_query = select(Event).where(
                    Event.cluster_id == cluster.id,
                    Event.name.ilike(f"%{event_name}%")
                )
                event_result = await session.execute(event_query)
                event = event_result.scalar_one_or_none()
                
                if not event:
                    await ctx.send(embed=discord.Embed(
                        title="❌ Event Not Found in Cluster",
                        description=f"Could not find event '{event_name}' in cluster '{cluster.name}'",
                        color=discord.Color.red()
                    ))
                    return None, None
                
                return event.id, event.name
                
            else:
                # Backward compatibility: plain event name
                event_query = select(Event).options(
                    selectinload(Event.cluster)  # Fix N+1 pattern - eager load clusters!
                ).where(Event.name.ilike(f"%{event_name}%"))
                event_result = await session.execute(event_query)
                events = list(event_result.scalars().all())
                
                if not events:
                    await ctx.send(embed=discord.Embed(
                        title="❌ Event Not Found",
                        description=f"Could not find event matching '{event_name}'",
                        color=discord.Color.red()
                    ))
                    return None, None
                
                elif len(events) == 1:
                    # Unambiguous, use the single match
                    event = events[0]
                    return event.id, event.name
                
                else:
                    # Ambiguous - show options with cluster->event format
                    cluster_events = []
                    for event in events[:10]:  # Limit to first 10 for readability
                        # Use pre-loaded cluster relationship (no additional query!)
                        cluster = event.cluster
                        if not cluster:
                            # Handle orphaned event (cluster was deleted)
                            continue
                        cluster_events.append(f"• `{cluster.name}->{event.name}`")
                    
                    description = (
                        f"Multiple events found matching '{event_name}'. "
                        f"Please specify using cluster->event format:\n\n" +
                        "\n".join(cluster_events)
                    )
                    
                    if len(events) > 10:
                        description += f"\n... and {len(events) - 10} more"
                    
                    await ctx.send(embed=discord.Embed(
                        title="❌ Ambiguous Event Name",
                        description=description,
                        color=discord.Color.orange()
                    ))
                    return None, None
    
    @commands.hybrid_command(name='admin-reset-elo', description="Reset a single player's Elo in a specific event or all events")
    @app_commands.describe(
        player="The Discord member whose Elo should be reset",
        event_name="Optional event name or cluster->event format (e.g., 'chess->blitz'). If not specified, resets all events for this player.",
        reason="Optional reason for the Elo reset (for audit trail)"
    )
    @app_commands.check(lambda interaction: interaction.user.id == Config.OWNER_DISCORD_ID)
    async def reset_player_elo(self, ctx, player: discord.Member, event_name: Optional[str] = None, *, reason: Optional[str] = None):
        """
        Reset a single player's Elo in a specific event (or all events if not specified).
        
        Usage:
        !admin-reset-elo @player [event_name] [reason]
        !admin-reset-elo @player "Super Smash Bros" Incorrect initial rating
        !admin-reset-elo @player Reset due to dispute
        
        Requires confirmation via reaction within 30 seconds.
        """
        try:
            # Defer response for slash commands to prevent timeout
            if ctx.interaction:
                await ctx.defer(ephemeral=True)
            
            # Validate event if specified (supports cluster->event syntax)
            event_id = None
            if event_name:
                event_id, event_name = await self._parse_cluster_event(ctx, event_name)
                if event_id is None:
                    return  # Error already sent to user
            
            # Create confirmation embed
            embed = discord.Embed(
                title="⚠️ Confirm Elo Reset",
                color=discord.Color.orange()
            )
            embed.add_field(name="Player", value=player.mention, inline=True)
            embed.add_field(name="Scope", value=event_name or "ALL EVENTS", inline=True)
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
            embed.add_field(
                name="⚠️ Warning",
                value="This action will reset the player's Elo to 1000 and cannot be easily undone!",
                inline=False
            )
            embed.set_footer(text="Click ✅ to confirm or ❌ to cancel • Times out in 30 seconds")
            
            # Create confirmation view
            view = self.EloResetConfirmationView(self, ctx.author.id, player, event_name, reason)
            
            # Send confirmation message
            confirmation_msg = await ctx.send(embed=embed, view=view)
            
            # Wait for confirmation
            await view.wait()
            
            if view.confirmed:
                try:
                    # Perform the reset
                    result = await self.admin_ops.reset_player_elo(
                        admin_discord_id=ctx.author.id,
                        player_discord_id=player.id,
                        event_id=event_id,
                        reason=reason
                    )
                    
                    # Success response
                    success_embed = discord.Embed(
                        title="✅ Elo Reset Completed",
                        color=discord.Color.green()
                    )
                    success_embed.add_field(name="Player", value=result['player_username'], inline=True)
                    success_embed.add_field(name="Events Affected", value=len(result['affected_events']), inline=True)
                    success_embed.add_field(name="Reset Type", value=result['reset_type'], inline=True)
                    
                    if result['affected_events']:
                        events_list = []
                        for event_info in result['affected_events'][:5]:  # Show first 5
                            events_list.append(f"• {event_info['event_name']}: {event_info['old_raw_elo']} → {event_info['new_elo']}")
                        
                        if len(result['affected_events']) > 5:
                            events_list.append(f"... and {len(result['affected_events']) - 5} more events")
                        
                        success_embed.add_field(
                            name="Elo Changes",
                            value="\n".join(events_list),
                            inline=False
                        )
                    
                    success_embed.set_footer(text="Action logged for audit trail")
                    
                    await confirmation_msg.edit(embed=success_embed, view=None)
                    
                except (AdminPermissionError, AdminValidationError, AdminOperationError) as e:
                    error_embed = discord.Embed(
                        title="❌ Elo Reset Failed",
                        description=str(e),
                        color=discord.Color.red()
                    )
                    await confirmation_msg.edit(embed=error_embed, view=None)
            
            elif not view.confirmed and view.is_finished():
                # Timeout occurred
                timeout_embed = discord.Embed(
                    title="⏰ Confirmation Timeout",
                    description="Elo reset cancelled due to timeout.",
                    color=discord.Color.orange()
                )
                await confirmation_msg.edit(embed=timeout_embed, view=None)
                
        except Exception as e:
            self.logger.error(f"Error in admin-reset-elo command: {e}")
            await ctx.send(embed=discord.Embed(
                title="❌ Command Error",
                description=f"An unexpected error occurred: {str(e)}",
                color=discord.Color.red()
            ))
    
    async def _event_autocomplete_helper(self, interaction: discord.Interaction, current: str):
        """Shared logic for event name autocomplete with cluster->event support and smart disambiguation."""
        try:
            async with self.bot.db.get_session() as session:
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                from bot.database.models import Event, Cluster
                
                if not current:
                    # Show recent events without cluster prefix for common cases
                    query = select(Event.name).where(Event.is_active == True).limit(25)
                    result = await session.execute(query)
                    event_names = result.scalars().all()
                    return [app_commands.Choice(name=name, value=name) for name in event_names[:25]]
                
                # Parse potential cluster->event format
                cluster_part, separator, event_part = current.partition('->')
                
                if separator:
                    # User is typing cluster->event format
                    cluster_name = cluster_part.strip()
                    event_name = event_part.strip()
                    
                    # Find matching cluster(s)
                    cluster_query = select(Cluster).where(Cluster.name.ilike(f"%{cluster_name}%"))
                    cluster_result = await session.execute(cluster_query)
                    clusters = list(cluster_result.scalars().all())
                    
                    if not clusters:
                        return []
                    
                    # OPTIMIZED: Single query for all events across matching clusters
                    cluster_ids = [c.id for c in clusters[:5]]  # Limit clusters
                    event_query = select(Event).options(
                        selectinload(Event.cluster)  # Eager load cluster relationships
                    ).where(
                        Event.cluster_id.in_(cluster_ids),  # Single query using IN clause
                        Event.is_active == True
                    )
                    if event_name:
                        event_query = event_query.where(Event.name.ilike(f"%{event_name}%"))
                    event_query = event_query.limit(25)  # Overall limit instead of per-cluster
                    
                    event_result = await session.execute(event_query)
                    events = list(event_result.scalars().all())
                    
                    choices = []
                    for event in events:
                        # Use pre-loaded cluster relationship (no additional queries!)
                        cluster_event_format = f"{event.cluster.name}->{event.name}"
                        choices.append(app_commands.Choice(name=cluster_event_format, value=cluster_event_format))
                    
                    return choices[:25]
                
                else:
                    # Regular event name search with smart disambiguation - OPTIMIZED with eager loading
                    query = select(Event).options(
                        selectinload(Event.cluster)  # Fix N+1 query pattern!
                    ).where(
                        Event.is_active == True,
                        Event.name.ilike(f"%{current}%")
                    ).limit(50)  # Get more to check for duplicates
                    
                    result = await session.execute(query)
                    events = list(result.scalars().all())
                    
                    # Group events by name to detect ambiguity
                    event_names = {}
                    for event in events:
                        if event.name not in event_names:
                            event_names[event.name] = []
                        event_names[event.name].append(event)
                    
                    choices = []
                    for name, event_list in event_names.items():
                        if len(event_list) == 1:
                            # Unambiguous, show simple name
                            choices.append(app_commands.Choice(name=name, value=name))
                        else:
                            # Ambiguous, show cluster->event format for each - NO MORE N+1 QUERIES!
                            for event in event_list:
                                # Access pre-loaded cluster relationship (no additional query)
                                cluster_event_format = f"{event.cluster.name}->{event.name}"
                                display_name = f"{name} (in {event.cluster.name})"
                                choices.append(app_commands.Choice(name=display_name, value=cluster_event_format))
                    
                    return choices[:25]
                    
        except Exception as e:
            self.logger.error(f"Error in event autocomplete: {e}", exc_info=True)
            return []
    
    @reset_player_elo.autocomplete('event_name')
    async def reset_player_elo_event_autocomplete(self, interaction: discord.Interaction, current: str):
        """Provide enhanced autocomplete with cluster->event format for disambiguation"""
        return await self._event_autocomplete_helper(interaction, current)
    
    @commands.hybrid_command(name='admin-reset-elo-all', description="Reset ALL players' Elo in a specific event or all events (DESTRUCTIVE)")
    @app_commands.describe(
        event_name="Optional event name (if not specified, resets ALL events for ALL players)",
        reason="Required reason for the mass Elo reset (for audit trail)"
    )
    @app_commands.check(lambda interaction: interaction.user.id == Config.OWNER_DISCORD_ID)
    async def reset_all_elo(self, ctx, event_name: Optional[str] = None, *, reason: Optional[str] = None):
        """
        Reset ALL players' Elo in a specific event (or all events if not specified).
        
        ⚠️ CRITICAL: This is a destructive operation requiring double confirmation.
        
        Usage:
        !admin-reset-elo-all [event_name] [reason]
        !admin-reset-elo-all "Super Smash Bros" Season reset
        !admin-reset-elo-all Global season reset
        
        Requires button confirmation (improved from broken modal workflow).
        """
        try:
            # Defer response for slash commands to prevent timeout
            if ctx.interaction:
                await ctx.defer(ephemeral=True)
            
            # Validate event if specified (supports cluster->event syntax)
            event_id = None
            if event_name:
                event_id, event_name = await self._parse_cluster_event(ctx, event_name)
                if event_id is None:
                    return  # Error already sent to user
            
            # Create warning embed
            scope = event_name or "GLOBAL"
            
            embed = discord.Embed(
                title="🚨 CRITICAL: Mass Elo Reset",
                color=discord.Color.dark_red()
            )
            embed.add_field(name="Scope", value=scope, inline=True)
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
            embed.add_field(
                name="⚠️ DANGER",
                value="This will reset ALL players' Elo ratings and cannot be easily undone!\n"
                      "A backup will be created automatically.",
                inline=False
            )
            embed.add_field(
                name="⚠️ Confirmation Required",
                value="Click the button below to confirm this destructive operation.",
                inline=False
            )
            embed.set_footer(text="This action is logged and irreversible • Times out in 60 seconds")
            
            # Create confirmation view
            view = self.MassEloResetConfirmationView(self, ctx.author.id, event_name, reason)
            
            # Send confirmation message
            confirmation_msg = await ctx.send(embed=embed, view=view)
            
            # Wait for confirmation
            await view.wait()
            
            if view.confirmed:
                try:
                    # Perform the mass reset
                    result = await self.admin_ops.reset_all_elo(
                        admin_discord_id=ctx.author.id,
                        event_id=event_id,
                        reason=reason,
                        create_backup=True
                    )
                    
                    # Success response
                    success_embed = discord.Embed(
                        title="✅ Mass Elo Reset Completed",
                        color=discord.Color.green()
                    )
                    success_embed.add_field(name="Scope", value=result['reset_type'], inline=True)
                    success_embed.add_field(name="Players Affected", value=result['affected_players'], inline=True)
                    success_embed.add_field(name="Events Affected", value=result['affected_events'], inline=True)
                    
                    if result.get('backup_info'):
                        success_embed.add_field(
                            name="Backup Created",
                            value=f"ID: {result['backup_info']['snapshot_id']}\nTime: {result['backup_info']['timestamp']}",
                            inline=False
                        )
                    
                    success_embed.set_footer(text="⚠️ All affected Elo ratings have been reset to 1000")
                    
                    await confirmation_msg.edit(embed=success_embed, view=None)
                    
                except (AdminPermissionError, AdminValidationError, AdminOperationError) as e:
                    error_embed = discord.Embed(
                        title="❌ Mass Elo Reset Failed",
                        description=str(e),
                        color=discord.Color.red()
                    )
                    await confirmation_msg.edit(embed=error_embed, view=None)
            
            elif not view.confirmed and view.is_finished():
                # Timeout occurred
                timeout_embed = discord.Embed(
                    title="⏰ Confirmation Timeout",
                    description="Mass Elo reset cancelled due to timeout.",
                    color=discord.Color.orange()
                )
                await confirmation_msg.edit(embed=timeout_embed, view=None)
            
        except Exception as e:
            self.logger.error(f"Error in admin-reset-elo-all command: {e}")
            await ctx.send(embed=discord.Embed(
                title="❌ Command Error",
                description=f"An unexpected error occurred: {str(e)}",
                color=discord.Color.red()
            ))
    
    @reset_all_elo.autocomplete('event_name')
    async def reset_all_elo_event_autocomplete(self, interaction: discord.Interaction, current: str):
        """Provide enhanced autocomplete with cluster->event format for disambiguation"""
        return await self._event_autocomplete_helper(interaction, current)
    
    @commands.hybrid_command(name='admin-undo-match', description="Undo a match and reverse its Elo effects")
    @app_commands.describe(
        match_id="ID of the match to undo",
        reason="Optional reason for undoing the match (for audit trail)"
    )
    @app_commands.check(lambda interaction: interaction.user.id == Config.OWNER_DISCORD_ID)
    async def undo_match(self, ctx, match_id: int, *, reason: Optional[str] = None):
        """
        Undo a match and reverse its Elo effects.
        
        Usage:
        !admin-undo-match 1337 Incorrect result reported
        !admin-undo-match 1337
        
        This will reverse all Elo changes from the specified match.
        """
        try:
            # Defer response for slash commands to prevent timeout
            if ctx.interaction:
                await ctx.defer(ephemeral=True)
            
            # Pre-resolve player changes for better UX
            player_changes_formatted = []
            try:
                # Perform dry run to get elo changes
                dry_run_result = await self.admin_ops.undo_match(
                    admin_discord_id=ctx.author.id,
                    match_id=match_id,
                    reason=reason,
                    dry_run=True
                )
                
                # Resolve player names for display
                if dry_run_result.get('elo_changes'):
                    player_changes_formatted = await self._resolve_player_changes_display(
                        dry_run_result['elo_changes'], 
                        ctx.guild
                    )
            except Exception as e:
                # If dry run fails, we'll proceed without pre-formatted changes
                self.logger.warning(f"Could not pre-resolve player changes for match {match_id}: {e}")
            
            # Create confirmation embed
            embed = discord.Embed(
                title="⚠️ Confirm Match Undo",
                description="This will reverse all Elo changes from this match.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Match ID", value=str(match_id), inline=True)
            embed.add_field(name="Reason", value=reason or "No reason provided", inline=True)
            embed.add_field(
                name="⚠️ Warning",
                value="All Elo changes from this match will be reversed!",
                inline=False
            )
            embed.set_footer(text="Click ✅ Preview to see changes or ❌ Cancel to abort • Times out in 30 seconds")
            
            # Create confirmation view with pre-formatted player changes
            view = self.UndoMatchConfirmationView(self, ctx.author.id, match_id, ctx, reason, player_changes_formatted)
            
            # Send confirmation message
            await ctx.send(embed=embed, view=view)
            
            # Wait for view completion
            await view.wait()
                
        except Exception as e:
            self.logger.error(f"Error in admin-undo-match command: {e}")
            await ctx.send(embed=discord.Embed(
                title="❌ Command Error",
                description=f"An unexpected error occurred: {str(e)}",
                color=discord.Color.red()
            ))


async def setup(bot):
    await bot.add_cog(AdminCog(bot))