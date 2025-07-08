"""
Profile view components for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides interactive Discord UI components for player profiles.
"""

import discord
from discord.ui import View, Button
from typing import Optional
from bot.data_models.profile import ProfileData
from bot.utils.embeds import build_profile_embed, build_clusters_overview_embed, build_leaderboard_table_embed


class ProfileView(View):
    """Interactive view for player profiles with navigation buttons."""
    
    def __init__(self, target_user_id: int, profile_service, leaderboard_service, bot, *, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.target_user_id = target_user_id
        self.profile_service = profile_service
        self.leaderboard_service = leaderboard_service
        self.bot = bot
        self.current_view = "main"  # main, clusters, history, tickets
        
        # Add navigation buttons
        self._add_nav_buttons()
    
    def _add_nav_buttons(self):
        """Add navigation buttons based on current view."""
        # Clear existing items
        self.clear_items()
        
        if self.current_view == "main":
            # Main view buttons with proper callback wiring
            clusters_btn = Button(
                label="Clusters Overview",
                emoji="🎯",
                style=discord.ButtonStyle.primary,
                custom_id=f"profile:{self.target_user_id}:clusters"
            )
            clusters_btn.callback = self._clusters_callback
            self.add_item(clusters_btn)
            
            history_btn = Button(
                label="Match History",
                emoji="⚔️",
                style=discord.ButtonStyle.primary,
                custom_id=f"profile:{self.target_user_id}:history"
            )
            history_btn.callback = self._history_callback
            self.add_item(history_btn)
            
            tickets_btn = Button(
                label="Ticket Ledger",
                emoji="🎫",
                style=discord.ButtonStyle.primary,
                custom_id=f"profile:{self.target_user_id}:tickets"
            )
            tickets_btn.callback = self._tickets_callback
            self.add_item(tickets_btn)
            
            leaderboard_btn = Button(
                label="View on Leaderboard",
                emoji="🏆",
                style=discord.ButtonStyle.secondary,
                custom_id=f"profile:{self.target_user_id}:leaderboard"
            )
            leaderboard_btn.callback = self._leaderboard_callback
            self.add_item(leaderboard_btn)
        else:
            # Back button for sub-views
            back_btn = Button(
                label="Back to Profile",
                emoji="⬅️",
                style=discord.ButtonStyle.secondary,
                custom_id=f"profile:{self.target_user_id}:back",
                row=1
            )
            back_btn.callback = self._back_callback
            self.add_item(back_btn)
    
    async def _clusters_callback(self, interaction: discord.Interaction):
        """Handle clusters button click."""
        await interaction.response.defer()
        await self._show_clusters_view(interaction)
    
    async def _history_callback(self, interaction: discord.Interaction):
        """Handle history button click."""
        await interaction.response.defer()
        await self._show_history_view(interaction)
    
    async def _tickets_callback(self, interaction: discord.Interaction):
        """Handle tickets button click."""
        await interaction.response.defer()
        await self._show_tickets_view(interaction)
    
    async def _leaderboard_callback(self, interaction: discord.Interaction):
        """Handle leaderboard button click."""
        await interaction.response.defer()
        await self._jump_to_leaderboard(interaction)
    
    async def _back_callback(self, interaction: discord.Interaction):
        """Handle back button click."""
        await interaction.response.defer()
        self.current_view = "main"
        self._add_nav_buttons()
        
        # Fetch fresh main profile data
        try:
            profile_data = await self.profile_service.get_profile_data(self.target_user_id)
            
            # Get the target member for avatar
            target_member = self.bot.get_user(self.target_user_id)
            if not target_member:
                target_member = await self.bot.fetch_user(self.target_user_id)
            
            embed = build_profile_embed(profile_data, target_member)
            
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self
            )
        except Exception as e:
            await interaction.followup.send(f"Error loading profile: {e}", ephemeral=True)
    
    async def _show_clusters_view(self, interaction: discord.Interaction):
        """Show detailed cluster statistics."""
        self.current_view = "clusters"
        self._add_nav_buttons()
        
        try:
            # Fetch fresh data
            profile_data = await self.profile_service.get_profile_data(self.target_user_id)
            
            # Build clusters embed with field limit safety
            embed = build_clusters_overview_embed(profile_data)
            
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self
            )
        except Exception as e:
            await interaction.followup.send(f"Error loading cluster data: {e}", ephemeral=True)
    
    async def _show_history_view(self, interaction: discord.Interaction):
        """Show match history."""
        self.current_view = "history"
        self._add_nav_buttons()
        
        try:
            # Fetch fresh data
            profile_data = await self.profile_service.get_profile_data(self.target_user_id)
            
            # Build history embed
            embed = discord.Embed(
                title=f"Match History - {profile_data.display_name}",
                color=profile_data.profile_color or discord.Color.blue()
            )
            
            if profile_data.recent_matches:
                history_text = ""
                for match in profile_data.recent_matches:
                    result_emoji = "🟢" if match.result == "win" else "🔴" if match.result == "loss" else "🟡"
                    change_text = f"+{match.elo_change}" if match.elo_change > 0 else str(match.elo_change)
                    history_text += (
                        f"{result_emoji} vs {match.opponent_name} ({match.event_name})\n"
                        f"Elo: {change_text} | <t:{int(match.played_at.timestamp())}:R>\n\n"
                    )
                embed.description = history_text
            else:
                embed.description = "No recent matches found."
            
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self
            )
        except Exception as e:
            await interaction.followup.send(f"Error loading match history: {e}", ephemeral=True)
    
    async def _show_tickets_view(self, interaction: discord.Interaction):
        """Show ticket ledger (placeholder for now)."""
        self.current_view = "tickets"
        self._add_nav_buttons()
        
        try:
            # Fetch fresh data
            profile_data = await self.profile_service.get_profile_data(self.target_user_id)
            
            # Build tickets embed
            embed = discord.Embed(
                title=f"Ticket Ledger - {profile_data.display_name}",
                color=profile_data.profile_color or discord.Color.blue()
            )
            
            embed.add_field(
                name="Current Balance",
                value=f"🎫 {profile_data.ticket_balance}",
                inline=False
            )
            
            embed.description = "Detailed ticket transaction history coming soon!"
            
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self
            )
        except Exception as e:
            await interaction.followup.send(f"Error loading ticket data: {e}", ephemeral=True)
    
    async def _jump_to_leaderboard(self, interaction: discord.Interaction):
        """Navigate to leaderboard showing this player."""
        try:
            # Get player's rank and surrounding leaderboard
            player_rank = await self.leaderboard_service.get_player_rank(self.target_user_id)
            
            if player_rank:
                # Calculate which page the player is on (10 players per page)
                page_number = ((player_rank - 1) // 10) + 1
                
                # Get that page of the leaderboard
                leaderboard_data = await self.leaderboard_service.get_page(
                    leaderboard_type="overall",
                    sort_by="final_score", 
                    page=page_number,
                    page_size=10
                )
                
                # Build leaderboard embed
                embed = self._build_leaderboard_embed(leaderboard_data)
                embed.description += f"\n\n**Showing leaderboard around rank #{player_rank}**"
                
                # Create leaderboard view
                from bot.views.leaderboard import LeaderboardView
                view = LeaderboardView(
                    leaderboard_service=self.leaderboard_service,
                    leaderboard_type="overall",
                    sort_by="final_score",
                    cluster_name=None,
                    event_name=None,
                    current_page=page_number,
                    total_pages=leaderboard_data.total_pages
                )
                
                # Use followup since interaction was deferred
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.followup.send(
                    "Could not find your rank on the leaderboard.", 
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"Error loading leaderboard: {e}", 
                ephemeral=True
            )
    
    def _build_leaderboard_embed(self, leaderboard_data) -> discord.Embed:
        """Build leaderboard embed using shared utility."""
        return build_leaderboard_table_embed(leaderboard_data)
