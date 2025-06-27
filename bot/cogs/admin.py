import discord
from discord.ext import commands
from typing import Optional
from bot.config import Config

class AdminCog(commands.Cog):
    """Admin-only commands for managing the tournament system"""
    
    def __init__(self, bot):
        self.bot = bot
    
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
    
    

async def setup(bot):
    await bot.add_cog(AdminCog(bot))