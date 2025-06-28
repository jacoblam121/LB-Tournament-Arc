"""
Event Operations Module

This module provides business logic operations for Event management,
focused on general event utilities and cluster management.

Key functionality:
- get_or_create_default_cluster(): Ensures default cluster exists
- validate_cluster_exists(): Check cluster validity
- Session context management for event operations

Architecture Benefits:
- Clean separation of Event operation logic
- Scalable for cloud migration and analytics
- Maintains consistency with existing Event patterns
"""

from typing import Optional
from contextlib import asynccontextmanager
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Event, Cluster
from bot.config import Config
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


class EventOperationError(Exception):
    """Base exception for event operation errors"""
    pass


class EventValidationError(EventOperationError):
    """Raised when event data validation fails"""
    pass


class EventOperations:
    """
    Business logic operations for Event management utilities.
    
    This class provides operations for Event lifecycle management,
    including cluster validation and default cluster management.
    """
    
    
    def __init__(self, database):
        """Initialize with database instance"""
        self.db = database
        self.logger = logger
    
    @asynccontextmanager
    async def _get_session_context(self, session: Optional[AsyncSession] = None):
        """
        Provides a session context. Uses the provided session if available,
        otherwise creates and manages a new session.
        """
        if session:
            # If a session is provided, we do not manage its lifecycle
            yield session
        else:
            # If no session is provided, we create one and manage its lifecycle
            async with self.db.get_session() as new_session:
                yield new_session
    
    async def get_or_create_default_cluster(self) -> Cluster:
        """
        Get the default "Other" cluster, creating it if it doesn't exist.
        
        This ensures that auto-created Events always have a valid cluster
        to belong to, even in edge cases where the default cluster is missing.
        
        Returns:
            Cluster: The "Other" cluster for auto-created events
        """
        async with self.db.get_session() as session:
            try:
                # Try to get existing "Other" cluster
                cluster_result = await session.execute(
                    select(Cluster).where(Cluster.id == Config.DEFAULT_CLUSTER_ID)
                )
                cluster = cluster_result.scalar_one_or_none()
                
                if cluster:
                    return cluster
                
                # Create "Other" cluster if it doesn't exist
                self.logger.warning(f"Default cluster {Config.DEFAULT_CLUSTER_ID} not found, creating it")
                
                cluster = Cluster(
                    id=Config.DEFAULT_CLUSTER_ID,
                    number=19,
                    name="Other",
                    is_active=True
                )
                
                session.add(cluster)
                await session.commit()
                await session.refresh(cluster)
                
                self.logger.info(f"Created default 'Other' cluster with ID {Config.DEFAULT_CLUSTER_ID}")
                
                return cluster
                
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to get/create default cluster: {e}")
                raise EventOperationError(f"Database error with default cluster: {e}")
    
    
    # Utility methods
    
    async def validate_cluster_exists(self, cluster_id: int) -> bool:
        """Check if a cluster exists and is active"""
        cluster = await self.db.get_cluster_by_id(cluster_id)
        return cluster is not None and cluster.is_active
    
