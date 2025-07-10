import asyncio
import logging
import traceback
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from bot.config import Config
from bot.database.database import Database
from bot.services.rate_limiter import SimpleRateLimiter
from bot.services.configuration import ConfigurationService
from bot.utils.logger import setup_logger

class TournamentBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        intents.reactions = True
        
        super().__init__(
            command_prefix=Config.COMMAND_PREFIX,
            intents=intents,
            help_command=None
        )
        
        # Attach app command error handler
        self.tree.on_error = self.on_app_command_error
        
        self.db: Optional[Database] = None
        self.rate_limiter = SimpleRateLimiter()
        self.config_service: Optional[ConfigurationService] = None
        self.logger = setup_logger(__name__)
        
    async def setup_hook(self):
        """Called when the bot is starting up"""
        self.logger.info("Setting up Tournament Bot...")
        
        # Initialize database
        self.db = Database()
        await self.db.initialize()
        
        # Initialize configuration service and load configs
        self.config_service = ConfigurationService(self.db.session_factory)
        await self.config_service.load_all()
        self.logger.info("Configuration service initialized")
        
        # Load cogs
        await self.load_cogs()
        
        # Sync slash commands
        await self._sync_commands()
        
        self.logger.info("Tournament Bot setup complete!")
        
    async def load_cogs(self):
        """Load all cogs"""
        cogs_to_load = [
            'bot.cogs.admin',
            'bot.cogs.tournament',
            'bot.cogs.player',
            'bot.cogs.challenge',
            'bot.cogs.leaderboard',
            'bot.cogs.leaderboard_commands',
            'bot.cogs.events',
            'bot.cogs.match_commands',
            'bot.cogs.housekeeping',
            'bot.cogs.help_commands'
        ]
        
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                self.logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                self.logger.error(f"Failed to load cog {cog}: {e}", exc_info=True)
    
    async def _sync_commands(self):
        """Sync slash commands with Discord"""
        # Verify commands exist before attempting to sync
        if not self.tree.get_commands():
            self.logger.warning("No application commands found to sync. Check for cog loading errors.")
            return
            
        try:
            guild_ids = Config.get_guild_ids()
            
            if guild_ids:
                # Guild-specific sync (instant updates, works in specified servers)
                self.logger.info(f"Attempting to sync commands to {len(guild_ids)} guild(s): {guild_ids}...")
                
                total_synced = 0
                for guild_id in guild_ids:
                    try:
                        guild = discord.Object(id=guild_id)
                        self.tree.copy_global_to(guild=guild)
                        synced = await self.tree.sync(guild=guild)
                        self.logger.info(f"Successfully synced {len(synced)} command(s) to guild {guild_id}")
                        
                        # Log commands for first guild only (to avoid spam)
                        if guild_id == guild_ids[0]:
                            for cmd in synced:
                                self.logger.info(f"  - {cmd.name}: {cmd.description}")
                        
                        total_synced += len(synced)
                    except discord.errors.Forbidden as e:
                        self.logger.error(f"Permission error syncing to guild {guild_id}. Ensure the bot has the 'application.commands' scope and is in the guild.", exc_info=True)
                    except discord.errors.HTTPException as e:
                        self.logger.error(f"HTTP error syncing to guild {guild_id}. Status: {e.status}, Response: {e.text}", exc_info=True)
                    except Exception as guild_error:
                        self.logger.error(f"An unexpected error occurred while syncing to guild {guild_id}", exc_info=True)
                    # Continue with other guilds
                    continue
                
                self.logger.info(f"Multi-guild sync complete: {total_synced} total command instances deployed")
            else:
                # Global sync (can take up to 1 hour, works everywhere)
                self.logger.info("Attempting to sync commands globally... (Note: This can take up to an hour to propagate)")
                synced = await self.tree.sync()
                self.logger.info(f"Successfully synced {len(synced)} command(s) globally")
                for cmd in synced:
                    self.logger.info(f"  - {cmd.name}: {cmd.description}")
        except Exception as e:
            self.logger.error(f"Failed to sync commands: {e}", exc_info=True)
            # Don't raise - bot should continue working with prefix commands
                
    async def on_ready(self):
        """Called when the bot is ready"""
        self.logger.info(f'{self.user} has connected to Discord!')
        self.logger.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Set bot status
        await self.change_presence(
            activity=discord.Game(name="Tournament Arc | !help or /help")
        )
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Global error handler for slash commands"""
        # Don't log full traceback for permission errors
        if isinstance(error, app_commands.CheckFailure):
            self.logger.info(f"Permission denied for command '{interaction.command.name if interaction.command else 'Unknown'}' by user {interaction.user}")
        else:
            self.logger.error(f"Error in app command '{interaction.command.name if interaction.command else 'Unknown'}': {error}", exc_info=True)
        
        # Handle specific error types
        if isinstance(error, app_commands.CommandOnCooldown):
            error_message = f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds."
        elif isinstance(error, app_commands.CheckFailure):
            # Check if this is an admin command based on command name
            if interaction.command and interaction.command.name.startswith('admin-'):
                error_message = "❌ Administrative Privileges Required\n\nThis command is restricted to bot administrators only."
            else:
                error_message = "❌ Permission Denied\n\nYou don't have the required permissions to use this command."
        elif isinstance(error, app_commands.MissingPermissions):
            error_message = "❌ You don't have permission to use this command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            error_message = "❌ I don't have the required permissions to execute this command."
        # Note: app_commands.MissingRequiredArgument doesn't exist in discord.py 2.x
        # This error type is handled by the command framework automatically
        else:
            error_message = "❌ An unexpected error occurred while processing your command. The developers have been notified."
        
        # Send error response
        try:
            # Create error embed for better presentation
            if isinstance(error, app_commands.CheckFailure) and interaction.command and interaction.command.name.startswith('admin-'):
                # Special embed for admin commands
                error_embed = discord.Embed(
                    title="❌ Administrative Privileges Required",
                    description="This command is restricted to bot administrators only.",
                    color=discord.Color.red()
                )
                error_embed.set_footer(text="Contact the bot owner if you believe you should have access.")
            else:
                # Generic error embed
                error_embed = discord.Embed(
                    title=error_message.split('\n')[0],  # Use first line as title
                    description='\n'.join(error_message.split('\n')[1:]) if '\n' in error_message else None,
                    color=discord.Color.red()
                )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=error_embed, ephemeral=True)
        except Exception as e:
            self.logger.error(f"Failed to send error response: {e}")
        
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global error handler for commands"""
        if isinstance(error, commands.CommandNotFound):
            return
            
        if isinstance(error, commands.CheckFailure):
            # Log permission denial without full traceback
            self.logger.info(f"Permission denied for command '{ctx.command.name if ctx.command else 'Unknown'}' by user {ctx.author}")
            
            # Check if this is an admin command (prefix commands from admin cog)
            if ctx.command and (ctx.command.name in ['shutdown', 'reload', 'dbstats'] or ctx.command.name.startswith('admin')):
                embed = discord.Embed(
                    title="❌ Administrative Privileges Required",
                    description="This command is restricted to bot administrators only.",
                    color=discord.Color.red()
                )
                embed.set_footer(text="Contact the bot owner if you believe you should have access.")
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ You don't have permission to use this command.")
            return
            
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
            return
            
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ I don't have the required permissions to execute this command.")
            return
            
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds.")
            return
            
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: `{error.param.name}`")
            return
            
        # Log unexpected errors (but not permission errors which were already handled)
        if not isinstance(error, (commands.CheckFailure, commands.MissingPermissions)):
            self.logger.error(f"Unexpected error in command {ctx.command}: {error}")
            self.logger.error(traceback.format_exc())
        
        embed = discord.Embed(
            title="❌ An error occurred",
            description="An unexpected error occurred while processing your command. The developers have been notified.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        
    async def close(self):
        """Cleanup when bot is shutting down"""
        self.logger.info("Shutting down Tournament Bot...")
        
        if self.db:
            await self.db.close()
            
        await super().close()

async def main():
    """Main entry point"""
    Config.validate()
    
    bot = TournamentBot()
    
    try:
        await bot.start(Config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        await bot.close()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        traceback.print_exc()
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())