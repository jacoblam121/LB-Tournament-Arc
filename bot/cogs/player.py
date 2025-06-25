import discord
from discord.ext import commands
from typing import Optional

from bot.database.models import Player

class PlayerCog(commands.Cog):
    """Player management commands"""
    
    def __init__(self, bot):
        self.bot = bot
        
    @commands.command(name='register', aliases=['signup'])
    async def register_player(self, ctx):
        """Register as a new player in the tournament system"""
        
        # Check if player already exists
        existing_player = await self.bot.db.get_player_by_discord_id(ctx.author.id)
        if existing_player:
            embed = discord.Embed(
                title="Already Registered",
                description=f"You're already registered with **{existing_player.elo_rating}** Elo rating.",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        # Create new player
        try:
            player = await self.bot.db.create_player(
                discord_id=ctx.author.id,
                username=ctx.author.name,
                display_name=ctx.author.display_name
            )
            
            embed = discord.Embed(
                title="🎮 Registration Successful!",
                description=f"Welcome to the Tournament Arc, {ctx.author.mention}!",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Starting Stats",
                value=f"**Elo Rating:** {player.elo_rating}\n"
                      f"**Tickets:** {player.tickets}\n"
                      f"**Matches Played:** {player.matches_played}",
                inline=False
            )
            embed.add_field(
                name="Next Steps",
                value="• Use `!profile` to view your stats\n"
                      "• Use `!games` to see available games\n"
                      "• Use `!challenge @player [game]` to start playing!",
                inline=False
            )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            self.bot.logger.error(f"Error registering player {ctx.author.id}: {e}")
            await ctx.send("❌ An error occurred during registration. Please try again.")
    
    @commands.command(name='profile', aliases=['stats', 'me'])
    async def show_profile(self, ctx, member: Optional[discord.Member] = None):
        """Show player profile and statistics"""
        
        target = member or ctx.author
        
        player = await self.bot.db.get_player_by_discord_id(target.id)
        if not player:
            if target == ctx.author:
                embed = discord.Embed(
                    title="Not Registered",
                    description="You're not registered yet! Use `!register` to get started.",
                    color=discord.Color.red()
                )
            else:
                embed = discord.Embed(
                    title="Not Registered",
                    description=f"{target.display_name} is not registered in the tournament system.",
                    color=discord.Color.red()
                )
            await ctx.send(embed=embed)
            return
        
        # Update activity for the requesting player
        if target == ctx.author:
            await self.bot.db.update_player_activity(ctx.author.id)
        
        embed = discord.Embed(
            title=f"🎮 {player.display_name}'s Profile",
            color=discord.Color.blue()
        )
        
        # Basic stats
        embed.add_field(
            name="Elo Rating",
            value=f"**{player.elo_rating}**",
            inline=True
        )
        embed.add_field(
            name="Tickets",
            value=f"🎫 {player.tickets}",
            inline=True
        )
        embed.add_field(
            name="Status",
            value="🔥 Provisional" if player.is_provisional else "✅ Ranked",
            inline=True
        )
        
        # Match statistics
        embed.add_field(
            name="Match Record",
            value=f"**Played:** {player.matches_played}\n"
                  f"**Wins:** {player.wins}\n"
                  f"**Losses:** {player.losses}\n"
                  f"**Draws:** {player.draws}",
            inline=True
        )
        
        embed.add_field(
            name="Win Rate",
            value=f"{player.win_rate:.1f}%",
            inline=True
        )
        
        embed.add_field(
            name="Registered",
            value=f"<t:{int(player.registered_at.timestamp())}:R>",
            inline=True
        )
        
        # Add user avatar
        embed.set_thumbnail(url=target.display_avatar.url)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='leaderboard', aliases=['top', 'rankings'])
    async def show_leaderboard(self, ctx, limit: int = 10):
        """Show the top players by Elo rating"""
        
        if limit < 1 or limit > 50:
            limit = 10
            
        top_players = await self.bot.db.get_leaderboard(limit)
        
        if not top_players:
            embed = discord.Embed(
                title="📊 Leaderboard",
                description="No players registered yet!",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"📊 Top {len(top_players)} Players",
            color=discord.Color.gold()
        )
        
        leaderboard_text = ""
        for i, player in enumerate(top_players, 1):
            # Medal emojis for top 3
            if i == 1:
                rank_emoji = "🥇"
            elif i == 2:
                rank_emoji = "🥈"
            elif i == 3:
                rank_emoji = "🥉"
            else:
                rank_emoji = f"`{i:2d}.`"
            
            leaderboard_text += (
                f"{rank_emoji} **{player.display_name}**\n"
                f"     {player.elo_rating} Elo • {player.matches_played} matches • {player.win_rate:.1f}% WR\n\n"
            )
        
        embed.description = leaderboard_text
        
        # Add footer with requestor's rank if they're registered
        requestor = await self.bot.db.get_player_by_discord_id(ctx.author.id)
        if requestor:
            # Get all players ordered by Elo to find rank
            all_players = await self.bot.db.get_leaderboard(1000)  # Get a large number
            try:
                requestor_rank = next(i for i, p in enumerate(all_players, 1) if p.id == requestor.id)
                embed.set_footer(text=f"Your rank: #{requestor_rank}")
            except StopIteration:
                pass
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(PlayerCog(bot))