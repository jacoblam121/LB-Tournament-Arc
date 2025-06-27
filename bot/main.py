import asyncio
import logging
import traceback
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from bot.config import Config
from bot.database.database import Database
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
        self.logger = setup_logger(__name__)
        
    async def setup_hook(self):
        """Called when the bot is starting up"""
        self.logger.info("Setting up Tournament Bot...")
        
        # Initialize database
        self.db = Database()
        await self.db.initialize()
        
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
            'bot.cogs.events',
            'bot.cogs.match_commands'
        ]
        
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                self.logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                self.logger.error(f"Failed to load cog {cog}: {e}")
    
    async def _sync_commands(self):
        """Sync slash commands with Discord"""
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
                    except Exception as guild_error:
                        self.logger.error(f"Failed to sync commands to guild {guild_id}: {guild_error}")
                        # Continue with other guilds
                        continue
                
                self.logger.info(f"Multi-guild sync complete: {total_synced} total command instances deployed")
            else:
                # Global sync (can take up to 1 hour, works everywhere)
                self.logger.info("Attempting to sync commands globally...")
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
        self.logger.error(f"Error in app command '{interaction.command.name if interaction.command else 'Unknown'}': {error}", exc_info=True)
        
        # Handle specific error types
        if isinstance(error, app_commands.CommandOnCooldown):
            error_message = f"❌ Command is on cooldown. Try again in {error.retry_after:.2f} seconds."
        elif isinstance(error, app_commands.MissingPermissions):
            error_message = "❌ You don't have permission to use this command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            error_message = "❌ I don't have the required permissions to execute this command."
        elif isinstance(error, app_commands.MissingRequiredArgument):
            error_message = f"❌ Missing required argument: `{error.param.name}`"
        else:
            error_message = "❌ An unexpected error occurred while processing your command. The developers have been notified."
        
        # Send error response
        try:
            if interaction.response.is_done():
                await interaction.followup.send(error_message, ephemeral=True)
            else:
                await interaction.response.send_message(error_message, ephemeral=True)
        except Exception as e:
            self.logger.error(f"Failed to send error response: {e}")
        
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global error handler for commands"""
        if isinstance(error, commands.CommandNotFound):
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
            
        # Log unexpected errors
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