"""
Rate limiting infrastructure for Discord commands.

Phase 1.1.1: Simple in-memory rate limiting using deques and time-based windows.
"""

import time
import asyncio
from functools import wraps
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)

class SimpleRateLimiter:
    """In-memory rate limiter for Discord commands.
    
    Note: This implementation stores request history in memory using defaultdict(deque).
    For production use with high traffic, consider implementing periodic cleanup or
    using external storage (Redis) to prevent unbounded memory growth.
    """
    
    def __init__(self):
        self._requests = defaultdict(deque)  # Memory grows with unique user:command pairs
        self._lock = asyncio.Lock()  # Async lock for concurrent access
    
    async def is_allowed(self, user_id: int, command: str, limit: int, window: int) -> bool:
        """Check if user can execute command within rate limit."""
        # Input validation: reject invalid parameters
        if limit <= 0 or window <= 0:
            return False
            
        key = f"{user_id}:{command}"
        now = time.time()
        
        async with self._lock:
            # Clean old requests outside window
            while self._requests[key] and self._requests[key][0] < now - window:
                self._requests[key].popleft()
            
            # Check if under limit
            if len(self._requests[key]) < limit:
                self._requests[key].append(now)
                return True
            
            return False

def rate_limit(command: str, limit: int = 1, window: int = 60):
    """Decorator for rate limiting Discord commands."""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, interaction, *args, **kwargs):
            # Get rate limiter from bot instance
            rate_limiter = self.bot.rate_limiter
            
            # Check if bot owner bypasses rate limits
            from bot.config import Config
            if interaction.user.id == Config.OWNER_DISCORD_ID:
                return await func(self, interaction, *args, **kwargs)
            
            if not await rate_limiter.is_allowed(interaction.user.id, command, limit, window):
                await interaction.response.send_message(
                    f"⏰ Rate limit exceeded. Please wait before using `/{command}` again.",
                    ephemeral=True
                )
                return
            
            return await func(self, interaction, *args, **kwargs)
        return wrapper
    return decorator