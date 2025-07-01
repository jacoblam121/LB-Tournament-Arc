"""
Admin Confirmation Modal - Phase 2.4.2 Enhancement

Provides secure confirmation dialog for destructive admin operations
with text input validation.
"""

import discord
from typing import Callable, Awaitable


class AdminConfirmationModal(discord.ui.Modal):
    """Modal for confirming destructive admin operations"""
    
    def __init__(
        self,
        title: str,
        confirmation_text: str,
        callback: Callable[[discord.Interaction], Awaitable[None]]
    ):
        super().__init__(title=title, timeout=300)
        self.confirmation_text = confirmation_text
        self.callback = callback
        
        # Add confirmation text input
        self.confirmation_input = discord.ui.TextInput(
            label=f'Type "{confirmation_text}" to confirm',
            placeholder=confirmation_text,
            required=True,
            max_length=len(confirmation_text) + 10
        )
        self.add_item(self.confirmation_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle modal submission with validation"""
        user_input = self.confirmation_input.value.strip()
        
        if user_input != self.confirmation_text:
            await interaction.response.send_message(
                f"❌ **Confirmation Failed**\n"
                f"You typed: `{user_input}`\n"
                f"Required: `{self.confirmation_text}`\n"
                f"Operation cancelled for safety.",
                ephemeral=True
            )
            return
        
        # Confirmation successful, execute callback
        await self.callback(interaction)
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal errors gracefully"""
        await interaction.response.send_message(
            f"❌ **Modal Error**\n"
            f"An error occurred during confirmation: {str(error)}\n"
            f"Operation cancelled.",
            ephemeral=True
        )