"""
Discord Views for Phase 3.5 Match History System

Provides interactive paginated views for player, cluster, and event match history
with Discord embed formatting and navigation buttons.
"""

import discord
from discord.ext import commands
from typing import Optional, List
from datetime import datetime, timezone
from bot.services.match_history_service import MatchHistoryService, HistoryPage, HistoryEntry, HistoryEntryType
import logging

# Clean match format display mapping
MATCH_FORMAT_DISPLAY = {
    "MatchFormat.ONE_V_ONE": "1v1",
    "MatchFormat.TWO_V_TWO": "2v2", 
    "MatchFormat.FREE_FOR_ALL": "FFA",
    "MatchFormat.TEAM": "Team",
    "ONE_V_ONE": "1v1",
    "TWO_V_TWO": "2v2",
    "FREE_FOR_ALL": "FFA",
    "TEAM": "Team",
    "1v1": "1v1",
    "2v2": "2v2", 
    "FFA": "FFA",
    "Team": "Team"
}

logger = logging.getLogger(__name__)

class BaseHistoryView(discord.ui.View):
    """Base view for match history with pagination controls"""
    
    def __init__(self, match_history_service: MatchHistoryService, 
                 title: str, page_size: int, initial_page: HistoryPage,
                 view_type: str = "player", timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.match_history_service = match_history_service
        self.title = title
        self.page_size = page_size
        self.current_page = initial_page
        self.view_type = view_type  # "player" or "event"
        self.cursor_stack = []  # For previous page navigation
        
        # Update button states
        self._update_buttons()
    
    def _update_buttons(self):
        """Update button states based on current page"""
        # Previous button enabled if we have cursor history
        self.previous_button.disabled = len(self.cursor_stack) == 0
        
        # Next button enabled if current page has more results
        self.next_button.disabled = not self.current_page.has_next
    
    def _truncate_embed_content(self, content: str, max_length: int = 4096) -> str:
        """Truncate embed content to fit Discord limits with graceful cutoff"""
        if len(content) <= max_length:
            return content
        
        # Find last complete entry before limit
        truncated = content[:max_length - 50]  # Leave space for truncation notice
        last_newline = truncated.rfind('\n\n')
        if last_newline > 0:
            truncated = truncated[:last_newline]
        
        return truncated + "\n\n*...Content truncated due to Discord limits*"
    
    def build_embed(self) -> discord.Embed:
        """Build Discord embed with current page data"""
        embed = discord.Embed(
            title=f"📜 {self.title}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        
        if not self.current_page.entries:
            embed.description = "No history found."
            return embed
        
        # Build history content
        content_lines = []
        for i, entry in enumerate(self.current_page.entries):
            if entry.type == HistoryEntryType.MATCH:
                if self.view_type == "event":
                    content_lines.append(self._format_event_match_entry(entry, i + 1))
                else:
                    content_lines.append(self._format_match_entry(entry, i + 1))
            else:  # LEADERBOARD
                content_lines.append(self._format_leaderboard_entry(entry, i + 1))
        
        content = "\n\n".join(content_lines)
        embed.description = self._truncate_embed_content(content)
        
        # Add footer with page info
        page_info = f"Page {len(self.cursor_stack) + 1}"
        if self.current_page.has_next:
            page_info += " • More results available"
        embed.set_footer(text=page_info)
        
        return embed
    
    def _format_match_entry(self, entry: HistoryEntry, index: int) -> str:
        """Format a match entry for player history display"""
        # Result emoji (no draws - only win or loss)
        result_emoji = {"win": "🟢", "loss": "🔴"}.get(entry.result, "⚪")
        
        # Opponent info
        if entry.opponent_names:
            if len(entry.opponent_names) == 1:
                opponent_text = entry.opponent_names[0]
            elif len(entry.opponent_names) <= 3:
                opponent_text = ", ".join(entry.opponent_names)
            else:
                opponent_text = f"{', '.join(entry.opponent_names[:2])}, +{len(entry.opponent_names) - 2} others"
        else:
            opponent_text = "Multiple opponents"
        
        # Elo change
        elo_text = ""
        if entry.elo_change is not None:
            sign = "+" if entry.elo_change >= 0 else ""
            elo_text = f" ({sign}{entry.elo_change} Elo)"
        
        # Placement info in X/Y format
        placement_text = ""
        if entry.placement:
            # Calculate total participants: opponents + current player
            total_participants = len(entry.opponent_names or []) + 1
            placement_text = f" ({entry.placement}/{total_participants})"
        
        # Time ago
        time_ago = self._format_time_ago(entry.timestamp)
        
        return (f"**{index}.** {result_emoji} **{entry.event_name}**{placement_text}\n"
               f"     vs {opponent_text}{elo_text}\n"
               f"     {time_ago} • {entry.cluster_name}")
    
    def _format_event_match_entry(self, entry: HistoryEntry, index: int) -> str:
        """Format a match entry for event history display (match-centric view)"""
        # For event history, we show match information without player-specific bias
        
        # Use complete participant data if available
        if entry.all_participants:
            # Get accurate participant count from complete data
            total_participants = len(entry.all_participants)
            
            # Find the actual winner (placement = 1)
            winner = next((p for p in entry.all_participants if p.placement == 1), None)
            winner_name = winner.display_name if winner else "Unknown"
            
            # Build participants display with placements
            if len(entry.all_participants) <= 4:
                # For small matches, show all participants with placements
                participants_list = []
                for p in sorted(entry.all_participants, key=lambda x: x.placement):
                    elo_text = ""
                    if p.elo_change is not None:
                        sign = "+" if p.elo_change >= 0 else ""
                        elo_text = f" ({sign}{p.elo_change})"
                    participants_list.append(f"{p.placement}. {p.display_name}{elo_text}")
                participants_text = " | ".join(participants_list)
            else:
                # For large matches, show winner + sample of others
                participants_list = [f"Winner: {winner_name}"]
                others = [p for p in entry.all_participants if p.placement != 1][:3]
                for p in others:
                    participants_list.append(f"{p.placement}. {p.display_name}")
                if len(entry.all_participants) > 4:
                    participants_list.append(f"+{len(entry.all_participants) - 4} others")
                participants_text = " | ".join(participants_list)
        else:
            # Fallback to original logic if complete data not available
            total_participants = len(entry.opponent_names or []) + 1
            winner_name = "Unknown"
            participants_text = ", ".join(entry.opponent_names or [])
        
        # Clean match format display
        format_text = ""
        if entry.match_format:
            clean_format = MATCH_FORMAT_DISPLAY.get(entry.match_format, entry.match_format)
            format_text = f" • {clean_format}"
        
        # Time ago
        time_ago = self._format_time_ago(entry.timestamp)
        
        # Clean display without emoji clutter
        return (f"**{index}.** **{entry.event_name}**{format_text} ({total_participants} players)\n"
               f"     Winner: **{winner_name}**\n"
               f"     {participants_text}\n"
               f"     {time_ago} • {entry.cluster_name}")
    
    def _format_leaderboard_entry(self, entry: HistoryEntry, index: int) -> str:
        """Format a leaderboard entry for display"""
        # Score formatting
        if entry.score_direction == "LOW":
            # For time-based events, format as time if reasonable
            if entry.score < 3600:  # Less than 1 hour, probably seconds
                minutes = int(entry.score // 60)
                seconds = entry.score % 60
                score_text = f"{minutes}:{seconds:06.3f}"
            else:
                score_text = f"{entry.score:.3f}"
        else:
            # For point-based events
            if entry.score == int(entry.score):
                score_text = str(int(entry.score))
            else:
                score_text = f"{entry.score:.1f}"
        
        # Time ago
        time_ago = self._format_time_ago(entry.timestamp)
        
        return (f"**{index}.** **{entry.event_name}** (Leaderboard)\n"
               f"     Score: {score_text}\n"
               f"     {time_ago} • {entry.cluster_name}")
    
    def _format_time_ago(self, timestamp: datetime) -> str:
        """Format timestamp as 'X time ago'"""
        now = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        
        delta = now - timestamp
        
        if delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours}h ago"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes}m ago"
        else:
            return "Just now"
    
    async def _load_next_page(self):
        """Load next page of results"""
        if not self.current_page.has_next:
            return False
        
        # Save current cursor to stack for back navigation
        if self.current_page.entries:
            current_cursor = self.current_page.entries[-1].to_cursor().encode()
            self.cursor_stack.append(current_cursor)
        
        # Load next page
        next_page = await self._fetch_page(self.current_page.next_cursor)
        if next_page and next_page.entries:
            self.current_page = next_page
            self._update_buttons()
            return True
        
        return False
    
    async def _load_previous_page(self):
        """Load previous page of results"""
        if not self.cursor_stack:
            return False
        
        # Get previous cursor
        previous_cursor = self.cursor_stack.pop()
        
        # Load previous page
        previous_page = await self._fetch_page(previous_cursor)
        if previous_page and previous_page.entries:
            self.current_page = previous_page
            self._update_buttons()
            return True
        
        return False
    
    async def _fetch_page(self, cursor: Optional[str]):
        """Fetch page - implemented by subclasses"""
        raise NotImplementedError
    
    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.gray, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle previous page button"""
        await interaction.response.defer()
        
        try:
            success = await self._load_previous_page()
            if success:
                embed = self.build_embed()
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.followup.send("❌ Failed to load previous page.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error loading previous page: {e}")
            await interaction.followup.send("❌ Error loading previous page.", ephemeral=True)
    
    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.gray)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle next page button"""
        await interaction.response.defer()
        
        try:
            success = await self._load_next_page()
            if success:
                embed = self.build_embed()
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.followup.send("❌ Failed to load next page.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error loading next page: {e}")
            await interaction.followup.send("❌ Error loading next page.", ephemeral=True)
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.green)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle refresh button"""
        await interaction.response.defer()
        
        try:
            # Reload current page (start from beginning if no cursor stack)
            cursor = self.cursor_stack[-1] if self.cursor_stack else None
            refreshed_page = await self._fetch_page(cursor)
            if refreshed_page:
                self.current_page = refreshed_page
                self._update_buttons()
                embed = self.build_embed()
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.followup.send("❌ Failed to refresh.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error refreshing page: {e}")
            await interaction.followup.send("❌ Error refreshing.", ephemeral=True)


class MatchHistoryView(BaseHistoryView):
    """View for individual player match history"""
    
    def __init__(self, match_history_service: MatchHistoryService, 
                 player_id: int, player_name: str, page_size: int, 
                 initial_page: HistoryPage):
        super().__init__(
            match_history_service, 
            f"Match History - {player_name}", 
            page_size, 
            initial_page
        )
        self.player_id = player_id
    
    async def _fetch_page(self, cursor: Optional[str]):
        """Fetch player history page"""
        return await self.match_history_service.get_player_history(
            self.player_id, self.page_size, cursor
        )


class ClusterHistoryView(BaseHistoryView):
    """View for cluster match history"""
    
    def __init__(self, match_history_service: MatchHistoryService, 
                 cluster_id: int, cluster_name: str, page_size: int, 
                 initial_page: HistoryPage):
        super().__init__(
            match_history_service, 
            f"Cluster History - {cluster_name}", 
            page_size, 
            initial_page,
            view_type="event"
        )
        self.cluster_id = cluster_id
    
    async def _fetch_page(self, cursor: Optional[str]):
        """Fetch cluster history page"""
        return await self.match_history_service.get_cluster_history(
            self.cluster_id, self.page_size, cursor
        )


class EventHistoryView(BaseHistoryView):
    """View for event match history"""
    
    def __init__(self, match_history_service: MatchHistoryService, 
                 event_id: int, event_name: str, page_size: int, 
                 initial_page: HistoryPage):
        super().__init__(
            match_history_service, 
            f"Event History - {event_name}", 
            page_size, 
            initial_page,
            view_type="event"
        )
        self.event_id = event_id
    
    async def _fetch_page(self, cursor: Optional[str]):
        """Fetch event history page"""
        return await self.match_history_service.get_event_history(
            self.event_id, self.page_size, cursor
        )