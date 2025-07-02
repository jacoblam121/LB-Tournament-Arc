"""
Help Commands Cog - Phase 5.2 Implementation

This cog provides interactive help commands for the tournament bot,
offering comprehensive guidance on challenging, match reporting, and system features.

Features:
- /match-help and /challenge-help commands (aliased for convenience)
- Interactive embed with navigation buttons
- Dynamic examples using real server data
- Sections: Challenging, Reporting, Match Types, FAQ
"""

import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List
from sqlalchemy import select
from types import SimpleNamespace

from bot.database.models import Event, Player, Match, Challenge
from bot.operations.player_operations import PlayerOperations
from bot.utils.logger import setup_logger
from bot.config import Config

logger = setup_logger(__name__)

# Help content sections with dynamic placeholders
HELP_CONTENT = {
    "challenge": {
        "title": "⚔️ How to Challenge a Player",
        "description": (
            "Challenge another player to a match in any active event.\n\n"
            "**Step 1: Send the Challenge**\n"
            "```\n"
            "/challenge player:@{player2_name} event:{event_1v1_name}\n"
            "```\n\n"
            "**Step 2: Player Response (Required)**\n"
            "The challenged player receives a notification and must respond:\n"
            "• **`/accept`** - Accept the challenge and start the match\n"
            "• **`/decline`** - Decline the challenge\n"
            "• **No response** - Challenge expires in 24 hours\n\n"
            "**Challenge Types Available:**\n"
            "• **1v1**: Direct duels between two players\n"
            "• **FFA**: Free-for-all matches (3+ players)\n"
            "• **Team**: Team-based competitions\n\n"
            "**Important:** Once accepted, you'll receive a match ID to report results with."
        )
    },
    "reporting": {
        "title": "📊 Reporting Match Results",
        "description": (
            "Report your match results through a 2-step confirmation process.\n\n"
            "**Step 1: Report Results**\n"
            "```\n"
            "/match-report match_id:12345\n"
            "```\n"
            "Enter placements when prompted (1st, 2nd, 3rd, etc.)\n\n"
            "**Step 2: All Players Confirm (REQUIRED)**\n"
            "• Each participant receives a confirmation message\n"
            "• Players must **confirm** or **reject** the results\n"
            "• **All players must confirm** before Elo changes apply\n"
            "• If anyone rejects, you can re-report with corrections\n\n"
            "**Result Formats:**\n"
            "• **1v1**: Winner vs Loser\n"
            "• **FFA**: 1st place, 2nd place, 3rd place...\n"
            "• **Team**: Winning team members vs Losing team members\n\n"
            "**🚨 Critical:** No Elo changes until **everyone confirms**!"
        )
    },
    "match_types": {
        "title": "🎮 Understanding Match Types",
        "description": (
            "The tournament supports four different match types:\n\n"
            "**1v1 Matches:**\n"
            "• Traditional duels between two players\n"
            "• Winner takes Elo from loser\n"
            "• Example events: {event_1v1_name}\n\n"
            "**FFA (Free-for-All):**\n"
            "• 3+ players competing individually\n"
            "• Placement-based Elo changes\n"
            "• Example events: {event_ffa_name}\n\n"
            "**Team Matches:**\n"
            "• Team vs team competitions\n"
            "• Team formation during challenge acceptance\n"
            "• Example events: {event_team_name}\n\n"
            "**Leaderboard Events:**\n"
            "• Performance-based scoring (no Elo loss)\n"
            "• Encourages participation\n"
            "• Uses Performance Points (PP) system\n\n"
            "Each event specifies which match types it supports."
        )
    },
    "faq": {
        "title": "❓ Common Issues & FAQ",
        "description": (
            "**Q: How do I accept or decline a challenge?**\n"
            "A: Use `/accept` to accept or `/decline` to decline when you receive a challenge notification.\n\n"
            "**Q: What happens if I don't respond to a challenge?**\n"
            "A: Challenges automatically expire after 24 hours if not accepted or declined.\n\n"
            "**Q: Why won't my Elo update after reporting results?**\n"
            "A: All participants must confirm the results first. Check if everyone has confirmed.\n\n"
            "**Q: Someone rejected my match results. What now?**\n"
            "A: You can re-report the results with corrections using `/match-report` again.\n\n"
            "**Q: I can't find an event to challenge in.**\n"
            "A: Use `/events` to see all available events. Some may be temporarily inactive.\n\n"
            "**Q: How do I see my pending challenges and matches?**\n"
            "A: Use `/challenges pending` to see your active challenges and ongoing matches.\n\n"
            "**Q: Can I challenge multiple people at once?**\n"
            "A: Yes! For FFA or Team matches, specify multiple players in your challenge.\n\n"
            "**Need more help?** Contact a server admin or check the other help sections above."
        )
    }
}


class HelpView(discord.ui.View):
    """Interactive help view with navigation buttons"""
    
    def __init__(self, author, bot, player1=None, player2=None, event_1v1=None, event_ffa=None, event_team=None):
        super().__init__(timeout=180.0)
        self.author = author
        self.bot = bot
        
        # Use provided data or fallbacks
        self.player1 = player1 or SimpleNamespace(display_name="PlayerA", username="PlayerA")
        self.player2 = player2 or SimpleNamespace(display_name="PlayerB", username="PlayerB")
        self.event_1v1 = event_1v1 or SimpleNamespace(name="1v1 Event")
        self.event_ffa = event_ffa or SimpleNamespace(name="FFA Event")
        self.event_team = event_team or SimpleNamespace(name="Team Event")
        
        # Start with the challenge section
        self.current_section = "challenge"
    
    @staticmethod
    async def _fetch_dynamic_data(session):
        """Fetch real server data for dynamic examples, with fallbacks"""
        try:
            # Get sample players
            players_query = select(Player).limit(2)
            players_result = await session.execute(players_query)
            players = list(players_result.scalars())
            
            player1 = players[0] if players else SimpleNamespace(
                display_name="PlayerA", username="PlayerA"
            )
            player2 = players[1] if len(players) > 1 else SimpleNamespace(
                display_name="PlayerB", username="PlayerB"
            )
            
            # Get sample events by type
            events_query = select(Event).where(Event.is_active == True).limit(10)
            events_result = await session.execute(events_query)
            events = list(events_result.scalars())
            
            # Find events by supported scoring types
            event_1v1 = SimpleNamespace(name="1v1 Event")
            event_ffa = SimpleNamespace(name="FFA Event")
            event_team = SimpleNamespace(name="Team Event")
            
            for event in events:
                if event.supported_scoring_types:
                    types = event.supported_scoring_types.lower()
                    if "1v1" in types and event_1v1.name == "1v1 Event":
                        event_1v1 = event
                    elif "ffa" in types and event_ffa.name == "FFA Event":
                        event_ffa = event
                    elif "team" in types and event_team.name == "Team Event":
                        event_team = event
            
            return player1, player2, event_1v1, event_ffa, event_team
            
        except Exception as e:
            logger.warning(f"Failed to fetch dynamic help data: {e}")
            # Return fallback data
            return (
                SimpleNamespace(display_name="PlayerA", username="PlayerA"),
                SimpleNamespace(display_name="PlayerB", username="PlayerB"),
                SimpleNamespace(name="1v1 Event"),
                SimpleNamespace(name="FFA Event"),
                SimpleNamespace(name="Team Event")
            )
    
    def _get_embed(self, section_key: str) -> discord.Embed:
        """Create embed for the specified section"""
        section = HELP_CONTENT[section_key]
        
        # Prepare dynamic data for formatting
        format_args = {
            "player1_name": getattr(self.player1, 'display_name', 'PlayerA'),
            "player2_name": getattr(self.player2, 'display_name', 'PlayerB'),
            "event_1v1_name": getattr(self.event_1v1, 'name', '1v1 Event'),
            "event_ffa_name": getattr(self.event_ffa, 'name', 'FFA Event'),
            "event_team_name": getattr(self.event_team, 'name', 'Team Event'),
            "bot_name": self.bot.user.name if self.bot.user else "Tournament Bot",
        }
        
        embed = discord.Embed(
            title=section["title"],
            description=section["description"].format(**format_args),
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Requested by {self.author.display_name} • Use buttons to navigate")
        
        return embed
    
    async def _update_embed(self, interaction: discord.Interaction, section_key: str):
        """Update the embed to show the specified section"""
        self.current_section = section_key
        embed = self._get_embed(section_key)
        
        # Update button states (disable current section button)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                button_section = child.custom_id.split(":")[-1] if child.custom_id else ""
                child.disabled = (button_section == section_key)
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except discord.NotFound:
            # Message was deleted, ignore
            pass
    
    @discord.ui.button(label="⚔️ Challenging", style=discord.ButtonStyle.secondary, custom_id="help:challenge")
    async def challenge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_embed(interaction, "challenge")
    
    @discord.ui.button(label="📊 Reporting", style=discord.ButtonStyle.secondary, custom_id="help:reporting")
    async def reporting_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_embed(interaction, "reporting")
    
    @discord.ui.button(label="🎮 Match Types", style=discord.ButtonStyle.secondary, custom_id="help:match_types")
    async def match_types_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_embed(interaction, "match_types")
    
    @discord.ui.button(label="❓ FAQ", style=discord.ButtonStyle.secondary, custom_id="help:faq")
    async def faq_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_embed(interaction, "faq")
    
    async def on_timeout(self):
        """Disable all buttons when the view times out"""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True


class HelpCommandsCog(commands.Cog):
    """User help commands for tournament system guidance"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.player_ops = None
        self.logger = logger
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize operations after bot and database are ready"""
        if self.bot.db:
            self.player_ops = PlayerOperations(self.bot.db)
            self.logger.info("HelpCommandsCog operations initialized successfully")
    
    async def _show_help_interface(self, interaction: discord.Interaction):
        """Private method containing the shared help interface logic"""
        try:
            async with self.db.get_session() as session:
                # Fetch dynamic data
                player1, player2, event_1v1, event_ffa, event_team = await HelpView._fetch_dynamic_data(session)
                
                # Create help view with dynamic data
                help_view = HelpView(
                    interaction.user, self.bot,
                    player1=player1, player2=player2,
                    event_1v1=event_1v1, event_ffa=event_ffa, event_team=event_team
                )
                embed = help_view._get_embed("challenge")
                
                # Disable the challenge button initially since it's the default
                help_view.challenge_button.disabled = True
                
                await interaction.response.send_message(embed=embed, view=help_view, ephemeral=True)
                
        except Exception as e:
            self.logger.error(f"Error in help command: {e}")
            error_embed = discord.Embed(
                title="❌ Help System Error",
                description="Unable to load help information. Please try again later.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
    
    @app_commands.command(name="match-help", description="Get comprehensive help for match commands and tournament system")
    async def match_help(self, interaction: discord.Interaction):
        """Display interactive match help guide"""
        await self._show_help_interface(interaction)
    
    @app_commands.command(name="challenge-help", description="Get comprehensive help for challenge commands and tournament system")
    async def challenge_help(self, interaction: discord.Interaction):
        """Display interactive challenge help guide (alias for match-help)"""
        await self._show_help_interface(interaction)


async def setup(bot):
    """Add the HelpCommandsCog to the bot"""
    await bot.add_cog(HelpCommandsCog(bot))