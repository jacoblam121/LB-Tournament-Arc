"""
Event Name Parser Utility - Phase 1.5

Provides functionality to extract base event names by removing scoring type suffixes.
This enables UI aggregation while preserving the underlying data structure.
"""

import re
from typing import Optional, List


# Known scoring type suffixes to remove
SCORING_TYPE_SUFFIXES: List[str] = [
    " (1v1)",
    " (FFA)", 
    " (Team)",
    " (Leaderboard)"
]


def extract_base_event_name(event_name: str) -> str:
    """
    Extract the base event name by removing known scoring type suffixes.
    
    Args:
        event_name: Full event name potentially containing scoring type suffix
        
    Returns:
        Base event name without scoring type suffix
        
    Examples:
        "Bonk (1v1)" -> "Bonk"
        "Bonk (FFA)" -> "Bonk"
        "2v2 (Team)" -> "2v2"
        "Game (Winter Edition)" -> "Game (Winter Edition)"  # Preserves non-scoring parentheses
        "Arsenal" -> "Arsenal"  # No change if no suffix
    """
    if not event_name:
        return event_name
        
    # Check each known suffix
    for suffix in SCORING_TYPE_SUFFIXES:
        if event_name.endswith(suffix):
            return event_name[:-len(suffix)].strip()
    
    # No known suffix found, return as-is
    return event_name


def has_scoring_type_suffix(event_name: str) -> bool:
    """
    Check if an event name contains a scoring type suffix.
    
    Args:
        event_name: Event name to check
        
    Returns:
        True if the event name ends with a known scoring type suffix
    """
    return any(event_name.endswith(suffix) for suffix in SCORING_TYPE_SUFFIXES)


def get_scoring_type_from_name(event_name: str) -> Optional[str]:
    """
    Extract the scoring type from an event name suffix.
    
    Args:
        event_name: Event name potentially containing scoring type suffix
        
    Returns:
        Scoring type (without parentheses) or None if no suffix found
        
    Examples:
        "Bonk (1v1)" -> "1v1"
        "Arsenal" -> None
    """
    for suffix in SCORING_TYPE_SUFFIXES:
        if event_name.endswith(suffix):
            # Remove parentheses and spaces
            return suffix.strip(" ()")
    
    return None