"""
Challenge Pagination View - Phase 2.4.3

Discord UI component for paginating through lists of challenges.
"""

import discord
from typing import List
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


class ChallengePaginationView(discord.ui.View):
    """
    Pagination view for navigating through multiple challenge embeds.
    
    Provides Previous/Next buttons to navigate through pages of challenges.
    """
    
    def __init__(self, embeds: List[discord.Embed], timeout: int = 300):
        """
        Initialize pagination view with list of embeds.
        
        Args:
            embeds: List of Discord embeds to paginate through
            timeout: Seconds before view expires (default 5 minutes)
        """
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.current_page = 0
        self.total_pages = len(embeds)
        
        # Update button states
        self._update_button_states()
    
    def _update_button_states(self):
        """Update enabled/disabled state of navigation buttons"""
        # Disable previous button on first page
        self.previous_button.disabled = self.current_page == 0
        
        # Disable next button on last page
        self.next_button.disabled = self.current_page >= self.total_pages - 1
    
    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Navigate to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self._update_button_states()
            
            await interaction.response.edit_message(
                embed=self.embeds[self.current_page],
                view=self
            )
    
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Navigate to next page"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_button_states()
            
            await interaction.response.edit_message(
                embed=self.embeds[self.current_page],
                view=self
            )
    
    async def on_timeout(self):
        """Called when the view times out"""
        # Disable all buttons when view expires
        for item in self.children:
            item.disabled = True
        
        logger.debug("ChallengePaginationView timed out")