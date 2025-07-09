"""
Time parsing utilities for leaderboard score submission.

Handles conversion between time strings and seconds for time-based events.
"""

from typing import Union
import math


def parse_time_to_seconds(time_str: str) -> float:
    """
    Parse a time string into total seconds.
    
    Supported formats:
    - HH:MM:SS.ms (e.g., 1:23:45.678)
    - MM:SS.ms (e.g., 8:30.5)
    - MM:SS (e.g., 8:00)
    - SS.ms (e.g., 45.2)
    - SS (e.g., 45)
    
    Args:
        time_str: Time string to parse
        
    Returns:
        Total seconds as float
        
    Raises:
        ValueError: If the format is invalid
    """
    time_str = time_str.strip()
    
    # Check for negative time before parsing
    if time_str.lstrip().startswith('-'):
        raise ValueError("Negative time values are not allowed")
    
    # Handle plain seconds (no colons)
    if ':' not in time_str:
        try:
            seconds = float(time_str)
            if seconds < 0 or math.isnan(seconds) or math.isinf(seconds):
                raise ValueError(f"Invalid time value: {time_str}")
            return seconds
        except ValueError:
            raise ValueError(f"Invalid time format: {time_str}")
    
    # Split by colons
    parts = time_str.split(':')
    if len(parts) > 3:
        raise ValueError("Invalid time format. Use HH:MM:SS.ms, MM:SS.ms, or SS")
    
    try:
        if len(parts) == 2:  # MM:SS or MM:SS.ms
            minutes = int(parts[0])
            seconds = float(parts[1])
            if minutes < 0 or seconds < 0 or seconds >= 60:
                raise ValueError(f"Invalid time components: minutes={minutes}, seconds={seconds}")
            total = minutes * 60 + seconds
            if math.isnan(total) or math.isinf(total):
                raise ValueError(f"Invalid time value")
            # Round to avoid floating point edge cases (e.g., 59.999 -> 60)
            return round(total, 3)
            
        elif len(parts) == 3:  # HH:MM:SS or HH:MM:SS.ms
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            if hours < 0 or minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
                raise ValueError(f"Invalid time components: hours={hours}, minutes={minutes}, seconds={seconds}")
            total = hours * 3600 + minutes * 60 + seconds
            if math.isnan(total) or math.isinf(total):
                raise ValueError(f"Invalid time value")
            # Round to avoid floating point edge cases
            return round(total, 3)
            
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid time format: {time_str}") from e


def format_seconds_to_time(seconds: float, include_ms: bool = True) -> str:
    """
    Format seconds into a human-readable time string.
    
    Args:
        seconds: Total seconds
        include_ms: Whether to include milliseconds
        
    Returns:
        Formatted time string (e.g., "8:30.5" or "1:23:45")
    """
    if seconds < 0:
        raise ValueError("Negative seconds not allowed")
    
    total_seconds = int(seconds)
    milliseconds = int((seconds - total_seconds) * 1000)
    
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    
    if include_ms and milliseconds > 0:
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
        else:
            return f"{minutes}:{secs:02d}.{milliseconds:03d}"
    else:
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

