"""
Configuration management service for LB Tournament Arc bot.

Phase 1.2.1: Provides async configuration management with in-memory caching,
audit trail, and runtime configuration updates.
"""

import json
import logging
from typing import Any, Dict
from sqlalchemy import select
from bot.services.base import BaseService
from bot.database.models import Configuration, AuditLog

logger = logging.getLogger(__name__)

class ConfigurationService(BaseService):
    """Manages bot configuration with simple caching and audit trail."""
    
    def __init__(self, session_factory):
        """
        Initialize configuration service with session factory.
        
        Args:
            session_factory: Async session factory from Database class
        """
        super().__init__(session_factory)
        self._cache: Dict[str, Any] = {}
    
    async def load_all(self):
        """Load all configurations from database into memory with error handling."""
        new_cache = {}
        async with self.get_session() as session:
            result = await session.execute(select(Configuration))
            configs = result.scalars().all()
            
            for config in configs:
                try:
                    new_cache[config.key] = json.loads(config.value)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON for config key '{config.key}', skipping")
                    continue
        
        self._cache = new_cache
        logger.info(f"Loaded {len(self._cache)} configuration parameters")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.
        
        Args:
            key: Configuration key (e.g., 'elo.starting_elo')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self._cache.get(key, default)
    
    async def set(self, key: str, value: Any, user_id: int):
        """
        Set configuration value and persist to database with cache consistency.
        
        Args:
            key: Configuration key
            value: Configuration value (will be JSON-encoded)
            user_id: Discord user ID for audit trail
        """
        async with self.get_session() as session:
            # Get existing config
            result = await session.execute(
                select(Configuration).where(Configuration.key == key)
            )
            config = result.scalar_one_or_none()
            
            if config:
                # Update existing
                old_value = config.value
                config.value = json.dumps(value)
            else:
                # Create new
                old_value = None
                config = Configuration(
                    key=key,
                    value=json.dumps(value)
                )
                session.add(config)
            
            # Create audit log entry with safe JSON parsing
            old_value_parsed = None
            if old_value:
                try:
                    old_value_parsed = json.loads(old_value)
                except json.JSONDecodeError:
                    old_value_parsed = {"error": "invalid JSON", "raw": old_value}
            
            audit_entry = AuditLog(
                user_id=user_id,
                action='config_set',
                details=json.dumps({
                    'key': key,
                    'old_value': old_value_parsed,
                    'new_value': value
                })
            )
            session.add(audit_entry)
            
            # Commit happens automatically on context exit
        
        # Fix cache consistency by reloading after successful database write
        await self.load_all()
    
    def list_all(self) -> Dict[str, Any]:
        """
        Return all configuration values.
        
        Returns:
            Dictionary of all configuration key-value pairs
        """
        return self._cache.copy()
    
    def get_by_category(self, category: str) -> Dict[str, Any]:
        """
        Get all configuration values for a specific category.
        
        Args:
            category: Configuration category (e.g., 'elo', 'shop')
            
        Returns:
            Dictionary of configuration values for the category
        """
        prefix = f"{category}."
        return {
            key[len(prefix):]: value 
            for key, value in self._cache.items() 
            if key.startswith(prefix)
        }
    
    def get_categories(self) -> Dict[str, int]:
        """
        Get all configuration categories and their parameter counts.
        
        Returns:
            Dictionary mapping category names to parameter counts
        """
        categories = {}
        for key in self._cache.keys():
            if '.' in key:
                category = key.split('.', 1)[0]
                categories[category] = categories.get(category, 0) + 1
        return categories