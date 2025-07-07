"""
Leaderboard view components for Phase 2.1.1 - Complete Profile & Leaderboard Overhaul

Provides interactive Discord UI components for tournament leaderboards.
"""

import discord
from discord.ui import View, Button, Select
from typing import Optional
from bot.data_models.leaderboard import LeaderboardPage


class LeaderboardView(View):
    """Paginated, sortable leaderboard view."""
    
    def __init__(
        self,
        leaderboard_service,
        leaderboard_type: str,
        sort_by: str,
        cluster_name: Optional[str],
        event_name: Optional[str],
        current_page: int,
        total_pages: int,
        *,
        timeout: int = 900
    ):
        super().__init__(timeout=timeout)
        self.leaderboard_service = leaderboard_service
        self.leaderboard_type = leaderboard_type
        self.sort_by = sort_by
        self.cluster_name = cluster_name
        self.event_name = event_name
        self.current_page = current_page
        self.total_pages = total_pages
        
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current page."""
        self.clear_items()
        
        # Previous button
        prev_button = Button(
            label="Previous",
            style=discord.ButtonStyle.primary,
            disabled=self.current_page <= 1,
            custom_id="leaderboard:prev"
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # Page indicator
        page_indicator = Button(
            label=f"Page {self.current_page}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        self.add_item(page_indicator)
        
        # Next button
        next_button = Button(
            label="Next",
            style=discord.ButtonStyle.primary,
            disabled=self.current_page >= self.total_pages,
            custom_id="leaderboard:next"
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
        
        # Sort dropdown
        self.add_item(SortSelect(self.sort_by))
    
    async def previous_page(self, interaction: discord.Interaction):
        """Navigate to previous page."""
        await interaction.response.defer()
        if self.current_page > 1:
            self.current_page -= 1
            await self._update_leaderboard(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        """Navigate to next page."""
        await interaction.response.defer()
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self._update_leaderboard(interaction)
    
    async def _update_leaderboard(self, interaction: discord.Interaction):
        """Fetch and display updated leaderboard page."""
        try:
            # Get new page data
            page_data = await self.leaderboard_service.get_page(
                leaderboard_type=self.leaderboard_type,
                sort_by=self.sort_by,
                cluster_name=self.cluster_name,
                event_name=self.event_name,
                page=self.current_page,
                page_size=10
            )
            
            # Update total pages in case it changed
            self.total_pages = page_data.total_pages
            
            # Build new embed
            embed = self._build_leaderboard_embed(page_data)
            
            # Update buttons
            self._update_buttons()
            
            # Edit message
            await interaction.followup.edit_message(
                message_id=interaction.message.id,
                embed=embed,
                view=self
            )
        except Exception as e:
            await interaction.followup.send(f"Error updating leaderboard: {e}", ephemeral=True)
    
    def _build_leaderboard_embed(self, page_data: LeaderboardPage) -> discord.Embed:
        """Build formatted leaderboard embed."""
        title = f"{page_data.leaderboard_type.title()} Leaderboard"
        if page_data.cluster_name:
            title += f" - {page_data.cluster_name}"
        if page_data.event_name:
            title += f" - {page_data.event_name}"
        
        embed = discord.Embed(
            title=title,
            description=f"Sorted by: **{page_data.sort_by.replace('_', ' ').title()}**",
            color=discord.Color.gold()
        )
        
        if not page_data.entries:
            embed.description += "\n\nThe leaderboard is empty for this category."
            return embed
        
        # Table header
        lines = ["```"]
        lines.append(f"{'Rank':<6} {'Player':<20} {'Score':<8} {'S.Elo':<8} {'R.Elo':<8}")
        lines.append("-" * 60)
        
        # Table rows
        for entry in page_data.entries:
            skull = "💀" if entry.overall_raw_elo < 1000 else "  "
            player_name = entry.display_name[:18]  # Truncate long names
            
            lines.append(
                f"{entry.rank:<6} {player_name:<20} "
                f"{entry.final_score:<8} {entry.overall_scoring_elo:<8} "
                f"{skull}{entry.overall_raw_elo:<6}"
            )
        
        lines.append("```")
        embed.description += "\n" + "\n".join(lines)
        
        # Footer with pagination info
        embed.set_footer(
            text=f"Page {page_data.current_page}/{page_data.total_pages} | Total Players: {page_data.total_players}"
        )
        
        return embed


class SortSelect(Select):
    """Dropdown for changing sort order."""
    
    def __init__(self, current_sort: str):
        options = [
            discord.SelectOption(
                label="Final Score",
                value="final_score",
                description="Tournament ranking score",
                default=current_sort == "final_score"
            ),
            discord.SelectOption(
                label="Scoring Elo",
                value="scoring_elo",
                description="Performance-based rating",
                default=current_sort == "scoring_elo"
            ),
            discord.SelectOption(
                label="Raw Elo",
                value="raw_elo",
                description="True skill rating",
                default=current_sort == "raw_elo"
            ),
            discord.SelectOption(
                label="Shard Bonus",
                value="shard_bonus",
                description="King slayer rewards",
                default=current_sort == "shard_bonus"
            ),
            discord.SelectOption(
                label="Shop Bonus",
                value="shop_bonus",
                description="Strategic purchases",
                default=current_sort == "shop_bonus"
            )
        ]
        
        super().__init__(
            placeholder="Sort by...",
            options=options,
            custom_id="leaderboard:sort"
        )
    
    async def callback(self, interaction: discord.Interaction):
        """Handle sort change."""
        await interaction.response.defer()
        
        # Parent view will handle the actual sorting
        view: LeaderboardView = self.view
        view.sort_by = self.values[0]
        view.current_page = 1  # Reset to first page
        await view._update_leaderboard(interaction)