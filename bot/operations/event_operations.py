"""
Event Operations Module - Phase 2A2.5 Subphase 2B

This module provides business logic operations for Event management,
particularly focused on dynamic Event creation for FFA matches.

Key functionality:
- create_ffa_event(): Dynamic Event creation with proper configuration
- Auto-naming with unique identifiers
- Cluster assignment (uses "Other" cluster for auto-created events)
- Consistent Event configuration for FFA matches

Architecture Benefits:
- Individual Events per FFA match (better data organization)
- Clean separation of Event creation logic
- Scalable for cloud migration and analytics
- Maintains consistency with existing Event patterns
"""

from typing import Optional
from datetime import datetime
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
    Business logic operations for Event management and dynamic creation.
    
    This class provides operations for Event lifecycle management,
    with a focus on auto-creating Events for FFA matches while maintaining
    consistency with the existing cluster and event structure.
    """
    
    # Constants for FFA Event configuration
    FFA_MIN_PLAYERS = 3
    FFA_MAX_PLAYERS = 16
    FFA_SCORING_TYPE = "FFA"
    
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
    
    async def create_ffa_event(
        self,
        participant_count: int,
        event_name_suffix: Optional[str] = None,
        cluster_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> Event:
        """
        Create a new Event specifically configured for FFA matches.
        
        This function creates individual Events for each FFA match, providing
        better data organization and analytics capabilities. Each Event is
        properly configured with FFA-specific settings.
        
        Features:
        - Auto-naming with timestamp for uniqueness
        - Uses "Other" cluster by default for general FFA matches
        - FFA-specific configuration (scoring type, player limits)
        - Validation of cluster existence
        - Atomic operation with proper error handling
        
        Args:
            participant_count: Number of participants in the FFA match
            event_name_suffix: Optional suffix for event name customization
            cluster_id: Optional cluster ID (defaults to "Other" cluster)
            
        Returns:
            Event: The created Event record
            
        Raises:
            EventValidationError: If validation fails
            EventOperationError: If database operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Use default cluster if not specified
                target_cluster_id = cluster_id or Config.DEFAULT_CLUSTER_ID
                
                # Validate cluster exists
                cluster_result = await s.execute(
                    select(Cluster).where(Cluster.id == target_cluster_id)
                )
                cluster = cluster_result.scalar_one_or_none()
                
                if not cluster:
                    raise EventValidationError(f"Cluster {target_cluster_id} not found")
                
                if not cluster.is_active:
                    raise EventValidationError(f"Cluster {target_cluster_id} is not active")
                
                # Validate participant count
                if participant_count < self.FFA_MIN_PLAYERS:
                    raise EventValidationError(
                        f"Participant count {participant_count} below minimum {self.FFA_MIN_PLAYERS}"
                    )
                
                if participant_count > self.FFA_MAX_PLAYERS:
                    raise EventValidationError(
                        f"Participant count {participant_count} above maximum {self.FFA_MAX_PLAYERS}"
                    )
                
                # Generate event name
                event_name = self._generate_ffa_event_name(participant_count, event_name_suffix)
                
                # Create Event with FFA configuration
                event = Event(
                    name=event_name,
                    cluster_id=target_cluster_id,
                    scoring_type=self.FFA_SCORING_TYPE,
                    crownslayer_pool=300,  # Standard crownslayer pool
                    is_active=True,
                    min_players=self.FFA_MIN_PLAYERS,
                    max_players=max(participant_count, self.FFA_MAX_PLAYERS),  # Allow for current match size
                    allow_challenges=False  # FFA events are for direct match creation only
                )
                
                s.add(event)
                
                if not session:  # Only commit if we manage the session
                    await s.commit()
                    await s.refresh(event)
                    # Load cluster relationship for return
                    await s.refresh(event, ['cluster'])
                else:
                    await s.flush()  # Get the ID without committing
                    await s.refresh(event)
                    # Load cluster relationship for return
                    await s.refresh(event, ['cluster'])
                
                self.logger.info(
                    f"Created FFA Event {event.id} '{event_name}' in cluster '{cluster.name}' "
                    f"for {participant_count} participants"
                )
                
                return event
                
            except Exception as e:
                if not session:  # Only rollback if we manage the session
                    await s.rollback()
                self.logger.error(f"Failed to create FFA Event: {e}")
                if isinstance(e, EventOperationError):
                    raise
                raise EventOperationError(f"Database error creating FFA Event: {e}")
    
    async def create_team_event(
        self,
        team_count: int,
        team_size: int,
        event_name_suffix: Optional[str] = None,
        cluster_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> Event:
        """
        Create a new Event specifically configured for Team matches.
        
        Similar to create_ffa_event but configured for team-based gameplay.
        
        Args:
            team_count: Number of teams
            team_size: Players per team
            event_name_suffix: Optional suffix for event name customization
            cluster_id: Optional cluster ID (defaults to "Other" cluster)
            
        Returns:
            Event: The created Event record
        """
        total_participants = team_count * team_size
        
        async with self._get_session_context(session) as s:
            try:
                # Use default cluster if not specified
                target_cluster_id = cluster_id or Config.DEFAULT_CLUSTER_ID
                
                # Validate cluster exists
                cluster_result = await s.execute(
                    select(Cluster).where(Cluster.id == target_cluster_id)
                )
                cluster = cluster_result.scalar_one_or_none()
                
                if not cluster:
                    raise EventValidationError(f"Cluster {target_cluster_id} not found")
                
                # Validate team configuration
                if team_count < 2:
                    raise EventValidationError("Team matches require at least 2 teams")
                
                if team_size < 1:
                    raise EventValidationError("Teams must have at least 1 player")
                
                if total_participants > 16:  # Reasonable limit for team matches
                    raise EventValidationError(f"Total participants {total_participants} exceeds limit of 16")
                
                # Generate event name
                event_name = self._generate_team_event_name(team_count, team_size, event_name_suffix)
                
                # Create Event with Team configuration
                event = Event(
                    name=event_name,
                    cluster_id=target_cluster_id,
                    scoring_type="Team",
                    crownslayer_pool=300,
                    is_active=True,
                    min_players=total_participants,  # Exact number required
                    max_players=total_participants,
                    allow_challenges=False  # Team events are for direct match creation only
                )
                
                s.add(event)
                
                if not session:  # Only commit if we manage the session
                    await s.commit()
                    await s.refresh(event)
                    # Load cluster relationship for return
                    await s.refresh(event, ['cluster'])
                else:
                    await s.flush()  # Get the ID without committing
                    await s.refresh(event)
                    # Load cluster relationship for return
                    await s.refresh(event, ['cluster'])
                
                self.logger.info(
                    f"Created Team Event {event.id} '{event_name}' in cluster '{cluster.name}' "
                    f"for {team_count} teams of {team_size} players each"
                )
                
                return event
                
            except Exception as e:
                if not session:  # Only rollback if we manage the session
                    await s.rollback()
                self.logger.error(f"Failed to create Team Event: {e}")
                if isinstance(e, EventOperationError):
                    raise
                raise EventOperationError(f"Database error creating Team Event: {e}")
    
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
                    select(Cluster).where(Cluster.id == self.DEFAULT_CLUSTER_ID)
                )
                cluster = cluster_result.scalar_one_or_none()
                
                if cluster:
                    return cluster
                
                # Create "Other" cluster if it doesn't exist
                self.logger.warning(f"Default cluster {self.DEFAULT_CLUSTER_ID} not found, creating it")
                
                cluster = Cluster(
                    id=self.DEFAULT_CLUSTER_ID,
                    number=19,
                    name="Other",
                    is_active=True
                )
                
                session.add(cluster)
                await session.commit()
                await session.refresh(cluster)
                
                self.logger.info(f"Created default 'Other' cluster with ID {self.DEFAULT_CLUSTER_ID}")
                
                return cluster
                
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to get/create default cluster: {e}")
                raise EventOperationError(f"Database error with default cluster: {e}")
    
    def _generate_ffa_event_name(self, participant_count: int, suffix: Optional[str] = None) -> str:
        """Generate a unique name for FFA events"""
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        base_name = f"FFA Match {participant_count}P - {timestamp}"
        
        if suffix:
            # Clean suffix (remove special characters, limit length)
            clean_suffix = self._clean_event_name_suffix(suffix)
            if clean_suffix:
                base_name = f"FFA Match {participant_count}P - {clean_suffix} - {timestamp}"
        
        # Ensure name doesn't exceed database limit (200 chars)
        if len(base_name) > 200:
            base_name = base_name[:197] + "..."
        
        return base_name
    
    def _generate_team_event_name(self, team_count: int, team_size: int, suffix: Optional[str] = None) -> str:
        """Generate a unique name for Team events"""
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        base_name = f"Team Match {team_count}x{team_size} - {timestamp}"
        
        if suffix:
            clean_suffix = self._clean_event_name_suffix(suffix)
            if clean_suffix:
                base_name = f"Team Match {team_count}x{team_size} - {clean_suffix} - {timestamp}"
        
        # Ensure name doesn't exceed database limit
        if len(base_name) > 200:
            base_name = base_name[:197] + "..."
        
        return base_name
    
    def _clean_event_name_suffix(self, suffix: str) -> str:
        """Clean and validate event name suffix"""
        if not suffix:
            return ""
        
        # Remove special characters, keep alphanumeric and basic punctuation
        import re
        cleaned = re.sub(r'[^a-zA-Z0-9\s\-_]', '', suffix.strip())
        
        # Limit length
        if len(cleaned) > 50:
            cleaned = cleaned[:50]
        
        return cleaned
    
    # Utility methods
    
    async def validate_cluster_exists(self, cluster_id: int) -> bool:
        """Check if a cluster exists and is active"""
        cluster = await self.db.get_cluster_by_id(cluster_id)
        return cluster is not None and cluster.is_active
    
    async def get_ffa_events(self, limit: int = 50) -> list[Event]:
        """Get recent FFA events for reference"""
        events = await self.db.get_all_events()
        ffa_events = [e for e in events if e.scoring_type == self.FFA_SCORING_TYPE]
        
        # Sort by creation date (newest first) and limit
        ffa_events.sort(key=lambda e: e.created_at, reverse=True)
        return ffa_events[:limit]