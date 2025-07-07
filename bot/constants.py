"""
Bot-wide constants for the Tournament Discord Bot.

This module contains all magic numbers and configuration values used throughout
the codebase to improve maintainability and clarity.
"""

class EloConstants:
    """Constants related to Elo calculations and scoring."""
    
    # Starting Elo for new players
    STARTING_ELO = 1000
    
    # Overall Elo calculation weights (from high-level overview section 2.6)
    # "Weighted Generalist" formula: Tier weights must sum to 1.0
    TIER_1_WEIGHT = 0.60  # Top 10 clusters: 60% weight
    TIER_2_WEIGHT = 0.25  # Clusters 11-15: 25% weight  
    TIER_3_WEIGHT = 0.15  # Clusters 16-20: 15% weight
    
    # Cluster Elo prestige multipliers (from high-level overview)
    PRESTIGE_RANK_1_MULTIPLIER = 4.0  # Best event in cluster
    PRESTIGE_RANK_2_MULTIPLIER = 2.5  # Second best event
    PRESTIGE_RANK_3_MULTIPLIER = 1.5  # Third best event
    PRESTIGE_REMAINDER_MULTIPLIER = 1.0  # Fourth+ events

class PaginationConstants:
    """Constants for paginated displays."""
    
    # Default page size for leaderboards
    DEFAULT_PAGE_SIZE = 10
    
    # Maximum items to show in profile cluster lists
    MAX_CLUSTER_DISPLAY = 20

class CacheConstants:
    """Constants for caching behavior."""
    
    # Default TTL for cached data (seconds)
    DEFAULT_CACHE_TTL = 900  # 15 minutes
    
    # Maximum cache size (number of entries)
    DEFAULT_MAX_CACHE_SIZE = 1000
    
    # Cache cleanup threshold
    CACHE_CLEANUP_THRESHOLD = 1200  # Clean when 20% over max

class UIConstants:
    """Constants for Discord UI elements."""
    
    # Embed colors
    DEFAULT_EMBED_COLOR = 0x3498db  # Blue
    GOLD_RANK_COLOR = 0xffd700     # Gold for #1 ranked players
    ERROR_COLOR = 0xe74c3c         # Red for errors
    SUCCESS_COLOR = 0x2ecc71       # Green for success
    
    # Emoji for UI elements
    SKULL_EMOJI = "💀"  # For below-threshold performance
    TROPHY_EMOJI = "🏆"  # For rankings and achievements
    TICKET_EMOJI = "🎫"  # For ticket balance