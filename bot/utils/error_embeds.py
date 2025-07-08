"""
Centralized error embeds for consistent error handling across the Discord tournament bot.

Provides standardized error messages and formatting to maintain consistency
and improve user experience when errors occur.
"""

import discord
from typing import Optional


class ErrorEmbeds:
    """Centralized error embed factory for consistent error handling."""
    
    @staticmethod
    def player_not_found(member: Optional[discord.abc.User] = None) -> discord.Embed:
        """Create embed for when a player is not found in the database."""
        if member:
            description = f"{member.mention} hasn't joined the tournament yet!\n\nUse `/challenge` to start playing!"
        else:
            description = "This player hasn't joined the tournament yet!\n\nUse `/challenge` to start playing!"
        
        return discord.Embed(
            title="Player Not Found",
            description=description,
            color=discord.Color.red()
        )
    
    @staticmethod
    def no_match_history() -> discord.Embed:
        """Create embed for when a player has no match history."""
        return discord.Embed(
            title="No Match History",
            description="This player hasn't completed any matches yet.",
            color=discord.Color.orange()
        )
    
    @staticmethod
    def command_error(error: str) -> discord.Embed:
        """Create embed for general command errors."""
        return discord.Embed(
            title="Command Error",
            description=f"An error occurred: {error}\n\nPlease try again or contact an administrator.",
            color=discord.Color.red()
        )
    
    @staticmethod
    def draw_not_supported() -> discord.Embed:
        """Create embed for when users attempt to report a draw."""
        return discord.Embed(
            title="Draw Not Supported",
            description="Draws are explicitly not handled. Please cancel this match and replay.",
            color=discord.Color.red()
        )
    
    @staticmethod
    def invalid_input(message: str) -> discord.Embed:
        """Create embed for invalid user input."""
        return discord.Embed(
            title="Invalid Input",
            description=message,
            color=discord.Color.red()
        )
    
    @staticmethod
    def database_error() -> discord.Embed:
        """Create embed for database-related errors."""
        return discord.Embed(
            title="Database Error",
            description="A database error occurred. Please try again later or contact an administrator.",
            color=discord.Color.red()
        )
    
    @staticmethod
    def permission_denied() -> discord.Embed:
        """Create embed for permission errors."""
        return discord.Embed(
            title="Permission Denied",
            description="You don't have permission to perform this action.",
            color=discord.Color.red()
        )
    
    @staticmethod
    def rate_limited() -> discord.Embed:
        """Create embed for rate limiting errors."""
        return discord.Embed(
            title="Rate Limited",
            description="You're using commands too quickly. Please wait a moment and try again.",
            color=discord.Color.orange()
        )
    
    @staticmethod
    def match_not_found() -> discord.Embed:
        """Create embed for when a match is not found."""
        return discord.Embed(
            title="Match Not Found",
            description="The specified match could not be found.",
            color=discord.Color.red()
        )
    
    @staticmethod
    def challenge_not_found() -> discord.Embed:
        """Create embed for when a challenge is not found."""
        return discord.Embed(
            title="Challenge Not Found",
            description="The specified challenge could not be found.",
            color=discord.Color.red()
        )