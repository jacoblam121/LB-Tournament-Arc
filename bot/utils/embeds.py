"""
Shared embed utilities for the Discord tournament bot.

Provides reusable embed building functions to maintain consistency
and reduce code duplication across cogs and views.
"""

import discord
from typing import Optional, List
from bot.data_models.profile import ProfileData
from bot.constants import EloConstants, UIConstants


def build_profile_embed(profile_data: ProfileData, target_member: Optional[discord.abc.User]) -> discord.Embed:
    """
    Build the main profile embed with all stats.
    
    Handles Discord's 25-field limit and ensures consistent formatting
    across all profile displays.
    
    Args:
        profile_data: Profile data containing all player statistics
        target_member: Discord user/member for avatar (can be None for ghosts)
        
    Returns:
        Formatted Discord embed ready for display
    """
    # Create main embed with special gold color for #1 ranked player
    embed_color = discord.Color.gold() if profile_data.server_rank == 1 else (profile_data.profile_color or discord.Color.blue())
    embed = discord.Embed(
        title=f"🏆 Tournament Profile: {profile_data.display_name}",
        color=embed_color
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
    
    # Match stats section (no draws) with streak always displayed
    embed.add_field(
        name="⚔️ Match History",
        value=(
            f"**Total Matches:** {profile_data.total_matches}\n"
            f"**Wins:** {profile_data.wins} | **Losses:** {profile_data.losses}\n"
            f"**Win Rate:** {profile_data.win_rate:.1%}\n"
            f"**Current Streak:** {profile_data.current_streak}"
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
            f"{i+1}. {cluster.cluster_name}: {cluster.raw_elo} elo"
            for i, cluster in enumerate(profile_data.top_clusters[:3])
        ])
        embed.add_field(
            name="🏅 Top Clusters",
            value=top_cluster_text,
            inline=True
        )
    
    # Bottom clusters (Areas for Improvement) with proper ranking
    if profile_data.bottom_clusters:
        # Get the actual indices of bottom clusters in the full sorted list
        total_clusters = len(profile_data.all_clusters)
        
        # Calculate proper ranks for bottom clusters
        bottom_cluster_text = "\n".join([
            f"{total_clusters - len(profile_data.bottom_clusters) + i + 1}. {cluster.cluster_name}: {cluster.raw_elo} elo"
            for i, cluster in enumerate(profile_data.bottom_clusters)
        ])
        embed.add_field(
            name=f"{UIConstants.SKULL_EMOJI} Areas for Improvement",
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


def build_clusters_overview_embed(profile_data: ProfileData, max_clusters: int = 24) -> discord.Embed:
    """
    Build the clusters overview embed with Discord field limit safeguards.
    
    Args:
        profile_data: Profile data containing cluster statistics
        max_clusters: Maximum clusters to display (Discord limit is 25 fields)
        
    Returns:
        Formatted Discord embed with cluster overview
    """
    embed = discord.Embed(
        title=f"Cluster Overview - {profile_data.display_name}",
        color=profile_data.profile_color or discord.Color.blue()
    )
    
    if not profile_data.all_clusters:
        embed.description = "No cluster data available yet."
        return embed
    
    # Apply Discord's 25-field limit with safety margin
    clusters_to_show = profile_data.all_clusters[:max_clusters]
    
    # Add cluster fields
    for i, cluster in enumerate(clusters_to_show, 1):
        skull = f"{UIConstants.SKULL_EMOJI} " if cluster.is_below_threshold else ""
        rank_display = f"#{cluster.rank_in_cluster}" if cluster.rank_in_cluster is not None else "N/A"
        embed.add_field(
            name=f"{i}. {cluster.cluster_name}",
            value=(
                f"{skull}Scoring: {cluster.scoring_elo} | Raw: {cluster.raw_elo}\n"
                f"Matches: {cluster.matches_played} | Rank: {rank_display}"
            ),
            inline=True
        )
    
    # Add footer if we truncated the list
    if len(profile_data.all_clusters) > max_clusters:
        embed.set_footer(
            text=f"Showing {len(clusters_to_show)} of {len(profile_data.all_clusters)} total clusters."
        )
    
    return embed


def build_leaderboard_table_embed(
    leaderboard_data,
    title_suffix: str = "",
    empty_message: str = "The leaderboard is empty."
) -> discord.Embed:
    """
    Build leaderboard embed with flexible customization options.
    
    Args:
        leaderboard_data: LeaderboardPage data containing entries and metadata
        title_suffix: Additional text to append to title (e.g., " - ClusterName")
        empty_message: Custom message to show when leaderboard is empty
        
    Returns:
        Formatted Discord embed with leaderboard table
    """
    title = f"{leaderboard_data.leaderboard_type.title()} Leaderboard{title_suffix}"
    
    embed = discord.Embed(
        title=title,
        description=f"Sorted by: **{leaderboard_data.sort_by.replace('_', ' ').title()}**",
        color=discord.Color.gold()
    )
    
    if not leaderboard_data.entries:
        embed.description += f"\n\n{empty_message}"
        return embed
    
    # Table format
    lines = ["```"]
    lines.append(f"{'Rank':<6} {'Player':<20} {'Score':<8} {'S.Elo':<8} {'R.Elo':<8}")
    lines.append("-" * 60)
    
    for entry in leaderboard_data.entries:
        skull = UIConstants.SKULL_EMOJI if entry.overall_raw_elo < EloConstants.STARTING_ELO else "  "
        player_name = entry.display_name[:18]  # Truncate long names
        
        lines.append(
            f"{entry.rank:<6} {player_name:<20} "
            f"{entry.final_score:<8} {entry.overall_scoring_elo:<8} "
            f"{skull}{entry.overall_raw_elo:<6}"
        )
    
    lines.append("```")
    embed.description += "\n" + "\n".join(lines)
    
    embed.set_footer(
        text=f"Page {leaderboard_data.current_page}/{leaderboard_data.total_pages} | Total Players: {leaderboard_data.total_players}"
    )
    
    return embed