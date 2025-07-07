"""
Profile view components for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides interactive Discord UI components for player profiles.
"""

import discord
from discord.ui import View, Button
from typing import Optional
from bot.data_models.profile import ProfileData


class ProfileView(View):
    """Interactive view for player profiles with navigation buttons."""
    
    def __init__(self, target_user_id: int, profile_service, bot, *, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.target_user_id = target_user_id
        self.profile_service = profile_service
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
            
            embed = self._build_main_profile_embed(profile_data, target_member)
            
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
            
            # Build clusters embed
            embed = discord.Embed(
                title=f"Cluster Overview - {profile_data.display_name}",
                color=profile_data.profile_color or discord.Color.blue()
            )
            
            # Add all clusters with pagination if needed
            for i, cluster in enumerate(profile_data.all_clusters, 1):
                skull = "💀 " if cluster.is_below_threshold else ""
                embed.add_field(
                    name=f"{i}. {cluster.cluster_name}",
                    value=f"{skull}Scoring: {cluster.scoring_elo} | Raw: {cluster.raw_elo}\n"
                          f"Matches: {cluster.matches_played} | Rank: #{cluster.rank_in_cluster}",
                    inline=True
                )
            
            if not profile_data.all_clusters:
                embed.description = "No cluster data available yet."
            
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
        # TODO: Implement leaderboard navigation
        await interaction.followup.send(
            "Leaderboard navigation will be implemented in the next phase!",
            ephemeral=True
        )
    
    def _build_main_profile_embed(self, profile_data: ProfileData, target_member) -> discord.Embed:
        """Build the main profile embed with all stats."""
        # Create main embed
        embed = discord.Embed(
            title=f"🏆 Tournament Profile: {profile_data.display_name}",
            color=profile_data.profile_color or discord.Color.blue()
        )
        
        # Add user avatar
        if target_member:
            embed.set_thumbnail(url=target_member.display_avatar.url)
        
        # Core stats section
        embed.add_field(
            name="📊 Core Statistics",
            value=(
                f"**Final Score:** {profile_data.final_score:,}\n"
                f"**Scoring Elo:** {profile_data.overall_scoring_elo:,}\n"
                f"**Raw Elo:** {profile_data.overall_raw_elo:,}\n"
                f"**Server Rank:** #{profile_data.server_rank:,} / {profile_data.total_players:,}"
            ),
            inline=True
        )
        
        # Match stats section
        streak_text = f" ({profile_data.current_streak})" if profile_data.current_streak else ""
        embed.add_field(
            name="⚔️ Match History",
            value=(
                f"**Total Matches:** {profile_data.total_matches}\n"
                f"**Wins:** {profile_data.wins} | **Losses:** {profile_data.losses}\n"
                f"**Win Rate:** {profile_data.win_rate:.1%}{streak_text}"
            ),
            inline=True
        )
        
        # Tickets section
        embed.add_field(
            name="🎫 Tickets",
            value=f"**Balance:** {profile_data.ticket_balance:,}",
            inline=True
        )
        
        # Top clusters preview
        if profile_data.top_clusters:
            top_cluster_text = "\n".join([
                f"{i+1}. {cluster.cluster_name}: {cluster.scoring_elo} elo"
                for i, cluster in enumerate(profile_data.top_clusters[:3])
            ])
            embed.add_field(
                name="🏅 Top Clusters",
                value=top_cluster_text,
                inline=True
            )
        
        # Bottom clusters (Areas for Improvement)
        if profile_data.bottom_clusters:
            # Calculate proper ranking for bottom clusters
            total_clusters = len(profile_data.all_clusters)
            bottom_clusters_to_show = profile_data.bottom_clusters[-3:]  # Last 3 clusters
            bottom_cluster_text = "\n".join([
                f"{total_clusters - len(bottom_clusters_to_show) + i + 1}. {cluster.cluster_name}: {cluster.scoring_elo} elo"
                for i, cluster in enumerate(bottom_clusters_to_show)
            ])
            embed.add_field(
                name="💀 Areas for Improvement",
                value=bottom_cluster_text,
                inline=True
            )
        
        # Ghost player warning
        if profile_data.is_ghost:
            embed.add_field(
                name="⚠️ Status",
                value="This player has left the server but their data is preserved.",
                inline=False
            )
        
        embed.set_footer(
            text="Use the buttons below to explore detailed statistics"
        )
        
        return embed