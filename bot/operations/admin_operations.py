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
    AdminAuditLog, SeasonSnapshot, LeaderboardScore, PlayerEventPersonalBest, WeeklyScores, PlayerWeeklyLeaderboardElo
)
from bot.utils.logger import setup_logger
from bot.utils.elo import EloCalculator
from bot.config import Config
from bot.services.player_stats_sync import PlayerStatsSyncService
from bot.utils.redis_utils import RedisUtils

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
    
    def __init__(self, database, config_service):
        """Initialize with database and config service instances"""
        self.db = database
        self.config_service = config_service
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
                        
                        # Create Elo history entry (handle None old_raw_elo defensively)
                        safe_old_elo = old_raw_elo if old_raw_elo is not None else Config.STARTING_ELO
                        elo_history = EloHistory(
                            player_id=player.id,
                            event_id=event_id,
                            match_id=None,  # No match associated with admin reset
                            challenge_id=None,  # No challenge associated with admin reset
                            opponent_id=None,  # No opponent for admin reset
                            old_elo=safe_old_elo,
                            new_elo=Config.STARTING_ELO,
                            elo_change=Config.STARTING_ELO - safe_old_elo,
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
                        
                        # Create Elo history entry (handle None old_raw_elo defensively)
                        safe_old_elo = old_raw_elo if old_raw_elo is not None else Config.STARTING_ELO
                        elo_history = EloHistory(
                            player_id=player.id,
                            event_id=stats.event_id,
                            match_id=None,
                            challenge_id=None,  # No challenge associated with admin reset
                            opponent_id=None,  # No opponent for admin reset
                            old_elo=safe_old_elo,
                            new_elo=Config.STARTING_ELO,
                            elo_change=Config.STARTING_ELO - safe_old_elo,
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
                        
                        # Create Elo history entry (handle None old_raw_elo defensively)
                        safe_old_elo = old_raw_elo if old_raw_elo is not None else Config.STARTING_ELO
                        elo_history = EloHistory(
                            player_id=stats.player_id,
                            event_id=event_id,
                            match_id=None,
                            challenge_id=None,  # No challenge associated with admin reset
                            opponent_id=None,  # No opponent for admin reset
                            old_elo=safe_old_elo,
                            new_elo=Config.STARTING_ELO,
                            elo_change=Config.STARTING_ELO - safe_old_elo,
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
                        
                        # Create Elo history entry (handle None old_raw_elo defensively)
                        safe_old_elo = old_raw_elo if old_raw_elo is not None else Config.STARTING_ELO
                        elo_history = EloHistory(
                            player_id=stats.player_id,
                            event_id=stats.event_id,
                            match_id=None,
                            challenge_id=None,  # No challenge associated with admin reset
                            opponent_id=None,  # No opponent for admin reset
                            old_elo=safe_old_elo,
                            new_elo=Config.STARTING_ELO,
                            elo_change=Config.STARTING_ELO - safe_old_elo,
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

    async def reset_leaderboard_event(
        self,
        admin_discord_id: int,
        event_id: int,
        reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Reset leaderboard data for a specific event with race condition protection.
        
        This operation uses distributed locking to prevent race conditions with
        scoring calculations and provides atomic deletion of all leaderboard data.
        
        Args:
            admin_discord_id: Discord ID of admin performing reset
            event_id: Event ID to reset
            reason: Admin-provided reason for reset
            session: Optional database session
            
        Returns:
            Dict containing operation results and affected counts
        """
        redis_client = None
        lock_key = f"leaderboard_exclusive:{event_id}"
        
        async with self._get_session_context(session) as s:
            try:
                # Check admin permissions
                if not await self._validate_admin_permissions(s, admin_discord_id, AdminPermissionType.RESET_LEADERBOARD):
                    raise AdminOperationError(f"Admin {admin_discord_id} lacks RESET_LEADERBOARD permission")
                
                # Validate event exists
                event_query = select(Event).where(Event.id == event_id)
                event_result = await s.execute(event_query)
                event = event_result.scalar_one_or_none()
                
                if not event:
                    raise AdminValidationError(f"Event with ID {event_id} not found")
                
                # Get Redis client for distributed locking
                redis_client = await self._get_redis_client()
                
                # Use exclusive lock to prevent race conditions
                
                if redis_client:
                    # Try to acquire lock with 30-minute timeout
                    is_locked = await redis_client.set(lock_key, "1", ex=1800, nx=True)
                    
                    if not is_locked:
                        raise AdminOperationError(f"Leaderboard reset for event {event_id} is already in progress")
                
                # Count records before deletion for audit
                counts = await self._count_leaderboard_records(s, event_id)
                
                # Delete all leaderboard data (CASCADE handles related records)
                await s.execute(
                    delete(LeaderboardScore).where(LeaderboardScore.event_id == event_id)
                )
                await s.execute(
                    delete(PlayerEventPersonalBest).where(PlayerEventPersonalBest.event_id == event_id)
                )
                await s.execute(
                    delete(WeeklyScores).where(WeeklyScores.event_id == event_id)
                )
                await s.execute(
                    delete(PlayerWeeklyLeaderboardElo).where(PlayerWeeklyLeaderboardElo.event_id == event_id)
                )
                
                # Reset event statistics
                await s.execute(
                    update(Event)
                    .where(Event.id == event_id)
                    .values(
                        score_count=0,
                        score_mean=0.0,
                        score_m2=0.0
                    )
                )
                
                # Create audit log
                await self._create_audit_log(
                    s,
                    admin_discord_id,
                    "RESET_LEADERBOARD_EVENT",
                    target_type="event",
                    target_id=event_id,
                    details=counts,
                    reason=reason,
                    affected_players_count=counts.get('unique_players', 0),
                    affected_events_count=1
                )
                
                self.logger.info(f"Leaderboard reset for event {event_id} completed by admin {admin_discord_id}")
                
                # Commit if we own the session
                if not session:
                    await s.commit()
                
                return {
                    'success': True,
                    'event_id': event_id,
                    'event_name': event.name,
                    'cluster_name': event.cluster.name if event.cluster else 'Unknown Cluster',
                    'records_deleted': counts,
                    'reason': reason
                }
                        
            except (AdminPermissionError, AdminValidationError):
                raise
            except Exception as e:
                self.logger.error(f"Leaderboard reset failed: {e}")
                raise AdminOperationError(f"Leaderboard reset operation failed: {e}")
            finally:
                # Always release the lock
                if redis_client:
                    await redis_client.delete(lock_key)

    async def reset_leaderboard_all_events(
        self,
        admin_discord_id: int,
        reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Reset leaderboard data for ALL events with race condition protection.
        
        This operation uses distributed locking to prevent race conditions with
        scoring calculations and provides atomic deletion of all leaderboard data.
        
        Args:
            admin_discord_id: Discord ID of admin performing reset
            reason: Admin-provided reason for reset
            session: Optional database session
            
        Returns:
            Dict containing operation results and affected counts
        """
        redis_client = None
        global_lock_key = "leaderboard_global_reset"
        
        async with self._get_session_context(session) as s:
            try:
                # Check admin permissions
                if not await self._validate_admin_permissions(s, admin_discord_id, AdminPermissionType.START_NEW_SEASON):
                    raise AdminOperationError(f"Admin {admin_discord_id} lacks START_NEW_SEASON permission")
                
                # Get all events
                events_query = select(Event)
                events_result = await s.execute(events_query)
                events = events_result.scalars().all()
                
                if not events:
                    raise AdminValidationError("No events found in the system")
                
                # Get Redis client for distributed locking
                redis_client = await self._get_redis_client()
                
                # Use global lock to prevent race conditions
                
                if redis_client:
                    # Try to acquire lock with 30-minute timeout
                    is_locked = await redis_client.set(global_lock_key, "1", ex=1800, nx=True)
                    
                    if not is_locked:
                        raise AdminOperationError("Global leaderboard reset is already in progress")
                
                # Count records before deletion for audit
                total_counts = {}
                
                for event in events:
                    event_counts = await self._count_leaderboard_records(s, event.id)
                    for key, value in event_counts.items():
                        total_counts[key] = total_counts.get(key, 0) + value
                
                # Delete all leaderboard data (CASCADE handles related records)
                await s.execute(delete(LeaderboardScore))
                await s.execute(delete(PlayerEventPersonalBest))
                await s.execute(delete(WeeklyScores))
                await s.execute(delete(PlayerWeeklyLeaderboardElo))
                
                # Reset event statistics for all events
                await s.execute(
                    update(Event).values(
                        score_count=0,
                        score_mean=0.0,
                        score_m2=0.0
                    )
                )
                
                # Create audit log
                await self._create_audit_log(
                    s,
                    admin_discord_id,
                    "RESET_LEADERBOARD_ALL_EVENTS",
                    target_type="global",
                    target_id=None,
                    details=total_counts,
                    reason=reason,
                    affected_players_count=total_counts.get('unique_players', 0),
                    affected_events_count=len(events)
                )
                
                self.logger.info(f"Global leaderboard reset completed by admin {admin_discord_id}")
                
                # Commit if we own the session
                if not session:
                    await s.commit()
                
                return {
                    'success': True,
                    'events_reset': len(events),
                    'records_deleted': total_counts,
                    'reason': reason
                }
                        
            except (AdminPermissionError, AdminValidationError):
                raise
            except Exception as e:
                self.logger.error(f"Global leaderboard reset failed: {e}")
                raise AdminOperationError(f"Global leaderboard reset operation failed: {e}")
            finally:
                    # Always release the lock
                    if redis_client:
                        await redis_client.delete(global_lock_key)

    async def _get_redis_client(self):
        """Get Redis client for distributed locking. Returns None if Redis is unavailable."""
        try:
            # Use centralized Redis utilities
            redis_client = await RedisUtils.create_redis_client()
            if redis_client is None:
                self.logger.warning("No secure Redis URL configured. Admin operations will run without locking.")
                return None
            return redis_client
        except Exception as e:
            self.logger.warning(f"Redis unavailable for distributed locking: {e}")
            return None

    async def _count_leaderboard_records(self, session: AsyncSession, event_id: int) -> Dict[str, int]:
        """Count leaderboard records for audit logging."""
        # Count LeaderboardScore records
        leaderboard_scores_query = select(func.count(LeaderboardScore.id)).where(LeaderboardScore.event_id == event_id)
        leaderboard_scores_result = await session.execute(leaderboard_scores_query)
        leaderboard_scores_count = leaderboard_scores_result.scalar() or 0
        
        # Count PlayerEventPersonalBest records
        personal_bests_query = select(func.count(PlayerEventPersonalBest.id)).where(PlayerEventPersonalBest.event_id == event_id)
        personal_bests_result = await session.execute(personal_bests_query)
        personal_bests_count = personal_bests_result.scalar() or 0
        
        # Count WeeklyScores records
        weekly_scores_query = select(func.count(WeeklyScores.id)).where(WeeklyScores.event_id == event_id)
        weekly_scores_result = await session.execute(weekly_scores_query)
        weekly_scores_count = weekly_scores_result.scalar() or 0
        
        # Count PlayerWeeklyLeaderboardElo records
        weekly_elo_query = select(func.count(PlayerWeeklyLeaderboardElo.id)).where(PlayerWeeklyLeaderboardElo.event_id == event_id)
        weekly_elo_result = await session.execute(weekly_elo_query)
        weekly_elo_count = weekly_elo_result.scalar() or 0
        
        # Count unique players affected
        unique_players_query = select(func.count(func.distinct(LeaderboardScore.player_id))).where(LeaderboardScore.event_id == event_id)
        unique_players_result = await session.execute(unique_players_query)
        unique_players_count = unique_players_result.scalar() or 0
        
        return {
            'leaderboard_scores': leaderboard_scores_count,
            'personal_bests': personal_bests_count,
            'weekly_scores': weekly_scores_count,
            'weekly_elo': weekly_elo_count,
            'unique_players': unique_players_count
        }

    async def reset_player_match_history(
        self,
        admin_discord_id: int,
        player_id: int,
        reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Reset a single player's complete match history and statistics.
        
        This operation removes all match history, resets event statistics,
        and zeroes player aggregate statistics with full audit logging.
        
        Args:
            admin_discord_id: Discord ID of admin performing reset
            player_id: Database ID of player to reset
            reason: Admin-provided reason for reset
            session: Optional database session
            
        Returns:
            Dictionary with reset results and affected counts
            
        Raises:
            AdminPermissionError: If admin lacks required permissions
            AdminValidationError: If player not found
            AdminOperationError: If operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Validate permissions - match history affects ratings
                if not await self._validate_admin_permissions(s, admin_discord_id, AdminPermissionType.MODIFY_RATINGS):
                    raise AdminPermissionError(f"Admin {admin_discord_id} lacks MODIFY_RATINGS permission")
                
                # Get player with row-level lock for consistency
                player_query = select(Player).where(Player.id == player_id)
                result = await s.execute(player_query)
                player = result.scalar_one_or_none()
                
                if not player:
                    raise AdminValidationError(f"Player with ID {player_id} not found")
                
                # Capture pre-reset statistics for audit
                old_stats = {
                    'matches_played': player.matches_played,
                    'wins': player.wins,
                    'losses': player.losses,
                    'draws': player.draws,
                    'current_streak': player.current_streak,
                    'max_streak': player.max_streak
                }
                
                # Delete all match history for this player
                history_delete = delete(EloHistory).where(EloHistory.player_id == player_id)
                history_result = await s.execute(history_delete)
                histories_deleted = history_result.rowcount or 0
                
                # Delete all event statistics for this player
                stats_delete = delete(PlayerEventStats).where(PlayerEventStats.player_id == player_id)
                stats_result = await s.execute(stats_delete)
                event_stats_deleted = stats_result.rowcount or 0
                
                # Reset player aggregate statistics
                player.matches_played = 0
                player.wins = 0
                player.losses = 0
                player.draws = 0
                player.current_streak = 0
                player.max_streak = 0
                
                # Create comprehensive audit log
                await self._create_audit_log(
                    s,
                    admin_discord_id,
                    "RESET_PLAYER_MATCH_HISTORY",
                    target_type="player",
                    target_id=player_id,
                    details={
                        'player_discord_id': player.discord_id,
                        'player_username': player.username,
                        'histories_deleted': histories_deleted,
                        'event_stats_deleted': event_stats_deleted,
                        'old_stats': old_stats,
                        'reason': reason
                    },
                    reason=reason,
                    affected_players_count=1,
                    affected_events_count=event_stats_deleted  # Number of events this player was in
                )
                
                self.logger.info(f"Match history reset completed for player {player_id} by admin {admin_discord_id}")
                
                # Commit if we own the session
                if not session:
                    await s.commit()
                
                return {
                    'success': True,
                    'player_id': player_id,
                    'player_discord_id': player.discord_id,
                    'player_username': player.username,
                    'histories_deleted': histories_deleted,
                    'event_stats_deleted': event_stats_deleted,
                    'old_stats': old_stats,
                    'reason': reason
                }
                
            except (AdminPermissionError, AdminValidationError):
                raise
            except Exception as e:
                self.logger.error(f"Match history reset failed for player {player_id}: {e}")
                raise AdminOperationError(f"Match history reset operation failed: {e}")
    
    async def reset_all_match_history(
        self,
        admin_discord_id: int,
        reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Reset ALL players' match history and statistics system-wide.
        
        This is a destructive operation that removes all match history,
        resets all event statistics, and zeroes all player aggregates.
        
        Args:
            admin_discord_id: Discord ID of admin performing reset
            reason: Admin-provided reason for reset
            session: Optional database session
            
        Returns:
            Dictionary with reset results and affected counts
            
        Raises:
            AdminPermissionError: If admin lacks required permissions
            AdminOperationError: If operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Validate permissions - mass reset requires highest level
                if not await self._validate_admin_permissions(s, admin_discord_id, AdminPermissionType.START_NEW_SEASON):
                    raise AdminPermissionError(f"Admin {admin_discord_id} lacks START_NEW_SEASON permission")
                
                # Get pre-reset counts for audit
                total_players_query = select(func.count(Player.id))
                total_players_result = await s.execute(total_players_query)
                total_players = total_players_result.scalar() or 0
                
                total_histories_query = select(func.count(EloHistory.id))
                total_histories_result = await s.execute(total_histories_query)
                total_histories = total_histories_result.scalar() or 0
                
                total_event_stats_query = select(func.count(PlayerEventStats.id))
                total_event_stats_result = await s.execute(total_event_stats_query)
                total_event_stats = total_event_stats_result.scalar() or 0
                
                # Bulk delete all match history (performance optimized)
                history_delete = delete(EloHistory)
                history_result = await s.execute(history_delete)
                histories_deleted = history_result.rowcount or 0
                
                # Bulk delete all player event statistics
                event_stats_delete = delete(PlayerEventStats)
                event_stats_result = await s.execute(event_stats_delete)
                event_stats_deleted = event_stats_result.rowcount or 0
                
                # Bulk reset all player aggregate statistics
                player_update = update(Player).values(
                    matches_played=0,
                    wins=0,
                    losses=0,
                    draws=0,
                    current_streak=0,
                    max_streak=0
                )
                player_result = await s.execute(player_update)
                players_updated = player_result.rowcount or 0
                
                # Create comprehensive audit log for mass operation
                await self._create_audit_log(
                    s,
                    admin_discord_id,
                    "RESET_ALL_MATCH_HISTORY",
                    target_type="system",
                    target_id=None,
                    details={
                        'total_players_before': total_players,
                        'total_histories_before': total_histories,
                        'total_event_stats_before': total_event_stats,
                        'histories_deleted': histories_deleted,
                        'event_stats_deleted': event_stats_deleted,
                        'players_updated': players_updated,
                        'reason': reason
                    },
                    reason=reason,
                    affected_players_count=players_updated,
                    affected_events_count=0  # No specific events affected, all events impacted
                )
                
                self.logger.info(f"Mass match history reset completed by admin {admin_discord_id}")
                
                # Commit if we own the session
                if not session:
                    await s.commit()
                
                return {
                    'success': True,
                    'histories_deleted': histories_deleted,
                    'event_stats_deleted': event_stats_deleted,
                    'players_updated': players_updated,
                    'total_players_before': total_players,
                    'total_histories_before': total_histories,
                    'total_event_stats_before': total_event_stats,
                    'reason': reason
                }
                
            except AdminPermissionError:
                raise
            except Exception as e:
                self.logger.error(f"Mass match history reset failed: {e}")
                raise AdminOperationError(f"Mass match history reset operation failed: {e}")