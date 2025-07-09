"""
Administrative Operations Module - Phase 5.3

This module provides business logic operations for administrative tournament management,
including Elo resets, match undo operations, and comprehensive audit logging.

Key functionality:
- reset_player_elo(): Reset individual player Elo ratings with audit trail
- reset_all_elo(): Reset all players' Elo ratings with backup creation
- undo_match(): Complex match undo with cascading Elo recalculation
- create_season_snapshot(): Create database snapshots for backups
- Comprehensive audit logging for all administrative actions

Architecture Benefits:
- Clean separation between Discord commands and database operations
- Reusable business logic for administrative operations
- Atomic operations with proper rollback capabilities
- Maintains consistency with existing operations patterns
- Full audit trail for compliance and debugging
"""

import json
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload

from bot.database.models import (
    Player, Event, Match, MatchParticipant, EloHistory, PlayerEventStats,
    AdminRole, AdminPermissionLog, MatchUndoLog, UndoMethod, AdminPermissionType, MatchResult,
    AdminAuditLog, SeasonSnapshot
)
from bot.utils.logger import setup_logger
from bot.utils.elo import EloCalculator
from bot.config import Config
from bot.services.player_stats_sync import PlayerStatsSyncService

logger = setup_logger(__name__)


class AdminOperationError(Exception):
    """Base exception for admin operation errors"""
    pass


class AdminPermissionError(AdminOperationError):
    """Raised when admin lacks required permissions"""
    pass


class AdminValidationError(AdminOperationError):
    """Raised when admin operation validation fails"""
    pass


class AdminOperations:
    """
    Business logic operations for administrative tournament management.
    
    This class provides atomic operations for administrative tasks including
    Elo management, match operations, and comprehensive audit logging.
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
    
    async def _create_audit_log(
        self,
        session: AsyncSession,
        admin_discord_id: int,
        action_type: str,
        target_type: Optional[str] = None,
        target_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        affected_players_count: int = 0,
        affected_events_count: int = 0
    ) -> None:
        """
        Create comprehensive audit log entry for administrative actions.
        
        Args:
            session: Database session
            admin_discord_id: Discord ID of performing admin
            action_type: Type of action (e.g., "elo_reset", "match_undo")
            target_type: Type of target (e.g., "player", "match", "event")
            target_id: ID of target entity
            details: Additional details as JSON
            reason: Admin-provided reason for action
            affected_players_count: Number of players affected by operation
            affected_events_count: Number of events affected by operation
        """
        try:
            # Create proper audit log entry using new AdminAuditLog model
            audit_entry = AdminAuditLog(
                admin_id=admin_discord_id,
                action_type=action_type,
                target_type=target_type,
                target_id=target_id,
                details=json.dumps(details or {}),
                reason=reason,
                affected_players_count=affected_players_count,
                affected_events_count=affected_events_count
            )
            
            session.add(audit_entry)
            
            self.logger.info(f"Admin audit log created: {action_type} by {admin_discord_id} on {target_type}:{target_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to create audit log: {e}")
            raise AdminOperationError(f"Failed to create audit log: {e}")
    
    async def _validate_admin_permissions(
        self,
        session: AsyncSession,
        admin_discord_id: int,
        required_permission: AdminPermissionType
    ) -> bool:
        """
        Validate that admin has required permissions for operation.
        
        Args:
            session: Database session
            admin_discord_id: Discord ID to check
            required_permission: Required permission type
            
        Returns:
            True if admin has permission (or is owner), False otherwise
        """
        # Owner always has all permissions
        if admin_discord_id == Config.OWNER_DISCORD_ID:
            return True
        
        # Check admin roles table
        admin_role_query = select(AdminRole).where(
            and_(
                AdminRole.discord_id == admin_discord_id,
                AdminRole.is_active == True
            )
        )
        
        result = await session.execute(admin_role_query)
        admin_role = result.scalar_one_or_none()
        
        if not admin_role:
            return False
        
        # Check if permission is in the role's permissions JSON
        try:
            permissions = json.loads(admin_role.permissions)
            return required_permission.value in permissions
        except (json.JSONDecodeError, AttributeError):
            return False
    
    async def reset_player_elo(
        self,
        admin_discord_id: int,
        player_discord_id: int,
        event_id: Optional[int] = None,
        reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Reset a single player's Elo rating in a specific event or all events.
        
        Args:
            admin_discord_id: Discord ID of admin performing reset
            player_discord_id: Discord ID of player to reset
            event_id: Optional event ID (if None, resets all events)
            reason: Admin-provided reason for reset
            session: Optional database session
            
        Returns:
            Dictionary with reset results and affected stats
            
        Raises:
            AdminPermissionError: If admin lacks required permissions
            AdminValidationError: If player or event not found
            AdminOperationError: If operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Validate permissions
                if not await self._validate_admin_permissions(s, admin_discord_id, AdminPermissionType.MODIFY_RATINGS):
                    raise AdminPermissionError(f"Admin {admin_discord_id} lacks MODIFY_RATINGS permission")
                
                # Get player
                player_query = select(Player).where(Player.discord_id == player_discord_id)
                result = await s.execute(player_query)
                player = result.scalar_one_or_none()
                
                if not player:
                    raise AdminValidationError(f"Player with Discord ID {player_discord_id} not found")
                
                affected_events = []
                
                if event_id:
                    # Reset specific event
                    event_query = select(Event).where(Event.id == event_id)
                    result = await s.execute(event_query)
                    event = result.scalar_one_or_none()
                    
                    if not event:
                        raise AdminValidationError(f"Event with ID {event_id} not found")
                    
                    # Get or create player event stats
                    stats_query = select(PlayerEventStats).where(
                        and_(
                            PlayerEventStats.player_id == player.id,
                            PlayerEventStats.event_id == event_id
                        )
                    )
                    result = await s.execute(stats_query)
                    stats = result.scalar_one_or_none()
                    
                    if stats:
                        old_raw_elo = stats.raw_elo
                        old_scoring_elo = stats.scoring_elo
                        
                        # Reset to starting Elo
                        stats.raw_elo = Config.STARTING_ELO
                        stats.scoring_elo = Config.STARTING_ELO
                        # Reset match statistics to return to provisional status
                        stats.matches_played = 0
                        stats.wins = 0
                        stats.losses = 0
                        stats.draws = 0
                        
                        # Create Elo history entry
                        elo_history = EloHistory(
                            player_id=player.id,
                            event_id=event_id,
                            match_id=None,  # No match associated with admin reset
                            challenge_id=None,  # No challenge associated with admin reset
                            opponent_id=None,  # No opponent for admin reset
                            old_elo=old_raw_elo,
                            new_elo=Config.STARTING_ELO,
                            elo_change=Config.STARTING_ELO - old_raw_elo,
                            match_result=MatchResult.DRAW,  # Neutral result for admin operations
                            k_factor=0  # No competitive k-factor for admin override
                        )
                        s.add(elo_history)
                        
                        affected_events.append({
                            'event_id': event_id,
                            'event_name': event.name,
                            'old_raw_elo': old_raw_elo,
                            'old_scoring_elo': old_scoring_elo,
                            'new_elo': Config.STARTING_ELO
                        })
                        
                        # Recalculate and update overall ELO aggregation
                        sync_service = PlayerStatsSyncService()
                        await sync_service.update_player_overall_stats(s, player.id)
                
                else:
                    # Reset all events for player
                    stats_query = select(PlayerEventStats).where(PlayerEventStats.player_id == player.id)
                    result = await s.execute(stats_query)
                    all_stats = result.scalars().all()
                    
                    for stats in all_stats:
                        old_raw_elo = stats.raw_elo
                        old_scoring_elo = stats.scoring_elo
                        
                        # Reset to starting Elo
                        stats.raw_elo = Config.STARTING_ELO
                        stats.scoring_elo = Config.STARTING_ELO
                        # Reset match statistics to return to provisional status
                        stats.matches_played = 0
                        stats.wins = 0
                        stats.losses = 0
                        stats.draws = 0
                        
                        # Create Elo history entry
                        elo_history = EloHistory(
                            player_id=player.id,
                            event_id=stats.event_id,
                            match_id=None,
                            challenge_id=None,  # No challenge associated with admin reset
                            opponent_id=None,  # No opponent for admin reset
                            old_elo=old_raw_elo,
                            new_elo=Config.STARTING_ELO,
                            elo_change=Config.STARTING_ELO - old_raw_elo,
                            match_result=MatchResult.DRAW,  # Neutral result for admin operations
                            k_factor=0  # No competitive k-factor for admin override
                        )
                        s.add(elo_history)
                        
                        # Get event name for logging
                        event_query = select(Event.name).where(Event.id == stats.event_id)
                        event_result = await s.execute(event_query)
                        event_name = event_result.scalar_one_or_none()
                        
                        affected_events.append({
                            'event_id': stats.event_id,
                            'event_name': event_name or 'Unknown',
                            'old_raw_elo': old_raw_elo,
                            'old_scoring_elo': old_scoring_elo,
                            'new_elo': Config.STARTING_ELO
                        })
                    
                    # Recalculate and update overall ELO aggregation for all events reset
                    sync_service = PlayerStatsSyncService()
                    await sync_service.update_player_overall_stats(s, player.id)
                
                # Create audit log
                await self._create_audit_log(
                    s,
                    admin_discord_id,
                    "elo_reset",
                    "player",
                    player.id,
                    {
                        'player_discord_id': player_discord_id,
                        'event_id': event_id,
                        'affected_events_count': len(affected_events),
                        'affected_events': affected_events[:5]  # Limit details to first 5 events
                    },
                    reason,
                    affected_players_count=1,
                    affected_events_count=len(affected_events)
                )
                
                # Commit if we manage the session
                if not session:
                    await s.commit()
                
                self.logger.info(f"Elo reset completed for player {player_discord_id} by admin {admin_discord_id}")
                
                return {
                    'success': True,
                    'player_discord_id': player_discord_id,
                    'player_username': player.username,
                    'affected_events': affected_events,
                    'reset_type': 'single_event' if event_id else 'all_events'
                }
                
            except (AdminPermissionError, AdminValidationError):
                raise
            except Exception as e:
                self.logger.error(f"Elo reset failed: {e}")
                raise AdminOperationError(f"Elo reset operation failed: {e}")
    
    async def reset_all_elo(
        self,
        admin_discord_id: int,
        event_id: Optional[int] = None,
        reason: Optional[str] = None,
        create_backup: bool = True,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Reset ALL players' Elo ratings in a specific event or all events.
        
        This is a destructive operation that requires careful validation and backup.
        
        Args:
            admin_discord_id: Discord ID of admin performing reset
            event_id: Optional event ID (if None, resets all events for all players)
            reason: Admin-provided reason for reset
            create_backup: Whether to create snapshot backup before reset
            session: Optional database session
            
        Returns:
            Dictionary with reset results and backup information
            
        Raises:
            AdminPermissionError: If admin lacks required permissions
            AdminValidationError: If event not found
            AdminOperationError: If operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Extra validation for destructive operation - require owner permissions
                if admin_discord_id != Config.OWNER_DISCORD_ID:
                    raise AdminPermissionError("Global Elo reset requires owner permissions")
                
                backup_info = None
                
                # Create backup snapshot if requested
                if create_backup:
                    backup_info = await self._create_season_snapshot(
                        s,
                        f"Pre-reset backup by admin {admin_discord_id}",
                        admin_discord_id
                    )
                
                affected_players = 0
                affected_events_count = 0
                
                if event_id:
                    # Reset specific event for all players
                    event_query = select(Event).where(Event.id == event_id)
                    result = await s.execute(event_query)
                    event = result.scalar_one_or_none()
                    
                    if not event:
                        raise AdminValidationError(f"Event with ID {event_id} not found")
                    
                    # Get all player stats for this event
                    stats_query = select(PlayerEventStats).where(PlayerEventStats.event_id == event_id)
                    result = await s.execute(stats_query)
                    all_stats = result.scalars().all()
                    
                    for stats in all_stats:
                        old_raw_elo = stats.raw_elo
                        
                        # Reset to starting Elo
                        stats.raw_elo = Config.STARTING_ELO
                        stats.scoring_elo = Config.STARTING_ELO
                        # Reset match statistics to return to provisional status
                        stats.matches_played = 0
                        stats.wins = 0
                        stats.losses = 0
                        stats.draws = 0
                        
                        # Create Elo history entry
                        elo_history = EloHistory(
                            player_id=stats.player_id,
                            event_id=event_id,
                            match_id=None,
                            challenge_id=None,  # No challenge associated with admin reset
                            opponent_id=None,  # No opponent for admin reset
                            old_elo=old_raw_elo,
                            new_elo=Config.STARTING_ELO,
                            elo_change=Config.STARTING_ELO - old_raw_elo,
                            match_result=MatchResult.DRAW,  # Neutral result for admin operations
                            k_factor=0  # No competitive k-factor for admin override
                        )
                        s.add(elo_history)
                        
                        affected_players += 1
                    
                    # Recalculate and update overall ELO aggregation for all affected players
                    sync_service = PlayerStatsSyncService()
                    players_query = select(PlayerEventStats.player_id).where(PlayerEventStats.event_id == event_id).distinct()
                    result = await s.execute(players_query)
                    affected_player_ids = [row[0] for row in result.all()]
                    
                    for player_id in affected_player_ids:
                        await sync_service.update_player_overall_stats(s, player_id)
                    
                    affected_events_count = 1
                
                else:
                    # Reset ALL events for ALL players (nuclear option)
                    stats_query = select(PlayerEventStats)
                    result = await s.execute(stats_query)
                    all_stats = result.scalars().all()
                    
                    # Track unique players and events
                    unique_players = set()
                    unique_events = set()
                    
                    for stats in all_stats:
                        old_raw_elo = stats.raw_elo
                        
                        # Reset to starting Elo
                        stats.raw_elo = Config.STARTING_ELO
                        stats.scoring_elo = Config.STARTING_ELO
                        # Reset match statistics to return to provisional status
                        stats.matches_played = 0
                        stats.wins = 0
                        stats.losses = 0
                        stats.draws = 0
                        
                        # Create Elo history entry
                        elo_history = EloHistory(
                            player_id=stats.player_id,
                            event_id=stats.event_id,
                            match_id=None,
                            challenge_id=None,  # No challenge associated with admin reset
                            opponent_id=None,  # No opponent for admin reset
                            old_elo=old_raw_elo,
                            new_elo=Config.STARTING_ELO,
                            elo_change=Config.STARTING_ELO - old_raw_elo,
                            match_result=MatchResult.DRAW,  # Neutral result for admin operations
                            k_factor=0  # No competitive k-factor for admin override
                        )
                        s.add(elo_history)
                        
                        unique_players.add(stats.player_id)
                        unique_events.add(stats.event_id)
                    
                    affected_players = len(unique_players)
                    affected_events_count = len(unique_events)
                    
                    # Recalculate and update overall ELO aggregation for all affected players
                    sync_service = PlayerStatsSyncService()
                    for player_id in unique_players:
                        await sync_service.update_player_overall_stats(s, player_id)
                
                # Create audit log
                await self._create_audit_log(
                    s,
                    admin_discord_id,
                    "elo_reset_all",
                    "global" if not event_id else "event",
                    event_id,
                    {
                        'affected_players': affected_players,
                        'affected_events': affected_events_count,
                        'backup_created': backup_info is not None,
                        'backup_id': backup_info.get('snapshot_id') if backup_info else None
                    },
                    reason,
                    affected_players_count=affected_players,
                    affected_events_count=affected_events_count
                )
                
                # Commit if we manage the session
                if not session:
                    await s.commit()
                
                self.logger.warning(f"Mass Elo reset completed by admin {admin_discord_id}: {affected_players} players, {affected_events_count} events")
                
                return {
                    'success': True,
                    'reset_type': 'single_event' if event_id else 'global',
                    'affected_players': affected_players,
                    'affected_events': affected_events_count,
                    'backup_info': backup_info
                }
                
            except (AdminPermissionError, AdminValidationError):
                raise
            except Exception as e:
                self.logger.error(f"Mass Elo reset failed: {e}")
                raise AdminOperationError(f"Mass Elo reset operation failed: {e}")
    
    async def _create_season_snapshot(
        self,
        session: AsyncSession,
        description: str,
        admin_discord_id: int,
        snapshot_type: str = "elo_backup"
    ) -> Dict[str, Any]:
        """
        Create a comprehensive snapshot of current season data for backup purposes.
        
        Args:
            session: Database session
            description: Description of the snapshot
            admin_discord_id: Admin creating the snapshot
            snapshot_type: Type of snapshot ("elo_backup", "season_end", "migration")
            
        Returns:
            Dictionary with snapshot information
        """
        try:
            # Gather comprehensive tournament state data
            
            # Get all players with their current stats
            players_query = select(Player, PlayerEventStats).join(PlayerEventStats, Player.id == PlayerEventStats.player_id)
            players_result = await session.execute(players_query)
            players_data = []
            
            for player, stats in players_result.all():
                players_data.append({
                    'player_id': player.id,
                    'discord_id': player.discord_id,
                    'username': player.username,
                    'event_id': stats.event_id,
                    'raw_elo': stats.raw_elo,
                    'scoring_elo': stats.scoring_elo,
                    'matches_played': stats.matches_played,
                    'wins': stats.wins,
                    'losses': stats.losses,
                    'draws': stats.draws
                })
            
            # Get event summary
            events_query = select(Event)
            events_result = await session.execute(events_query)
            events_data = []
            
            for event in events_result.scalars().all():
                events_data.append({
                    'event_id': event.id,
                    'name': event.name,
                    'cluster_id': event.cluster_id,
                    'scoring_type': event.scoring_type,
                    'is_active': event.is_active
                })
            
            # Get match summary (recent matches only for size management)
            matches_query = select(Match).order_by(Match.created_at.desc()).limit(1000)
            matches_result = await session.execute(matches_query)
            matches_data = []
            
            for match in matches_result.scalars().all():
                matches_data.append({
                    'match_id': match.id,
                    'event_id': match.event_id,
                    'match_format': match.match_format.value if match.match_format else None,
                    'status': match.status.value if match.status else None,
                    'created_at': match.created_at.isoformat() if match.created_at else None
                })
            
            # Compile comprehensive snapshot data
            snapshot_data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'admin_id': admin_discord_id,
                'description': description,
                'snapshot_type': snapshot_type,
                'data': {
                    'players': players_data,
                    'events': events_data,
                    'matches': matches_data[:100]  # Limit matches to keep size manageable
                },
                'statistics': {
                    'total_players': len(players_data),
                    'total_events': len(events_data),
                    'total_matches': len(matches_data)
                }
            }
            
            # Generate season name
            season_name = f"{snapshot_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Create SeasonSnapshot record
            snapshot = SeasonSnapshot(
                season_name=season_name,
                snapshot_data=json.dumps(snapshot_data),
                created_by=admin_discord_id,
                snapshot_type=snapshot_type,
                description=description,
                players_count=len(players_data),
                events_count=len(events_data),
                matches_count=len(matches_data)
            )
            
            session.add(snapshot)
            
            self.logger.info(f"Season snapshot created: {season_name} by {admin_discord_id} ({len(players_data)} players, {len(events_data)} events)")
            
            return {
                'snapshot_id': snapshot.id,
                'season_name': season_name,
                'description': description,
                'timestamp': snapshot_data['timestamp'],
                'players_count': len(players_data),
                'events_count': len(events_data),
                'matches_count': len(matches_data)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to create season snapshot: {e}")
            raise AdminOperationError(f"Failed to create backup snapshot: {e}")
    
    async def undo_match(
        self,
        admin_discord_id: int,
        match_id: int,
        reason: Optional[str] = None,
        dry_run: bool = False,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Undo a match and recalculate all subsequent matches (complex operation).
        
        This operation implements the inverse delta algorithm to efficiently undo
        a match without requiring full recalculation of the entire match history.
        
        Args:
            admin_discord_id: Discord ID of admin performing undo
            match_id: ID of match to undo
            reason: Admin-provided reason for undo
            dry_run: If True, simulate operation without making changes
            session: Optional database session
            
        Returns:
            Dictionary with undo results and affected matches
            
        Raises:
            AdminPermissionError: If admin lacks required permissions
            AdminValidationError: If match not found or already undone
            AdminOperationError: If operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Validate permissions
                if not await self._validate_admin_permissions(s, admin_discord_id, AdminPermissionType.UNDO_MATCH):
                    raise AdminPermissionError(f"Admin {admin_discord_id} lacks UNDO_MATCH permission")
                
                # Get match with participants and event/cluster context for public announcement
                match_query = select(Match).options(
                    selectinload(Match.participants),
                    selectinload(Match.event).selectinload(Event.cluster)
                ).where(Match.id == match_id)
                result = await s.execute(match_query)
                match = result.scalar_one_or_none()
                
                if not match:
                    raise AdminValidationError(f"Match with ID {match_id} not found")
                
                # Check if already undone
                undo_check_query = select(MatchUndoLog).where(MatchUndoLog.match_id == match_id)
                undo_result = await s.execute(undo_check_query)
                existing_undo = undo_result.scalar_one_or_none()
                
                if existing_undo:
                    raise AdminValidationError(f"Match {match_id} has already been undone (undo log ID: {existing_undo.id})")
                
                if not match.participants:
                    raise AdminValidationError(f"Match {match_id} has no participants to undo")
                
                affected_players = []
                elo_changes = []
                
                # Use inverse delta method: reverse each participant's Elo changes
                for participant in match.participants:
                    if participant.elo_change is not None:
                        # Get current player event stats
                        stats_query = select(PlayerEventStats).where(
                            and_(
                                PlayerEventStats.player_id == participant.player_id,
                                PlayerEventStats.event_id == match.event_id
                            )
                        )
                        stats_result = await s.execute(stats_query)
                        current_stats = stats_result.scalar_one_or_none()
                        
                        if current_stats:
                            old_raw_elo = current_stats.raw_elo
                            old_scoring_elo = current_stats.scoring_elo
                            
                            # Reverse the Elo change
                            new_raw_elo = participant.elo_before  # Restore to pre-match Elo
                            new_scoring_elo = max(new_raw_elo, Config.STARTING_ELO)  # Apply floor
                            
                            if not dry_run:
                                # Apply the reversal
                                current_stats.raw_elo = new_raw_elo
                                current_stats.scoring_elo = new_scoring_elo
                                
                                # Create Elo history entry
                                elo_history = EloHistory(
                                    player_id=participant.player_id,
                                    event_id=match.event_id,
                                    match_id=match_id,
                                    challenge_id=None,  # Match undo not tied to specific challenge
                                    opponent_id=None,  # Multi-player undo, no single opponent
                                    old_elo=old_raw_elo,
                                    new_elo=new_raw_elo,
                                    elo_change=new_raw_elo - old_raw_elo,
                                    match_result=MatchResult.DRAW,  # Neutral result for admin undo
                                    k_factor=0  # No competitive k-factor for admin undo
                                )
                                s.add(elo_history)
                            
                            elo_changes.append({
                                'player_id': participant.player_id,
                                'old_elo': old_raw_elo,
                                'new_elo': new_raw_elo,
                                'elo_change': new_raw_elo - old_raw_elo,
                                'original_match_change': participant.elo_change
                            })
                            
                            affected_players.append(participant.player_id)
                
                # Create undo log
                if not dry_run:
                    undo_log = MatchUndoLog(
                        match_id=match_id,
                        undone_by=admin_discord_id,
                        undo_method=UndoMethod.INVERSE_DELTA,
                        affected_players=len(affected_players),
                        subsequent_matches_recalculated=0,  # Inverse delta doesn't require subsequent recalc
                        reason=reason
                    )
                    s.add(undo_log)
                    
                    # Create audit log
                    await self._create_audit_log(
                        s,
                        admin_discord_id,
                        "match_undo",
                        "match",
                        match_id,
                        {
                            'undo_method': 'inverse_delta',
                            'affected_players': len(affected_players),
                            'elo_changes': elo_changes[:10]  # Limit details
                        },
                        reason,
                        affected_players_count=len(affected_players),
                        affected_events_count=1
                    )
                    
                    # Commit if we manage the session
                    if not session:
                        await s.commit()
                    
                    self.logger.info(f"Match {match_id} undone by admin {admin_discord_id} using inverse delta method")
                
                return {
                    'success': True,
                    'match_id': match_id,
                    'event_name': match.event.name if match.event else 'Unknown Event',
                    'cluster_name': match.event.cluster.name if match.event and match.event.cluster else 'Unknown Cluster',
                    'undo_method': 'inverse_delta',
                    'affected_players': len(affected_players),
                    'elo_changes': elo_changes,
                    'subsequent_matches_recalculated': 0,
                    'dry_run': dry_run
                }
                
            except (AdminPermissionError, AdminValidationError):
                raise
            except Exception as e:
                self.logger.error(f"Match undo failed: {e}")
                raise AdminOperationError(f"Match undo operation failed: {e}")
    
    async def populate_data_with_audit(
        self,
        admin_discord_id: int,
        reason: Optional[str] = None,
        csv_path: str = "LB Culling Games List.csv",
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Populate clusters and events from CSV with comprehensive audit logging.
        
        Args:
            admin_discord_id: Discord ID of admin performing operation
            reason: Admin-provided reason for data population
            csv_path: Path to CSV file to import
            session: Optional database session
            
        Returns:
            Dictionary with population results and audit information
            
        Raises:
            AdminPermissionError: If admin lacks required permissions
            AdminOperationError: If operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Validate permissions
                if not await self._validate_admin_permissions(s, admin_discord_id, AdminPermissionType.MODIFY_RATINGS):
                    raise AdminPermissionError(f"Admin {admin_discord_id} lacks data population permissions")
                
                # Import populate function
                try:
                    from populate_from_csv import populate_clusters_and_events
                except ImportError:
                    raise AdminOperationError("populate_from_csv module not available")
                
                # Execute the population operation with shared session
                self.logger.info(f"Starting CSV data population by admin {admin_discord_id}")
                populate_results = await populate_clusters_and_events(
                    csv_path=csv_path,
                    session=s,
                    db_instance=self.db
                )
                
                # Create audit log entry
                await self._create_audit_log(
                    s,
                    admin_discord_id,
                    "data_populate",
                    "global",
                    None,  # No specific target ID for global operation
                    {
                        'csv_path': csv_path,
                        'clusters_created': populate_results.get('clusters_created', 0),
                        'events_created': populate_results.get('events_created', 0),
                        'events_skipped': populate_results.get('events_skipped', 0)
                    },
                    reason,
                    affected_players_count=0,  # Data population doesn't directly affect players
                    affected_events_count=populate_results.get('events_created', 0)
                )
                
                # Commit if we manage the session
                if not session:
                    await s.commit()
                
                self.logger.info(f"CSV data population completed by admin {admin_discord_id}: {populate_results}")
                
                return {
                    'success': True,
                    'populate_results': populate_results,
                    'clusters_created': populate_results.get('clusters_created', 0),
                    'events_created': populate_results.get('events_created', 0),
                    'events_skipped': populate_results.get('events_skipped', 0),
                    'audit_logged': True
                }
                
            except (AdminPermissionError, AdminValidationError):
                raise
            except Exception as e:
                self.logger.error(f"Data population failed: {e}")
                raise AdminOperationError(f"Data population operation failed: {e}")