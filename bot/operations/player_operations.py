"""
Player Operations Module - Phase 2A2.5 Subphase 2A

This module provides business logic operations for Player management,
particularly focused on seamless Discord user integration and auto-registration.

Key functionality:
- get_or_create_player(): Atomic Discord user → Player conversion
- Discord user data extraction and validation
- Consistent Player creation with proper defaults
- Transaction-safe operations

Architecture Benefits:
- Clean separation between Discord integration and database operations
- Reusable business logic for Player management
- Atomic operations with proper error handling
- Maintains consistency with existing Player cog patterns
"""

import discord
from typing import Optional, Union
from datetime import datetime
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import Player
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


class PlayerOperationError(Exception):
    """Base exception for player operation errors"""
    pass


class PlayerValidationError(PlayerOperationError):
    """Raised when player data validation fails"""
    pass


class PlayerOperations:
    """
    Business logic operations for Player management and Discord integration.
    
    This class provides atomic operations for Player lifecycle management,
    with a focus on seamless Discord user integration and auto-registration.
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
    
    async def get_or_create_player(
        self, 
        discord_user: Union[discord.User, discord.Member],
        update_activity: bool = True,
        session: Optional[AsyncSession] = None
    ) -> Player:
        """
        Get existing Player or create new one from Discord user (atomic operation).
        
        This is the primary function for converting Discord users to Player records.
        It handles the complete workflow: lookup → create if needed → update activity.
        
        Features:
        - Idempotent: Safe to call multiple times for same user
        - Atomic: All operations in single transaction scope
        - Activity tracking: Updates last_active timestamp
        - Validation: Ensures Discord user data is valid
        - Proper defaults: Uses Config values for new players
        
        Args:
            discord_user: Discord User or Member object
            update_activity: Whether to update last_active timestamp
            
        Returns:
            Player: Existing or newly created Player record
            
        Raises:
            PlayerValidationError: If Discord user data is invalid
            PlayerOperationError: If database operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Validate Discord user data
                await self._validate_discord_user(discord_user)
                
                # Check if player already exists
                from sqlalchemy import select
                result = await s.execute(
                    select(Player).where(Player.discord_id == discord_user.id)
                )
                existing_player = result.scalar_one_or_none()
                
                if existing_player:
                    self.logger.debug(f"Found existing Player {existing_player.id} for Discord user {discord_user.id}")
                    
                    # Update activity if requested
                    if update_activity:
                        from sqlalchemy import update, func
                        await s.execute(
                            update(Player)
                            .where(Player.discord_id == discord_user.id)
                            .values(last_active=func.now())
                        )
                        if not session:  # Only commit if we manage the session
                            await s.commit()
                        self.logger.debug(f"Updated activity for Player {existing_player.id}")
                    
                    return existing_player
                
                # Create new player
                player_data = self._extract_player_data(discord_user)
                from bot.config import Config
                new_player = Player(
                    discord_id=player_data["discord_id"],
                    username=player_data["username"],
                    display_name=player_data["display_name"],
                    elo_rating=Config.STARTING_ELO,
                    tickets=Config.STARTING_TICKETS
                )
                s.add(new_player)
                
                if not session:  # Only commit if we manage the session
                    await s.commit()
                    await s.refresh(new_player)
                else:
                    await s.flush()  # Get the ID without committing
                    await s.refresh(new_player)
                
                self.logger.info(
                    f"Created new Player {new_player.id} for Discord user {discord_user.id} "
                    f"({discord_user.display_name})"
                )
                
                return new_player
                
            except Exception as e:
                self.logger.error(f"Failed to get/create Player for Discord user {discord_user.id}: {e}")
                if isinstance(e, PlayerOperationError):
                    raise
                raise PlayerOperationError(f"Database error in get_or_create_player: {e}")
    
    async def get_player_by_discord_user(
        self, 
        discord_user: Union[discord.User, discord.Member],
        update_activity: bool = True
    ) -> Optional[Player]:
        """
        Get existing Player by Discord user (no auto-creation).
        
        This function only retrieves existing Player records without creating new ones.
        Useful when you need to check if a user is registered without auto-registering them.
        
        Args:
            discord_user: Discord User or Member object
            update_activity: Whether to update last_active timestamp if found
            
        Returns:
            Player if exists, None otherwise
        """
        try:
            await self._validate_discord_user(discord_user)
            
            player = await self.db.get_player_by_discord_id(discord_user.id)
            
            if player and update_activity:
                await self.db.update_player_activity(discord_user.id)
                self.logger.debug(f"Updated activity for Player {player.id}")
            
            return player
            
        except Exception as e:
            self.logger.error(f"Failed to get Player for Discord user {discord_user.id}: {e}")
            if isinstance(e, PlayerOperationError):
                raise
            raise PlayerOperationError(f"Database error in get_player_by_discord_user: {e}")
    
    async def bulk_get_or_create_players(
        self, 
        discord_users: list[Union[discord.User, discord.Member]],
        session: Optional[AsyncSession] = None
    ) -> list[Player]:
        """
        Get or create multiple Players efficiently.
        
        This function processes a list of Discord users and returns corresponding
        Player records, creating new ones as needed. Useful for FFA match creation
        where multiple users need to be converted to Players.
        
        Features:
        - Batch processing for efficiency
        - Individual error handling (continues on single user failure)
        - Maintains order of input list
        - Comprehensive logging for troubleshooting
        
        Args:
            discord_users: List of Discord User or Member objects
            
        Returns:
            List of Player records (same order as input)
            
        Raises:
            PlayerOperationError: If critical operation fails
        """
        if not discord_users:
            return []
        
        players = []
        failed_users = []
        
        self.logger.info(f"Processing {len(discord_users)} Discord users for Player conversion")
        
        for discord_user in discord_users:
            try:
                player = await self.get_or_create_player(discord_user, update_activity=True, session=session)
                players.append(player)
                
            except PlayerOperationError as e:
                self.logger.error(
                    f"Failed to process Discord user {discord_user.id} ({discord_user.display_name}): {e}"
                )
                failed_users.append(discord_user.display_name)
        
        if failed_users:
            self.logger.warning(f"Failed to process {len(failed_users)} users: {failed_users}")
            
            # If all users failed, raise error
            if len(failed_users) == len(discord_users):
                raise PlayerOperationError(f"Failed to process all {len(discord_users)} Discord users")
        
        self.logger.info(
            f"Successfully processed {len(players)} players, {len(failed_users)} failed"
        )
        
        return players
    
    async def _validate_discord_user(self, discord_user: Union[discord.User, discord.Member]) -> None:
        """Validate Discord user data for Player creation"""
        if not discord_user:
            raise PlayerValidationError("Discord user is None")
        
        if not discord_user.id:
            raise PlayerValidationError("Discord user has no ID")
        
        if discord_user.bot:
            raise PlayerValidationError(f"Discord user {discord_user.id} is a bot")
        
        # Check for valid username (Discord users always have names)
        if not discord_user.name or len(discord_user.name.strip()) == 0:
            raise PlayerValidationError(f"Discord user {discord_user.id} has invalid username")
    
    def _extract_player_data(self, discord_user: Union[discord.User, discord.Member]) -> dict:
        """Extract Player creation data from Discord user"""
        # Prefer display_name for more readable names, fall back to username
        display_name = discord_user.display_name or discord_user.name
        
        # Ensure display name is reasonable length (database constraint)
        if len(display_name) > 100:
            display_name = display_name[:97] + "..."
        
        return {
            "discord_id": discord_user.id,
            "username": discord_user.name,
            "display_name": display_name
        }
    
    # Utility methods for common Player operations
    
    async def validate_players_exist(self, discord_user_ids: list[int]) -> tuple[list[Player], list[int]]:
        """
        Validate that Players exist for given Discord user IDs.
        
        Args:
            discord_user_ids: List of Discord user IDs to check
            
        Returns:
            Tuple of (existing_players, missing_user_ids)
        """
        existing_players = []
        missing_user_ids = []
        
        for discord_id in discord_user_ids:
            player = await self.db.get_player_by_discord_id(discord_id)
            if player:
                existing_players.append(player)
            else:
                missing_user_ids.append(discord_id)
        
        return existing_players, missing_user_ids
    
    async def get_players_by_discord_ids(self, discord_user_ids: list[int]) -> list[Optional[Player]]:
        """
        Get Players by Discord user IDs (preserves order, includes None for missing).
        
        Args:
            discord_user_ids: List of Discord user IDs
            
        Returns:
            List of Player records (None for non-existent users)
        """
        players = []
        
        for discord_id in discord_user_ids:
            player = await self.db.get_player_by_discord_id(discord_id)
            players.append(player)
        
        return players