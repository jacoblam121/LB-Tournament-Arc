"""
Base service class for LB Tournament Arc bot.

Phase 1.1.1: Provides async database session management and retry logic
for all service layer operations.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Any
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class BaseService:
    """Base class for all services with async database session management."""
    
    def __init__(self, session_factory):
        """
        Initialize base service with session factory.
        
        Args:
            session_factory: Async session factory from Database class
        """
        self.session_factory = session_factory
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional scope for async database operations."""
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def execute_with_retry(self, func: Callable, max_retries: int = 3) -> Any:
        """Execute a function with automatic retry on database errors."""
        for attempt in range(max_retries):
            try:
                return await func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"Retry attempt {attempt + 1} for {func.__name__}: {e}")
                await asyncio.sleep(0.1 * (2 ** attempt))  # Exponential backoff