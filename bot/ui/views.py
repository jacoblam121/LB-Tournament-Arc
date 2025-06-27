"""
Discord UI Views for Tournament Bot

This module contains all discord.ui.View components for interactive tournament functionality.
Components follow established patterns for error handling, logging, and database integration.

Components:
- EventBrowserView: Interactive event browsing with filtering and pagination
- PlacementModal: Dynamic placement entry for matches (will be moved here)
- MatchConfirmationView: Match result confirmation system (will be moved here)
"""

import discord
from discord.ext import commands
from typing import Optional, List, Dict, Any
import math
from bot.config import Config
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)

class EventBrowserView(discord.ui.View):
    """
    Interactive event browser with filtering and pagination.
    
    Features:
    - Cluster filtering via dropdown selection
    - Pagination with Previous/Next buttons  
    - Permission-based data filtering (admin vs regular users)
    - Event type filtering (1v1, FFA, Team, Leaderboard)
    - State management for current view
    - 5-minute timeout for browsing sessions
    """
    
    EVENTS_PER_PAGE = 10
    TIMEOUT_SECONDS = 300  # 5 minutes
    
    def __init__(self, bot, initial_interaction: discord.Interaction, initial_cluster_id: Optional[int] = None):
        """
        Initialize EventBrowserView.
        
        Args:
            bot: Bot instance for database access
            initial_interaction: Discord interaction that started this view
            initial_cluster_id: Optional cluster ID to filter by initially
        """
        super().__init__(timeout=self.TIMEOUT_SECONDS)
        self.bot = bot
        self.initial_interaction = initial_interaction
        self.logger = setup_logger(f"{__name__}.EventBrowserView")
        
        # State management
        self.current_page = 1
        self.current_cluster_id = initial_cluster_id  # None = all clusters
        self.current_filter = None  # None = all event types
        self.total_pages = 0
        self.current_events = []
        self.available_clusters = []
        
        # Permission check
        self.is_owner = initial_interaction.user.id == Config.OWNER_DISCORD_ID
        
        self.logger.info(f"EventBrowserView initialized by user {initial_interaction.user.id} with initial_cluster_id: {initial_cluster_id}")
    
    async def start(self):
        """Initialize the view and send the first message."""
        try:
            await self._load_clusters()
            await self._update_events_data()
            
            embed = await self._create_embed()
            self._update_components()
            
            await self.initial_interaction.response.send_message(embed=embed, view=self)
            self.logger.info(f"EventBrowserView started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start EventBrowserView: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to load event browser. Please try again.",
                color=discord.Color.red()
            )
            await self.initial_interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def _load_clusters(self):
        """Load available clusters for filtering."""
        try:
            self.available_clusters = await self.bot.db.get_all_clusters(active_only=not self.is_owner)
            self.logger.debug(f"Loaded {len(self.available_clusters)} clusters")
        except Exception as e:
            self.logger.error(f"Failed to load clusters: {e}")
            self.available_clusters = []
    
    async def _update_events_data(self):
        """Update events data and pagination info."""
        try:
            # Get filtered events with pagination
            events = await self.bot.db.get_all_events(
                cluster_id=self.current_cluster_id,
                active_only=not self.is_owner
            )
            
            # Apply event type filtering if set
            if self.current_filter:
                events = [e for e in events if e.scoring_type == self.current_filter]
            
            # Calculate pagination
            total_events = len(events)
            self.total_pages = math.ceil(total_events / self.EVENTS_PER_PAGE) if total_events > 0 else 1
            
            # Get events for current page
            start_idx = (self.current_page - 1) * self.EVENTS_PER_PAGE
            end_idx = start_idx + self.EVENTS_PER_PAGE
            self.current_events = events[start_idx:end_idx]
            
            self.logger.debug(f"Updated events data: {total_events} total, page {self.current_page}/{self.total_pages}")
            
        except Exception as e:
            self.logger.error(f"Failed to update events data: {e}")
            self.current_events = []
            self.total_pages = 1
    
    async def _create_embed(self) -> discord.Embed:
        """Create embed for current view state."""
        # Title with current filters
        title = "Tournament Events"
        if self.is_owner:
            title += " (Admin View)"
        
        # Add filter indicators to title
        filters = []
        if self.current_cluster_id:
            cluster_name = next((c.name for c in self.available_clusters if c.id == self.current_cluster_id), "Unknown")
            filters.append(f"Cluster: {cluster_name}")
        if self.current_filter:
            filters.append(f"Type: {self.current_filter}")
        
        if filters:
            title += f" - {', '.join(filters)}"
        
        embed = discord.Embed(title=title, color=discord.Color.blue())
        
        # Events content
        if not self.current_events:
            if self.current_cluster_id or self.current_filter:
                embed.description = "No events match the current filters."
            else:
                embed.description = "No events found." if self.is_owner else "No active events found."
                if self.is_owner:
                    embed.description += "\n\nUse `/admin-populate-data` to load from CSV."
        else:
            event_lines = []
            for i, event in enumerate(self.current_events):
                # Calculate display number based on page
                event_number = (self.current_page - 1) * self.EVENTS_PER_PAGE + i + 1
                
                # Admin sees status indicators
                if self.is_owner:
                    status = "🟢" if event.is_active else "🔴"
                    cluster_name = event.cluster.name if event.cluster else "Unknown"
                    event_lines.append(
                        f"{status} **{event_number}.** {event.name}\n"
                        f"   └ {event.scoring_type} in {cluster_name}"
                    )
                else:
                    cluster_name = event.cluster.name if event.cluster else "Unknown" 
                    event_lines.append(
                        f"**{event_number}.** {event.name}\n"
                        f"   └ {event.scoring_type} in {cluster_name}"
                    )
            
            embed.description = "\n\n".join(event_lines)
        
        # Footer with pagination
        if self.total_pages > 1:
            embed.set_footer(text=f"Page {self.current_page} of {self.total_pages}")
        
        # Admin summary in footer
        if self.is_owner and self.current_events:
            current_footer = embed.footer.text if embed.footer else ""
            total_count = len(self.current_events)
            active_count = sum(1 for e in self.current_events if e.is_active)
            summary = f"Showing {total_count} events ({active_count} active)"
            
            if current_footer:
                embed.set_footer(text=f"{current_footer} • {summary}")
            else:
                embed.set_footer(text=summary)
        
        return embed
    
    def _update_components(self):
        """Update view components based on current state."""
        self.clear_items()
        
        # Cluster filter dropdown
        if self.available_clusters:
            cluster_select = self._create_cluster_select()
            self.add_item(cluster_select)
        
        # Event type filter dropdown 
        event_type_select = self._create_event_type_select()
        self.add_item(event_type_select)
        
        # Navigation buttons
        prev_button = discord.ui.Button(
            label="◀ Previous",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page <= 1),
            row=2
        )
        prev_button.callback = self._prev_page_callback
        self.add_item(prev_button)
        
        next_button = discord.ui.Button(
            label="Next ▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_page >= self.total_pages),
            row=2
        )
        next_button.callback = self._next_page_callback
        self.add_item(next_button)
        
        # Home/Reset button
        home_button = discord.ui.Button(
            label="🏠 Home",
            style=discord.ButtonStyle.primary,
            disabled=(self.current_page == 1 and not self.current_cluster_id and not self.current_filter),
            row=2
        )
        home_button.callback = self._home_callback
        self.add_item(home_button)
    
    def _create_cluster_select(self) -> discord.ui.Select:
        """Create cluster filter dropdown."""
        # Create "All Clusters" option with proper default logic
        all_clusters_option = discord.SelectOption(
            label="All Clusters",
            value="all",
            description="Show events from all clusters",
            default=(self.current_cluster_id is None)
        )
        options = [all_clusters_option]
        
        # Create individual cluster options
        for cluster in self.available_clusters[:24]:  # Discord limit: 25 options
            is_selected = (self.current_cluster_id is not None and self.current_cluster_id == cluster.id)
            status_emoji = "🟢" if cluster.is_active else "🔴" if self.is_owner else ""
            label = f"{status_emoji} {cluster.name}".strip()
            
            cluster_option = discord.SelectOption(
                label=label,
                value=str(cluster.id),
                description=f"Cluster {cluster.number}",
                default=is_selected
            )
            options.append(cluster_option)
            
            # Debug logging for dropdown state
            if is_selected:
                self.logger.debug(f"Cluster dropdown: Setting {cluster.name} (ID: {cluster.id}) as default")
        
        select = discord.ui.Select(
            placeholder="Filter by cluster...",
            options=options,
            row=0
        )
        select.callback = self._cluster_select_callback
        return select
    
    def _create_event_type_select(self) -> discord.ui.Select:
        """Create event type filter dropdown."""
        event_types = ["1v1", "FFA", "Team", "Leaderboard"]
        
        options = [
            discord.SelectOption(
                label="All Types",
                value="all",
                description="Show all event types",
                default=(self.current_filter is None)
            )
        ]
        
        for event_type in event_types:
            options.append(
                discord.SelectOption(
                    label=event_type,
                    value=event_type,
                    description=f"Show {event_type} events only",
                    default=(self.current_filter == event_type)
                )
            )
        
        select = discord.ui.Select(
            placeholder="Filter by event type...",
            options=options,
            row=1
        )
        select.callback = self._event_type_select_callback
        return select
    
    # Callback methods
    async def _cluster_select_callback(self, interaction: discord.Interaction):
        """Handle cluster filter selection."""
        try:
            await interaction.response.defer()
            
            value = interaction.data["values"][0]
            old_cluster_id = self.current_cluster_id
            self.current_cluster_id = None if value == "all" else int(value)
            self.current_page = 1  # Reset to first page
            
            self.logger.debug(f"Cluster filter changed: {old_cluster_id} → {self.current_cluster_id} (value: {value})")
            
            await self._update_view(interaction)
            
        except Exception as e:
            self.logger.error(f"Error in cluster select callback: {e}")
            await self._handle_error(interaction, "Failed to update cluster filter.")
    
    async def _event_type_select_callback(self, interaction: discord.Interaction):
        """Handle event type filter selection."""
        try:
            await interaction.response.defer()
            
            value = interaction.data["values"][0]
            self.current_filter = None if value == "all" else value
            self.current_page = 1  # Reset to first page
            
            await self._update_view(interaction)
            
        except Exception as e:
            self.logger.error(f"Error in event type select callback: {e}")
            await self._handle_error(interaction, "Failed to update event type filter.")
    
    async def _prev_page_callback(self, interaction: discord.Interaction):
        """Handle previous page button."""
        try:
            await interaction.response.defer()
            
            if self.current_page > 1:
                self.current_page -= 1
                await self._update_view(interaction)
            
        except Exception as e:
            self.logger.error(f"Error in prev page callback: {e}")
            await self._handle_error(interaction, "Failed to navigate to previous page.")
    
    async def _next_page_callback(self, interaction: discord.Interaction):
        """Handle next page button."""
        try:
            await interaction.response.defer()
            
            if self.current_page < self.total_pages:
                self.current_page += 1
                await self._update_view(interaction)
            
        except Exception as e:
            self.logger.error(f"Error in next page callback: {e}")
            await self._handle_error(interaction, "Failed to navigate to next page.")
    
    async def _home_callback(self, interaction: discord.Interaction):
        """Handle home/reset button."""
        try:
            await interaction.response.defer()
            
            # Reset all filters and go to first page
            self.current_page = 1
            self.current_cluster_id = None
            self.current_filter = None
            
            await self._update_view(interaction)
            
        except Exception as e:
            self.logger.error(f"Error in home callback: {e}")
            await self._handle_error(interaction, "Failed to reset filters.")
    
    async def _update_view(self, interaction: discord.Interaction):
        """Update the view with new data and components."""
        try:
            await self._update_events_data()
            embed = await self._create_embed()
            self._update_components()
            
            await interaction.edit_original_response(embed=embed, view=self)
            
            self.logger.debug(f"View updated successfully for page {self.current_page}")
            
        except Exception as e:
            self.logger.error(f"Failed to update view: {e}")
            await self._handle_error(interaction, "Failed to update view.")
    
    async def _handle_error(self, interaction: discord.Interaction, message: str):
        """Handle errors with user feedback."""
        try:
            embed = discord.Embed(
                title="❌ Error",
                description=message,
                color=discord.Color.red()
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
        except:
            # Fallback if interaction is no longer valid
            self.logger.warning(f"Could not send error message to user: {message}")
    
    async def on_timeout(self):
        """Handle view timeout."""
        self.logger.info(f"EventBrowserView timed out after {self.TIMEOUT_SECONDS} seconds")
        # Note: Cannot edit message after timeout due to Discord limitations
    
    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        """Handle view interaction errors."""
        self.logger.error(f"EventBrowserView error: {error}")
        await self._handle_error(interaction, "An unexpected error occurred.")