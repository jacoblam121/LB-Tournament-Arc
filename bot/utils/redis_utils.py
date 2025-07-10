"""
Redis utility module for centralized Redis configuration and connection logic.

Provides secure Redis connection management with production validation.
"""

import os
import logging
from typing import Optional

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class RedisUtils:
    """Centralized Redis configuration and connection utilities."""
    
    @staticmethod
    def get_secure_redis_url() -> Optional[str]:
        """Get Redis URL with security validation for production deployments."""
        # Try environment variable first (for cloud deployments)
        env_redis_url = os.getenv('REDIS_URL')
        if env_redis_url:
            if RedisUtils._validate_redis_security(env_redis_url):
                return env_redis_url
            else:
                logger.error("REDIS_URL environment variable contains insecure configuration")
                return None
        
        # Check if we're in production mode
        from bot.config import Config
        if not getattr(Config, 'DEBUG', True):
            # Production mode - no insecure defaults allowed
            logger.error("Production deployment requires secure Redis configuration. Set REDIS_URL environment variable with rediss:// protocol and authentication.")
            return None
        else:
            # Development mode - allow localhost for testing
            logger.warning("Development mode: using insecure localhost Redis. Do not use in production!")
            return 'redis://localhost:6379'
    
    @staticmethod
    def _validate_redis_security(redis_url: str) -> bool:
        """Validate that Redis URL meets security requirements."""
        if not redis_url:
            return False
            
        # For production, require secure protocol and authentication
        from bot.config import Config
        if not getattr(Config, 'DEBUG', True):
            # Production mode - enforce strict security
            if not redis_url.startswith('rediss://'):
                logger.error("Production Redis must use rediss:// (TLS) protocol")
                return False
            if '@' not in redis_url:
                logger.error("Production Redis must include authentication credentials")
                return False
        else:
            # Development mode - allow localhost for testing
            if redis_url.startswith('redis://localhost') or redis_url.startswith('redis://127.0.0.1'):
                return True
            # Still validate secure connections in dev if provided
            if redis_url.startswith('rediss://'):
                return True
            logger.warning(f"Potentially insecure Redis URL in development: {redis_url}")
            return True
        
        return True
    
    @staticmethod
    async def create_redis_client() -> Optional['redis.Redis']:
        """Create a Redis client with secure configuration."""
        if not REDIS_AVAILABLE:
            return None
            
        redis_url = RedisUtils.get_secure_redis_url()
        if not redis_url:
            return None
            
        try:
            client = redis.from_url(redis_url)
            # Test connection
            await client.ping()
            logger.info("Successfully connected to Redis")
            return client
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None