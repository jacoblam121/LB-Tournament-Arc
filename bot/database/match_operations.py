"""
Match Operations Module - Phase 2A2.4: N-Player Integration

This module provides the operational layer for Match and MatchParticipant CRUD operations,
implementing the bridge between existing Challenge workflows and new N-player Match system.

Based on expert-validated architecture with single source of truth principle:
- Match model is authoritative for all game results
- Challenge model continues handling invitation workflows  
- Bridge functions provide backward compatibility
- All operations are atomic and idempotent

Architecture Patterns:
- Pattern A: Challenge → Match bridge (1v1 compatibility)
- Pattern B: Direct Match creation (FFA/Team)
- Pattern C: Result recording with placement tracking
"""

import asyncio
import json
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from sqlalchemy import select, update, and_, or_, delete as sql_delete, func
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    Match, MatchParticipant, MatchStatus, MatchFormat,
    Challenge, ChallengeStatus, MatchResult,
    Player, Event, EloHistory,
    ConfirmationStatus, MatchResultProposal, MatchConfirmation,  # Phase B
    ChallengeRole, ChallengeParticipant  # Added for N-player support
)
from bot.utils.scoring_strategies import (
    ScoringStrategy, ParticipantResult, ScoringResult,
    Elo1v1Strategy, EloFfaStrategy, PerformancePointsStrategy
)
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


class MatchOperationError(Exception):
    """Base exception for match operation errors"""
    pass


class MatchValidationError(MatchOperationError):
    """Raised when match data validation fails"""
    pass


class MatchStateError(MatchOperationError):
    """Raised when match is in invalid state for operation"""
    pass


class MatchOperations:
    """
    Core service class for Match and MatchParticipant operations.
    
    Provides atomic, transactional operations for match lifecycle management
    with expert-validated patterns for data integrity and backward compatibility.
    """
    
    def __init__(self, database, config_service=None):
        """Initialize with database instance and optional config service"""
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
    
    # ============================================================================
    # Phase 2A2.4a: Bridge Challenge → Match Workflow Functions
    # ============================================================================
    
    async def create_match_from_challenge(self, challenge_id: int) -> Match:
        """
        Creates a Match from a completed Challenge (1v1 bridge pattern).
        
        This function implements Pattern A from expert analysis: backward compatible
        bridge that allows existing 1v1 Challenge workflow to optionally create
        Match records for unified result tracking.
        
        Features:
        - Idempotent: Returns existing Match if already created
        - Atomic: All operations in single transaction
        - Validation: Ensures Challenge is in correct state
        - Backward Compatible: Challenge result fields preserved
        
        Args:
            challenge_id: ID of the completed Challenge to bridge
            
        Returns:
            Match: The created or existing Match record
            
        Raises:
            MatchValidationError: If Challenge is not in valid state
            MatchOperationError: If database operation fails
        """
        async with self.db.get_session() as session:
            try:
                # Load Challenge with related data
                result = await session.execute(
                    select(Challenge)
                    .options(
                        selectinload(Challenge.challenger),
                        selectinload(Challenge.challenged),
                        selectinload(Challenge.event)
                    )
                    .where(Challenge.id == challenge_id)
                )
                challenge = result.scalar_one_or_none()
                
                if not challenge:
                    raise MatchValidationError(f"Challenge {challenge_id} not found")
                
                # Validation: Challenge must be completed
                if challenge.status != ChallengeStatus.COMPLETED:
                    raise MatchValidationError(
                        f"Challenge {challenge_id} is not completed (status: {challenge.status.value})"
                    )
                
                # Validation: Must have result data
                if not challenge.challenger_result or not challenge.challenged_result:
                    raise MatchValidationError(
                        f"Challenge {challenge_id} missing result data"
                    )
                
                # Idempotency check: Return existing Match if already created
                existing_match_result = await session.execute(
                    select(Match).where(Match.challenge_id == challenge_id)
                )
                existing_match = existing_match_result.scalar_one_or_none()
                if existing_match:
                    self.logger.info(f"Returning existing Match {existing_match.id} for Challenge {challenge_id}")
                    return existing_match
                
                # Create new Match record
                match = Match(
                    event_id=challenge.event_id,
                    match_format=MatchFormat.ONE_V_ONE,
                    status=MatchStatus.COMPLETED,  # Bridge from completed Challenge
                    challenge_id=challenge_id,
                    started_at=challenge.accepted_at,
                    completed_at=challenge.completed_at,
                    created_by=challenge.challenger_id,
                    discord_channel_id=challenge.discord_channel_id,
                    discord_message_id=challenge.discord_message_id,
                    admin_notes=f"Bridged from Challenge {challenge_id}"
                )
                
                session.add(match)
                await session.flush()  # Get Match ID for MatchParticipant creation
                
                # Create MatchParticipant records with correct placements
                challenger_placement = 1 if challenge.challenger_result == MatchResult.WIN else 2
                challenged_placement = 1 if challenge.challenged_result == MatchResult.WIN else 2
                
                # Handle draws (both get placement 1)
                if challenge.challenger_result == MatchResult.DRAW:
                    challenger_placement = challenged_placement = 1
                
                challenger_participant = MatchParticipant(
                    match_id=match.id,
                    player_id=challenge.challenger_id,
                    placement=challenger_placement,
                    elo_change=challenge.challenger_elo_change,
                    elo_before=challenge.challenger.elo_rating - challenge.challenger_elo_change,
                    elo_after=challenge.challenger.elo_rating
                )
                
                challenged_participant = MatchParticipant(
                    match_id=match.id,
                    player_id=challenge.challenged_id,
                    placement=challenged_placement,
                    elo_change=challenge.challenged_elo_change,
                    elo_before=challenge.challenged.elo_rating - challenge.challenged_elo_change,
                    elo_after=challenge.challenged.elo_rating
                )
                
                session.add(challenger_participant)
                session.add(challenged_participant)
                
                await session.commit()
                
                # Reload match with relationships for return
                result = await session.execute(
                    select(Match)
                    .options(
                        selectinload(Match.participants),
                        selectinload(Match.event).selectinload(Event.cluster)
                    )
                    .where(Match.id == match.id)
                )
                match = result.scalar_one()
                
                self.logger.info(
                    f"Successfully created Match {match.id} from Challenge {challenge_id} "
                    f"(Challenger: {challenger_placement}, Challenged: {challenged_placement})"
                )
                
                return match
                
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to create Match from Challenge {challenge_id}: {e}")
                if isinstance(e, MatchOperationError):
                    raise
                raise MatchOperationError(f"Database error creating Match from Challenge: {e}")
    
    async def get_or_create_match_from_challenge(self, challenge_id: int) -> Match:
        """
        Idempotent version of create_match_from_challenge.
        
        This is the recommended function for most use cases as it handles
        both creation and retrieval scenarios safely.
        
        Args:
            challenge_id: ID of the Challenge to bridge
            
        Returns:
            Match: The Match record (created or existing)
        """
        return await self.create_match_from_challenge(challenge_id)
    
    async def get_match_by_challenge(self, challenge_id: int) -> Optional[Match]:
        """
        Retrieve Match created from a specific Challenge.
        
        Args:
            challenge_id: Challenge ID to lookup
            
        Returns:
            Match if exists, None otherwise
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(Match)
                .options(selectinload(Match.participants))
                .where(Match.challenge_id == challenge_id)
            )
            return result.scalar_one_or_none()
    
    # ============================================================================
    # Phase 2A2.4b: Direct FFA Match Creation System  
    # ============================================================================
    
    async def create_ffa_match(
        self,
        event_id: int,
        participant_ids: List[int],
        created_by_id: Optional[int] = None,
        admin_notes: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> Match:
        """
        Creates a direct FFA Match without Challenge workflow (Pattern B).
        
        This implements the new capability for N-player matches that bypass
        the traditional Challenge invitation system entirely.
        
        Features:
        - Validates event supports FFA format
        - Validates participant count within event limits
        - Creates Match with all participants in PENDING status
        - Ready for result recording via complete_match_with_results()
        
        Args:
            event_id: Event this match belongs to
            participant_ids: List of Player IDs participating
            created_by_id: Optional Player ID who created the match
            admin_notes: Optional admin notes
            
        Returns:
            Match: The created Match record with participants
            
        Raises:
            MatchValidationError: If validation fails
            MatchOperationError: If database operation fails
        """
        async with self._get_session_context(session) as s:
            try:
                # Validate event exists and supports FFA
                result = await s.execute(
                    select(Event).where(Event.id == event_id)
                )
                event = result.scalar_one_or_none()
                
                if not event:
                    raise MatchValidationError(f"Event {event_id} not found")
                
                if event.scoring_type not in ['FFA', 'Team']:
                    raise MatchValidationError(
                        f"Event {event_id} does not support FFA matches (scoring_type: {event.scoring_type})"
                    )
                
                # Validate all participants exist and are unique (before count validation)
                if len(set(participant_ids)) != len(participant_ids):
                    raise MatchValidationError("Duplicate participants not allowed")
                
                player_result = await s.execute(
                    select(Player.id).where(Player.id.in_(participant_ids))
                )
                existing_player_ids = {row.id for row in player_result}
                missing_players = set(participant_ids) - existing_player_ids
                
                if missing_players:
                    raise MatchValidationError(f"Players not found: {missing_players}")
                
                # Validate participant count (after ensuring valid unique players)
                participant_count = len(set(participant_ids))  # Use deduplicated count
                if participant_count < event.min_players:
                    raise MatchValidationError(
                        f"Not enough participants: {participant_count} < {event.min_players}"
                    )
                if participant_count > event.max_players:
                    raise MatchValidationError(
                        f"Too many participants: {participant_count} > {event.max_players}"
                    )
                
                # Create Match record
                match_format = MatchFormat.FFA if event.scoring_type == 'FFA' else MatchFormat.TEAM
                match = Match(
                    event_id=event_id,
                    match_format=match_format,
                    status=MatchStatus.PENDING,
                    challenge_id=None,  # Direct creation, no Challenge
                    started_at=None,    # Will be set when match starts
                    completed_at=None,  # Will be set when results recorded
                    created_by=created_by_id,
                    admin_notes=admin_notes or f"Direct {match_format.value} match creation"
                )
                
                s.add(match)
                await s.flush()  # Get Match ID
                
                # Create MatchParticipant records (no placements yet)
                participants = []
                for player_id in participant_ids:
                    participant = MatchParticipant(
                        match_id=match.id,
                        player_id=player_id,
                        placement=None,  # Will be set when results recorded
                        elo_change=0,    # Will be calculated when results recorded
                        elo_before=None, # Will be set when results recorded
                        elo_after=None   # Will be set when results recorded
                    )
                    participants.append(participant)
                    s.add(participant)
                
                if not session:  # Only commit if we manage the session
                    await s.commit()
                    
                    # Reload match with relationships for return
                    result = await s.execute(
                        select(Match)
                        .options(selectinload(Match.participants))
                        .where(Match.id == match.id)
                    )
                    match = result.scalar_one()
                else:
                    await s.flush()  # Ensure all data is flushed
                    # Still need to reload to get relationships
                    result = await s.execute(
                        select(Match)
                        .options(selectinload(Match.participants))
                        .where(Match.id == match.id)
                    )
                    match = result.scalar_one()
                
                self.logger.info(
                    f"Successfully created {match_format.value} Match {match.id} "
                    f"for Event {event_id} with {participant_count} participants"
                )
                
                return match
                
            except Exception as e:
                if not session:  # Only rollback if we manage the session
                    await s.rollback()
                self.logger.error(f"Failed to create FFA match: {e}")
                if isinstance(e, MatchOperationError):
                    raise
                raise MatchOperationError(f"Database error creating FFA match: {e}")
    
    async def create_team_match(
        self,
        event_id: int,
        teams: Dict[str, List[int]],  # team_id -> player_ids
        created_by_id: Optional[int] = None,
        admin_notes: Optional[str] = None
    ) -> Match:
        """
        Creates a team-based Match (Pattern C variation).
        
        Args:
            event_id: Event this match belongs to
            teams: Dictionary mapping team_id to list of player_ids
                  e.g., {"A": [1, 2], "B": [3, 4]}
            created_by_id: Optional Player ID who created the match
            admin_notes: Optional admin notes
            
        Returns:
            Match: The created Match record with team participants
        """
        # Flatten teams into participant list with team assignments
        all_participant_ids = []
        team_assignments = {}  # player_id -> team_id
        
        for team_id, player_ids in teams.items():
            all_participant_ids.extend(player_ids)
            for player_id in player_ids:
                team_assignments[player_id] = team_id
        
        # Create base FFA match first
        match = await self.create_ffa_match(
            event_id=event_id,
            participant_ids=all_participant_ids,
            created_by_id=created_by_id,
            admin_notes=admin_notes
        )
        
        # Update Match format and add team assignments
        async with self.db.get_session() as session:
            # Update match format
            await session.execute(
                update(Match)
                .where(Match.id == match.id)
                .values(match_format=MatchFormat.TEAM)
            )
            
            # Update participants with team assignments
            for player_id, team_id in team_assignments.items():
                await session.execute(
                    update(MatchParticipant)
                    .where(
                        and_(
                            MatchParticipant.match_id == match.id,
                            MatchParticipant.player_id == player_id
                        )
                    )
                    .values(team_id=team_id)
                )
            
            await session.commit()
            
            # Reload match with relationships for return
            result = await session.execute(
                select(Match)
                .options(selectinload(Match.participants))
                .where(Match.id == match.id)
            )
            match = result.scalar_one()
        
        self.logger.info(
            f"Successfully created Team Match {match.id} with teams: {teams}"
        )
        
        return match
    
    # ============================================================================
    # Utility Functions
    # ============================================================================
    
    async def get_match_by_id(self, match_id: int) -> Optional[Match]:
        """
        Retrieve Match by ID with participants loaded.
        
        Args:
            match_id: Match ID to retrieve
            
        Returns:
            Match with participants if exists, None otherwise
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(Match)
                .options(
                    selectinload(Match.participants),
                    selectinload(Match.event),
                    selectinload(Match.challenge)
                )
                .where(Match.id == match_id)
            )
            return result.scalar_one_or_none()
    
    async def get_match_with_participants(self, match_id: int) -> Optional[Match]:
        """
        Alias for get_match_by_id with participants loaded (for modal functionality).
        
        Args:
            match_id: Match ID to retrieve
            
        Returns:
            Match with participants and player relationships loaded if exists, None otherwise
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(Match)
                .options(
                    selectinload(Match.participants).selectinload(MatchParticipant.player),
                    selectinload(Match.event),
                    selectinload(Match.challenge)
                )
                .where(Match.id == match_id)
            )
            return result.scalar_one_or_none()
    
    async def get_pending_matches(self, limit: int = 50) -> List[Match]:
        """
        Get all pending matches that need results.
        
        Args:
            limit: Maximum number of matches to return
            
        Returns:
            List of pending Match records
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(Match)
                .options(selectinload(Match.participants))
                .where(Match.status == MatchStatus.PENDING)
                .order_by(Match.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
    
    async def get_active_matches_for_player(
        self, 
        player_discord_id: int, 
        limit: Optional[int] = None
    ) -> List[Match]:
        """
        Get all active matches for a player (Phase 2.4.4).
        
        Active matches include:
        - PENDING: Match created, waiting to start
        - ACTIVE: Match in progress  
        - AWAITING_CONFIRMATION: Results submitted, awaiting confirmation
        
        Performance optimized with:
        - Composite database indexes (player_id, match_id) and (status, id)
        - Eager loading to prevent N+1 queries
        - Optional limit for Discord embed field constraints
        
        Args:
            player_discord_id: Discord ID of the player
            limit: Maximum number of matches to return (recommended: 25 for Discord embeds)
            
        Returns:
            List of active Match records ordered by most recent first
        """
        # Define active statuses
        ACTIVE_STATUSES = [
            MatchStatus.PENDING,
            MatchStatus.ACTIVE, 
            MatchStatus.AWAITING_CONFIRMATION
        ]
        
        async with self.db.get_session() as session:
            # First get the player to ensure they exist
            player_stmt = select(Player).where(Player.discord_id == player_discord_id)
            player_result = await session.execute(player_stmt)
            player = player_result.scalar_one_or_none()
            
            if not player:
                # Return empty list if player not found (graceful handling)
                return []
            
            # Build optimized query with expert-recommended eager loading
            query = (
                select(Match)
                .join(Match.participants)  # Join to MatchParticipant
                .where(
                    and_(
                        MatchParticipant.player_id == player.id,
                        Match.status.in_(ACTIVE_STATUSES)
                    )
                )
                .options(
                    # Use joinedload for one-to-one relationships (performance optimized)
                    joinedload(Match.event).joinedload(Event.cluster),
                    # Use selectinload for one-to-many relationships (avoids cartesian product)
                    selectinload(Match.participants).selectinload(MatchParticipant.player)
                )
                .order_by(Match.started_at.desc().nulls_last(), Match.created_at.desc())
                .distinct()  # Ensure no duplicate matches from JOIN
            )
            
            # Apply limit if specified (important for Discord embed constraints)
            if limit is not None:
                query = query.limit(limit)
            
            result = await session.execute(query)
            matches = list(result.scalars().unique().all())
            
            self.logger.info(
                f"Retrieved {len(matches)} active matches for player {player_discord_id} "
                f"(limit: {limit or 'none'})"
            )
            
            return matches
    
    async def validate_match_for_results(self, match: Match) -> bool:
        """
        Validate that a Match is ready for result recording.
        
        Args:
            match: Match to validate
            
        Returns:
            True if match is valid for results
            
        Raises:
            MatchValidationError: If match is not valid
        """
        if match.status == MatchStatus.COMPLETED:
            raise MatchValidationError(f"Match {match.id} is already completed")
        
        if match.status == MatchStatus.CANCELLED:
            raise MatchValidationError(f"Match {match.id} is cancelled")
        
        if not match.participants:
            raise MatchValidationError(f"Match {match.id} has no participants")
        
        return True
    
    # ============================================================================
    # Phase 2A2.4c: Result Recording with Placement Tracking
    # ============================================================================
    
    async def complete_match_with_results(
        self,
        match_id: int,
        results: List[Dict[str, Union[int, str]]],  # [{"player_id": int, "placement": int}, ...]
        recorded_by_id: Optional[int] = None
    ) -> Match:
        """
        Records results for a Match and calculates rating changes (Pattern C).
        
        This is the authoritative function for all match result recording,
        implementing the expert-validated single source of truth pattern.
        
        Features:
        - Atomic: All operations in single transaction with rollback
        - Validation: Comprehensive result data validation
        - Scoring Integration: Uses scoring strategies for rating calculations
        - EloHistory Creation: Creates proper history records
        - Challenge Sync: Updates legacy Challenge fields for compatibility
        
        Args:
            match_id: ID of the Match to complete
            results: List of result dictionaries with keys:
                    - player_id (int): Player ID
                    - placement (int): Final placement (1=1st, 2=2nd, etc.)
                    - Optional: team_id (str) for team matches
            recorded_by_id: Optional Player ID who recorded results
            
        Returns:
            Match: The completed Match with updated participants
            
        Raises:
            MatchValidationError: If validation fails
            MatchOperationError: If database operation fails
        """
        async with self.db.get_session() as session:
            try:
                # Load Match with full context
                result = await session.execute(
                    select(Match)
                    .options(
                        selectinload(Match.participants).selectinload(MatchParticipant.player),
                        selectinload(Match.event),
                        selectinload(Match.challenge)
                    )
                    .where(Match.id == match_id)
                )
                match = result.scalar_one_or_none()
                
                if not match:
                    raise MatchValidationError(f"Match {match_id} not found")
                
                # Validate match state
                await self.validate_match_for_results(match)
                
                # Validate results data
                await self._validate_results_data(match, results)
                
                # Prepare participant data for scoring calculation
                participant_results = []
                results_by_player = {r["player_id"]: r for r in results}
                
                # Phase 1.2: Get event-specific stats for each participant
                event_id = match.event_id
                
                # Validate all participants have results before bulk fetching
                for participant in match.participants:
                    if participant.player_id not in results_by_player:
                        raise MatchValidationError(
                            f"Missing result for participant {participant.player_id}"
                        )
                
                # Bulk fetch/create PlayerEventStats to avoid N+1 query
                player_ids = [p.player_id for p in match.participants]
                player_event_stats = await self.db.bulk_get_or_create_player_event_stats(
                    player_ids, event_id, session
                )
                
                # Calculate cluster ELO "before" values for all participants
                from bot.operations.elo_hierarchy import EloHierarchyCalculator
                cluster_elo_calculator = EloHierarchyCalculator(session)
                cluster_elos_before = {}
                cluster_id = match.event.cluster_id
                
                for participant in match.participants:
                    try:
                        cluster_elos = await cluster_elo_calculator.calculate_cluster_elo(
                            participant.player_id, cluster_id
                        )
                        cluster_elos_before[participant.player_id] = cluster_elos.get(cluster_id, 1000)
                    except Exception as e:
                        self.logger.warning(f"Failed to calculate cluster ELO before for player {participant.player_id}: {e}")
                        cluster_elos_before[participant.player_id] = 1000
                
                # Build participant results using bulk-fetched stats
                for participant in match.participants:
                    result_data = results_by_player[participant.player_id]
                    event_stats = player_event_stats[participant.player_id]
                    
                    # Use event-specific elo and matches for calculations
                    participant_result = ParticipantResult(
                        player_id=participant.player_id,
                        current_elo=event_stats.raw_elo,  # Use event elo instead of global
                        matches_played=event_stats.matches_played,  # Use event matches
                        placement=result_data["placement"],
                        team_id=result_data.get("team_id"),
                        event_id=event_id  # Pass event context
                    )
                    participant_results.append(participant_result)
                
                # Calculate rating changes using appropriate scoring strategy
                scoring_strategy = await self._get_scoring_strategy(match.match_format)
                scoring_results = scoring_strategy.calculate_results(participant_results)
                
                # Update match status and timing
                now = datetime.now(timezone.utc)
                match.status = MatchStatus.COMPLETED
                match.completed_at = now
                if not match.started_at:
                    match.started_at = now  # Auto-set if not already set
                
                # Update MatchParticipant records with results and rating changes
                elo_history_records = []
                
                for participant in match.participants:
                    result_data = results_by_player[participant.player_id]
                    scoring_result = scoring_results[participant.player_id]
                    event_stats = player_event_stats[participant.player_id]
                    
                    # Update participant with results
                    participant.placement = result_data["placement"]
                    
                    # Phase 1.2: Use event-specific elo for before/after tracking
                    participant.elo_before = event_stats.raw_elo
                    participant.elo_change = scoring_result.elo_change
                    participant.pp_change = scoring_result.pp_change
                    participant.points_earned = scoring_result.points_earned
                    participant.elo_after = participant.elo_before + scoring_result.elo_change
                    
                    # Set team assignment if provided
                    if "team_id" in result_data:
                        participant.team_id = result_data["team_id"]
                    
                    # Phase 1.2: Update event-specific elo
                    await self.db.update_event_elo(
                        player_id=participant.player_id,
                        event_id=event_id,
                        new_raw_elo=participant.elo_after,
                        match_result=self._determine_match_result(participant.placement, len(match.participants)),
                        match_id=match.id,
                        session=session
                    )
                    
                    # Update event-specific matches played
                    event_stats.matches_played += 1
                    
                    # Update event-specific win/loss/draw stats
                    match_result = self._determine_match_result(participant.placement, len(match.participants))
                    if match_result == MatchResult.WIN:
                        event_stats.wins += 1
                    elif match_result == MatchResult.LOSS:
                        event_stats.losses += 1
                    elif match_result == MatchResult.DRAW:
                        event_stats.draws += 1
                    
                    # Store cluster ELO "before" value in participant
                    participant.cluster_id = cluster_id
                    participant.cluster_elo_before = cluster_elos_before.get(participant.player_id, 1000)
                    
                    # Phase 1.2: Keep global elo in sync for backward compatibility
                    participant.player.elo_rating = participant.elo_after
                    participant.player.matches_played += 1
                    
                    # Update win/loss/draw stats (global only for now)
                    if match.match_format == MatchFormat.ONE_V_ONE:
                        if participant.placement == 1:
                            participant.player.wins += 1
                        elif participant.placement == 2:
                            participant.player.losses += 1
                        # Note: Draws handled when both players have placement=1
                    
                    # Create EloHistory record - now includes event_id
                    elo_history = EloHistory(
                        player_id=participant.player_id,
                        event_id=event_id,  # Phase 1.2: Add event context
                        old_elo=participant.elo_before,
                        new_elo=participant.elo_after,
                        elo_change=scoring_result.elo_change,
                        challenge_id=None,  # Match-based, not Challenge-based
                        match_id=match.id,
                        opponent_id=None,   # For multi-player, no single opponent
                        match_result=self._determine_match_result(participant.placement, len(match.participants)),
                        k_factor=event_stats.k_factor,  # Use event-specific k_factor
                        recorded_at=now
                    )
                    elo_history_records.append(elo_history)
                    session.add(elo_history)
                
                # Sync to Challenge for backward compatibility (if bridged from Challenge)
                if match.challenge_id:
                    await self._sync_results_to_challenge(session, match)
                
                # Flush session to ensure event ELO updates are visible for cluster calculations
                await session.flush()
                
                # Calculate cluster ELO "after" values and store in participants
                for participant in match.participants:
                    try:
                        cluster_elos_after = await cluster_elo_calculator.calculate_cluster_elo(
                            participant.player_id, cluster_id
                        )
                        participant.cluster_elo_after = cluster_elos_after.get(cluster_id, 1000)
                        participant.cluster_elo_change = participant.cluster_elo_after - participant.cluster_elo_before
                    except Exception as e:
                        self.logger.warning(f"Failed to calculate cluster ELO after for player {participant.player_id}: {e}")
                        participant.cluster_elo_after = participant.cluster_elo_before
                        participant.cluster_elo_change = 0
                
                # Phase 2.3 Fix: Sync overall player stats after match completion
                try:
                    # Import at method level to avoid circular dependencies
                    from bot.services.player_stats_sync import PlayerStatsSyncService
                    sync_service = PlayerStatsSyncService()
                    participant_ids = [p.player_id for p in match.participants]
                    await sync_service.sync_match_participants(session, participant_ids)
                except Exception as sync_error:
                    # Log error but don't fail the match completion
                    self.logger.error(f"Failed to sync player stats for match {match_id}: {sync_error}")
                    # Stats sync failure is non-critical - match results are already saved
                
                # Single commit for both match results and synced stats
                await session.commit()
                
                # Reload match with relationships for return
                result = await session.execute(
                    select(Match)
                    .options(
                        selectinload(Match.participants),
                        selectinload(Match.event).selectinload(Event.cluster)
                    )
                    .where(Match.id == match.id)
                )
                match = result.scalar_one()
                
                self.logger.info(
                    f"Successfully completed Match {match_id} with {len(results)} participants. "
                    f"Event ELO changes: {[(r['player_id'], scoring_results[r['player_id']].elo_change) for r in results]}. "
                    f"Cluster ELO changes: {[(p.player_id, p.cluster_elo_change) for p in match.participants]}"
                )
                
                return match
                
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to complete Match {match_id}: {e}")
                if isinstance(e, MatchOperationError):
                    raise
                raise MatchOperationError(f"Database error completing Match: {e}")
    
    async def _validate_results_data(self, match: Match, results: List[Dict]) -> None:
        """Validate that results data is consistent and complete"""
        # First validate that all result dicts have required keys
        for i, result in enumerate(results):
            if "player_id" not in result:
                raise MatchValidationError(f"Missing 'player_id' key in result at index {i}")
            if "placement" not in result:
                raise MatchValidationError(f"Missing 'placement' key in result at index {i}")
        
        participant_ids = {p.player_id for p in match.participants}
        result_player_ids = {r["player_id"] for r in results}
        
        # Check all participants have results
        missing_results = participant_ids - result_player_ids
        if missing_results:
            raise MatchValidationError(f"Missing results for players: {missing_results}")
        
        # Check no extra results
        extra_results = result_player_ids - participant_ids
        if extra_results:
            raise MatchValidationError(f"Results for non-participants: {extra_results}")
        
        # Validate placement values
        placements = [r["placement"] for r in results]
        if not all(isinstance(p, int) and p > 0 for p in placements):
            raise MatchValidationError("All placements must be positive integers")
        
        # Check placement range
        max_placement = max(placements)
        if max_placement > len(results):
            raise MatchValidationError(f"Invalid placement {max_placement} for {len(results)} participants")
        
        # Phase 2.5: Draw Policy Enforcement - Explicitly reject draws in 1v1 matches
        if match.match_format == MatchFormat.ONE_V_ONE and len(results) == 2:
            # Check if both players have placement=1 (draw situation)
            if placements.count(1) == 2:
                raise MatchValidationError("Draws are explicitly not handled. Please cancel this match and replay.")
        
        # Validate placement sequence (must start from 1, allow ties)
        # Examples: [1,2,3] valid, [1,1,3] valid (tie for 1st), [2,3,4] invalid (must start at 1)
        unique_placements = sorted(set(placements))
        if unique_placements[0] != 1:
            raise MatchValidationError("Placements must start from 1")
        
        # Check that all used placement values are within valid range
        # For tied placements, the next placement can skip numbers
        # Example: [1,1,3,4] is valid - two tied for 1st, so 3rd place is next
        placement_counts = {}
        for p in placements:
            placement_counts[p] = placement_counts.get(p, 0) + 1
        
        # Validate that placement numbers don't exceed logical maximum
        # e.g., if two players tie for 1st, the next placement should be 3rd, not 2nd
        current_position = 1
        for placement in sorted(placement_counts.keys()):
            if placement < current_position:
                raise MatchValidationError(f"Invalid placement sequence: placement {placement} used after position {current_position}")
            current_position += placement_counts[placement]
    
    async def _get_scoring_strategy(self, match_format: MatchFormat) -> ScoringStrategy:
        """Get appropriate scoring strategy based on match format"""
        # Map MatchFormat enum to scoring strategy
        if match_format == MatchFormat.ONE_V_ONE:
            return Elo1v1Strategy(self.config_service)
        elif match_format == MatchFormat.FFA:
            return EloFfaStrategy(self.config_service)
        elif match_format == MatchFormat.TEAM:
            return EloFfaStrategy(self.config_service)  # Team matches use FFA algorithm for now
        elif match_format == MatchFormat.LEADERBOARD:
            return PerformancePointsStrategy()
        else:
            raise MatchValidationError(f"Unknown match format: {match_format}")
    
    def _determine_match_result(self, placement: int, total_participants: int) -> MatchResult:
        """Determine MatchResult enum value based on placement"""
        if placement == 1:
            return MatchResult.WIN
        elif total_participants == 2 and placement == 2:
            return MatchResult.LOSS
        else:
            # For FFA, 2nd place and below are considered losses
            # Draw is only used for explicit ties in 1v1
            return MatchResult.LOSS
    
    async def _sync_results_to_challenge(self, session, match: Match) -> None:
        """
        Sync Match results back to originating Challenge for backward compatibility.
        
        This implements the expert recommendation for maintaining Challenge
        result fields while using Match as the authoritative source.
        """
        if not match.challenge_id or match.match_format != MatchFormat.ONE_V_ONE:
            return  # Only sync 1v1 matches from Challenges
        
        # Get Challenge with participants eagerly loaded, using row lock for safety
        result = await session.execute(
            select(Challenge)
            .options(selectinload(Challenge.participants))
            .where(Challenge.id == match.challenge_id)
            .with_for_update()
        )
        challenge = result.scalar_one_or_none()
        
        if not challenge:
            self.logger.warning(f"Challenge {match.challenge_id} not found for Match {match.id}")
            return
        
        # Build role lookup for efficiency, handling potential NULL roles from migration
        participants_by_role = {}
        for p in challenge.participants:
            if p.role is not None:  # Explicit null check for migration compatibility
                participants_by_role[p.role] = p
        
        challenger_participant = participants_by_role.get(ChallengeRole.CHALLENGER)
        challenged_participant = participants_by_role.get(ChallengeRole.CHALLENGED)
        
        if not challenger_participant or not challenged_participant:
            self.logger.warning(
                f"Missing required participants for Challenge {challenge.id}. "
                f"Found roles: {list(participants_by_role.keys())}"
            )
            return
        
        challenger_id = challenger_participant.player_id
        challenged_id = challenged_participant.player_id
        
        # Get match participants sorted by placement
        match_participants = sorted(match.participants, key=lambda p: p.placement)
        
        if len(match_participants) == 2:
            winner_participant = match_participants[0]  # placement = 1
            loser_participant = match_participants[1]   # placement = 2 (or 1 for tie)
            
            # Handle draws (both have same placement)
            if winner_participant.placement == loser_participant.placement:
                challenge.challenger_result = MatchResult.DRAW
                challenge.challenged_result = MatchResult.DRAW
            else:
                # Determine which participant is challenger vs challenged
                if winner_participant.player_id == challenger_id:
                    challenge.challenger_result = MatchResult.WIN
                    challenge.challenged_result = MatchResult.LOSS
                else:
                    challenge.challenger_result = MatchResult.LOSS
                    challenge.challenged_result = MatchResult.WIN
            
            # Update Elo changes - find by player_id
            challenger_match_participant = next(
                (p for p in match_participants if p.player_id == challenger_id),
                None
            )
            challenged_match_participant = next(
                (p for p in match_participants if p.player_id == challenged_id),
                None
            )
            
            if challenger_match_participant and challenged_match_participant:
                challenge.challenger_elo_change = challenger_match_participant.elo_change
                challenge.challenged_elo_change = challenged_match_participant.elo_change
            else:
                self.logger.warning(
                    f"Could not find match participants for Challenge {challenge.id} sync"
                )
        
        self.logger.info(f"Synced Match {match.id} results to Challenge {challenge.id}")
    
    # ============================================================================
    # Administrative Functions
    # ============================================================================
    
    async def cancel_match(self, match_id: int, reason: str = None) -> Match:
        """
        Cancel a pending or active match.
        
        Args:
            match_id: Match to cancel
            reason: Optional cancellation reason
            
        Returns:
            Cancelled Match
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(Match).where(Match.id == match_id)
            )
            match = result.scalar_one_or_none()
            
            if not match:
                raise MatchValidationError(f"Match {match_id} not found")
            
            if match.status == MatchStatus.COMPLETED:
                raise MatchStateError(f"Cannot cancel completed Match {match_id}")
            
            match.status = MatchStatus.CANCELLED
            if reason:
                match.admin_notes = f"{match.admin_notes or ''}\nCancelled: {reason}".strip()
            
            await session.commit()
            
            self.logger.info(f"Cancelled Match {match_id}: {reason}")
            return match
    
    def _validate_results_json(self, results: List[Dict[str, Union[int, str]]]) -> None:
        """
        Validate results data structure before JSON serialization.
        
        Ensures data is JSON-serializable and has correct structure.
        
        Args:
            results: List of result dictionaries
            
        Raises:
            MatchValidationError: If data structure is invalid
        """
        if not isinstance(results, list):
            raise MatchValidationError("Results must be a list")
        
        if not results:
            raise MatchValidationError("Results list cannot be empty")
        
        for i, result in enumerate(results):
            if not isinstance(result, dict):
                raise MatchValidationError(f"Result at index {i} must be a dictionary")
            
            # Check required keys
            if "player_id" not in result:
                raise MatchValidationError(f"Missing 'player_id' in result at index {i}")
            if "placement" not in result:
                raise MatchValidationError(f"Missing 'placement' in result at index {i}")
            
            # Check data types
            if not isinstance(result["player_id"], int):
                raise MatchValidationError(f"player_id must be an integer at index {i}")
            if not isinstance(result["placement"], int):
                raise MatchValidationError(f"placement must be an integer at index {i}")
            
            # Check value ranges
            if result["player_id"] <= 0:
                raise MatchValidationError(f"player_id must be positive at index {i}")
            if result["placement"] <= 0:
                raise MatchValidationError(f"placement must be positive at index {i}")
    
    # ============================================================================
    # Phase B: Confirmation System Operations
    # ============================================================================
    
    async def create_result_proposal(
        self,
        match_id: int,
        proposer_id: int,
        results: List[Dict[str, Union[int, str]]],
        expires_in_hours: int = 24,
        discord_channel_id: Optional[int] = None,
        discord_message_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> MatchResultProposal:
        """
        Create a proposal for match results requiring confirmation.
        
        Args:
            match_id: Match these results belong to
            proposer_id: Player ID proposing the results
            results: List of dicts with player_id and placement
            expires_in_hours: Hours until proposal expires (default 24)
            discord_channel_id: Channel where proposal was made
            discord_message_id: Message ID of the proposal
            session: Optional session for transaction participation
            
        Returns:
            Created MatchResultProposal
            
        Raises:
            MatchValidationError: If match not found or in wrong state
            MatchOperationError: If proposal already exists
        """
        async with self._get_session_context(session) as sess:
            # Load match with participants
            result = await sess.execute(
                select(Match)
                .options(selectinload(Match.participants).selectinload(MatchParticipant.player))
                .where(Match.id == match_id)
            )
            match = result.scalar_one_or_none()
            
            if not match:
                raise MatchValidationError(f"Match {match_id} not found")
            
            if match.status != MatchStatus.PENDING:
                raise MatchStateError(f"Match {match_id} is not in PENDING status")
            
            # Check if proposal already exists
            existing = await sess.execute(
                select(MatchResultProposal)
                .where(MatchResultProposal.match_id == match_id)
                .where(MatchResultProposal.is_active == True)
            )
            if existing.scalar_one_or_none():
                raise MatchOperationError(f"Active proposal already exists for Match {match_id}")
            
            # Validate proposer is a participant
            participant_ids = [p.player_id for p in match.participants]
            if proposer_id not in participant_ids:
                raise MatchValidationError(f"Proposer {proposer_id} is not a participant in Match {match_id}")
            
            # Validate results data before storing
            self._validate_results_json(results)
            await self._validate_results_data(match, results)
            
            # Create proposal
            expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_in_hours)
            proposal = MatchResultProposal(
                match_id=match_id,
                proposer_id=proposer_id,
                proposed_results=json.dumps(results),
                expires_at=expires_at,
                discord_channel_id=discord_channel_id,
                discord_message_id=discord_message_id
            )
            sess.add(proposal)
            
            # Create confirmation records for all participants
            for participant in match.participants:
                confirmation = MatchConfirmation(
                    match_id=match_id,
                    player_id=participant.player_id,
                    status=ConfirmationStatus.PENDING
                )
                # Auto-confirm for proposer
                if participant.player_id == proposer_id:
                    confirmation.status = ConfirmationStatus.CONFIRMED
                    confirmation.responded_at = datetime.now(timezone.utc)
                sess.add(confirmation)
            
            # Update match status
            match.status = MatchStatus.AWAITING_CONFIRMATION
            
            await sess.commit()
            
            # Re-fetch the proposal with all relationships loaded to prevent session detachment issues
            # This uses the same eager loading strategy as get_proposal_by_id()
            result = await sess.execute(
                select(MatchResultProposal)
                .options(
                    selectinload(MatchResultProposal.match).options(
                        selectinload(Match.participants).selectinload(MatchParticipant.player),
                        selectinload(Match.event).selectinload(Event.cluster)
                    ),
                    selectinload(MatchResultProposal.proposer)
                )
                .where(MatchResultProposal.id == proposal.id)
            )
            proposal = result.scalar_one()
            
            self.logger.info(f"Created result proposal for Match {match_id} by Player {proposer_id}")
            return proposal
    
    async def get_pending_proposal(self, match_id: int) -> Optional[MatchResultProposal]:
        """
        Get active proposal for a match if exists.
        
        Args:
            match_id: Match to check
            
        Returns:
            Active MatchResultProposal or None
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(MatchResultProposal)
                .options(
                    selectinload(MatchResultProposal.match)
                    .selectinload(Match.event)
                    .selectinload(Event.cluster),
                    selectinload(MatchResultProposal.proposer)
                )
                .where(MatchResultProposal.match_id == match_id)
                .where(MatchResultProposal.is_active == True)
            )
            return result.scalar_one_or_none()
    
    async def get_proposal_by_id(self, proposal_id: int) -> Optional[MatchResultProposal]:
        """
        Get proposal by ID with all relationships loaded.
        
        Fetches an active, non-expired proposal with eagerly loaded
        match, participants, and player relationships to prevent N+1 queries.
        
        Args:
            proposal_id: ID of the proposal to fetch
            
        Returns:
            Active MatchResultProposal or None if not found/expired
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(MatchResultProposal)
                .options(
                    selectinload(MatchResultProposal.match).options(
                        selectinload(Match.participants).selectinload(MatchParticipant.player),
                        selectinload(Match.event).selectinload(Event.cluster)
                    ),
                    selectinload(MatchResultProposal.proposer)
                )
                .where(
                    MatchResultProposal.id == proposal_id,
                    MatchResultProposal.is_active == True,
                    MatchResultProposal.expires_at > func.now()
                )
            )
            return result.scalar_one_or_none()
    
    async def record_confirmation(
        self,
        match_id: int,
        player_id: int,
        status: ConfirmationStatus,
        reason: Optional[str] = None,
        discord_user_id: Optional[int] = None,
        discord_message_id: Optional[int] = None
    ) -> MatchConfirmation:
        """
        Record a player's confirmation/rejection of proposed results.
        
        Uses atomic UPDATE to prevent race conditions when multiple
        users confirm simultaneously.
        
        Args:
            match_id: Match being confirmed
            player_id: Player responding
            status: CONFIRMED or REJECTED
            reason: Optional reason if rejected
            discord_user_id: Discord user who clicked button
            discord_message_id: Message where response was made
            
        Returns:
            Updated MatchConfirmation
            
        Raises:
            MatchValidationError: If confirmation record not found
            MatchStateError: If player already responded
        """
        async with self.db.get_session() as session:
            # Atomic UPDATE with status check in WHERE clause
            stmt = (
                update(MatchConfirmation)
                .where(
                    MatchConfirmation.match_id == match_id,
                    MatchConfirmation.player_id == player_id,
                    MatchConfirmation.status == ConfirmationStatus.PENDING
                )
                .values(
                    status=status,
                    responded_at=datetime.now(timezone.utc),
                    rejection_reason=reason if status == ConfirmationStatus.REJECTED else None,
                    discord_user_id=discord_user_id,
                    discord_message_id=discord_message_id
                )
            )
            
            result = await session.execute(stmt)
            await session.commit()
            
            # Check if update succeeded
            if result.rowcount == 0:
                # No rows updated - determine why
                check_result = await session.execute(
                    select(MatchConfirmation)
                    .where(
                        MatchConfirmation.match_id == match_id,
                        MatchConfirmation.player_id == player_id
                    )
                )
                existing = check_result.scalar_one_or_none()
                
                if not existing:
                    raise MatchValidationError(f"No confirmation record for Player {player_id} in Match {match_id}")
                else:
                    raise MatchStateError(f"Player {player_id} already responded to Match {match_id} with status: {existing.status.value}")
            
            # Fetch the updated confirmation
            result = await session.execute(
                select(MatchConfirmation)
                .options(selectinload(MatchConfirmation.player))
                .where(
                    MatchConfirmation.match_id == match_id,
                    MatchConfirmation.player_id == player_id
                )
            )
            confirmation = result.scalar_one()
            
            self.logger.info(f"Recorded {status.value} from Player {player_id} for Match {match_id}")
            return confirmation
    
    async def check_all_confirmed(self, match_id: int) -> Tuple[bool, List[MatchConfirmation]]:
        """
        Check if all participants have confirmed the results.
        
        Args:
            match_id: Match to check
            
        Returns:
            Tuple of (all_confirmed: bool, confirmations: List[MatchConfirmation])
        """
        async with self.db.get_session() as session:
            result = await session.execute(
                select(MatchConfirmation)
                .options(selectinload(MatchConfirmation.player))
                .where(MatchConfirmation.match_id == match_id)
            )
            confirmations = result.scalars().all()
            
            if not confirmations:
                return False, []
            
            # Check if all are confirmed (no pending or rejected)
            all_confirmed = all(
                c.status == ConfirmationStatus.CONFIRMED 
                for c in confirmations
            )
            
            return all_confirmed, confirmations
    
    async def finalize_confirmed_results(self, match_id: int) -> Match:
        """
        Finalize results after all confirmations received.
        
        Takes the proposed results and applies them using the existing
        complete_match_with_results method.
        
        Args:
            match_id: Match to finalize
            
        Returns:
            Completed Match with results
            
        Raises:
            MatchValidationError: If no active proposal
            MatchStateError: If not all players confirmed
        """
        async with self.db.get_session() as session:
            # Get active proposal
            result = await session.execute(
                select(MatchResultProposal)
                .where(MatchResultProposal.match_id == match_id)
                .where(MatchResultProposal.is_active == True)
            )
            proposal = result.scalar_one_or_none()
            
            if not proposal:
                raise MatchValidationError(f"No active proposal for Match {match_id}")
            
            # Check all confirmed
            all_confirmed, _ = await self.check_all_confirmed(match_id)
            if not all_confirmed:
                raise MatchStateError(f"Not all players have confirmed results for Match {match_id}")
            
            # Parse proposed results
            results = json.loads(proposal.proposed_results)
            
            # Mark proposal as inactive
            proposal.is_active = False
            await session.commit()
            
            # Use existing method to complete the match
            return await self.complete_match_with_results(match_id, results)
    
    async def cleanup_expired_proposals(self) -> int:
        """
        Clean up expired proposals and reset match status.
        
        This should be run periodically (e.g., hourly) to handle
        proposals that expired without all confirmations.
        
        Returns:
            Number of proposals cleaned up
        """
        async with self.db.get_session() as session:
            # Find expired active proposals
            result = await session.execute(
                select(MatchResultProposal)
                .options(selectinload(MatchResultProposal.match))
                .where(MatchResultProposal.is_active == True)
                .where(MatchResultProposal.expires_at < datetime.now(timezone.utc))
            )
            expired_proposals = result.scalars().all()
            
            count = 0
            for proposal in expired_proposals:
                # Reset match status if still awaiting
                if proposal.match and proposal.match.status == MatchStatus.AWAITING_CONFIRMATION:
                    proposal.match.status = MatchStatus.PENDING
                
                # Delete confirmation records
                await session.execute(
                    sql_delete(MatchConfirmation).where(
                        MatchConfirmation.match_id == proposal.match_id
                    )
                )
                
                # Delete the proposal itself
                await session.delete(proposal)
                
                count += 1
                self.logger.info(f"Cleaned up expired proposal for Match {proposal.match_id}")
            
            await session.commit()
            return count
    
    async def terminate_proposal(self, match_id: int, reason: str = "Rejected by participant") -> None:
        """
        Terminate an active result proposal due to rejection, resetting match state.
        
        This method performs atomic cleanup when any participant rejects the proposed
        results. It resets the match status to PENDING and cleans up all related records
        so that new proposals can be submitted.
        
        Args:
            match_id: Match whose proposal should be terminated
            reason: Reason for termination (for logging)
            
        Raises:
            MatchValidationError: If no active proposal exists
            MatchOperationError: If database operation fails
        """
        async with self.db.get_session() as session:
            try:
                # Find the match and verify it has an active proposal
                match_result = await session.execute(
                    select(Match)
                    .options(selectinload(Match.participants))
                    .where(Match.id == match_id)
                )
                match = match_result.scalar_one_or_none()
                
                if not match:
                    raise MatchValidationError(f"Match {match_id} not found")
                
                # Find active proposal for this match
                proposal_result = await session.execute(
                    select(MatchResultProposal)
                    .where(MatchResultProposal.match_id == match_id)
                    .where(MatchResultProposal.is_active == True)
                )
                proposal = proposal_result.scalar_one_or_none()
                
                if not proposal:
                    raise MatchValidationError(f"No active proposal found for Match {match_id}")
                
                # Reset match status to PENDING so new proposals can be created
                if match.status == MatchStatus.AWAITING_CONFIRMATION:
                    match.status = MatchStatus.PENDING
                    self.logger.info(f"Reset Match {match_id} status to PENDING due to rejection")
                
                # Delete all confirmation records for this match
                await session.execute(
                    sql_delete(MatchConfirmation).where(
                        MatchConfirmation.match_id == match_id
                    )
                )
                
                # Delete the proposal itself
                await session.delete(proposal)
                
                await session.commit()
                self.logger.info(f"Successfully terminated proposal for Match {match_id}: {reason}")
                
            except Exception as e:
                await session.rollback()
                self.logger.error(f"Failed to terminate proposal for Match {match_id}: {e}")
                raise MatchOperationError(f"Database error terminating proposal for Match {match_id}: {e}")
    
    # ============================================================================
    # Admin Operations - Match Management
    # ============================================================================
    
    async def clear_active_matches(
        self,
        statuses: Optional[List[MatchStatus]] = None,
        batch_size: int = 250
    ) -> Dict[str, int]:
        """
        Delete matches matching specified statuses in batches.
        
        Uses FK cascade ("all, delete-orphan") for automatic MatchParticipant deletion.
        Each batch is processed in its own transaction to avoid long locks.
        
        Args:
            statuses: List of match statuses to delete (default: PENDING, ACTIVE, AWAITING_CONFIRMATION)
            batch_size: Number of matches to process per batch
            
        Returns:
            Dictionary with status counts and error information
        """
        from sqlalchemy import func, delete
        
        if statuses is None:
            statuses = [MatchStatus.PENDING, MatchStatus.ACTIVE, MatchStatus.AWAITING_CONFIRMATION]
        
        results = {'total_deleted': 0, 'errors': 0}
        
        # Pre-count matches by status using database count
        async with self.db.get_session() as session:
            for status in statuses:
                count_stmt = select(func.count(Match.id)).where(Match.status == status)
                status_count = await session.scalar(count_stmt) or 0
                results[f'{status.value}_count'] = status_count
        
        # Process deletions in batches, each in its own transaction
        for status in statuses:
            processed_in_status = 0
            while True:
                try:
                    async with self.db.transaction() as session:
                        # Get batch of match IDs to delete
                        batch_stmt = (
                            select(Match.id)
                            .where(Match.status == status)
                            .limit(batch_size)
                        )
                        match_ids = (await session.execute(batch_stmt)).scalars().all()
                        
                        if not match_ids:
                            break  # No more matches for this status
                        
                        # Bulk delete matches (participants deleted via FK cascade)
                        delete_matches_stmt = delete(Match).where(Match.id.in_(match_ids))
                        await session.execute(delete_matches_stmt)
                        
                        # Transaction commits automatically when exiting this block
                        
                        batch_count = len(match_ids)
                        processed_in_status += batch_count
                        results['total_deleted'] += batch_count
                        
                        self.logger.info(
                            f"Deleted batch of {batch_count} {status.value} matches "
                            f"(total {processed_in_status} for this status)"
                        )
                        
                except Exception as e:
                    results['errors'] += 1
                    self.logger.error(f"Error processing batch of {status.value} matches: {e}", exc_info=True)
                    # Stop processing this status on error to prevent infinite loops
                    break
        
        return results
    
    async def delete_match_by_id(self, match_id: int) -> bool:
        """
        Delete a single match by its ID.
        
        Uses FK cascade to automatically delete associated MatchParticipant records.
        
        Args:
            match_id: ID of the match to delete
            
        Returns:
            True if match was deleted, False if match not found
        """
        async with self.db.get_session() as session:
            async with session.begin():
                match = await session.get(Match, match_id)
                if not match:
                    return False
                
                # The cascade="all, delete-orphan" on the relationship will handle participants
                await session.delete(match)
                
                self.logger.info(f"Admin deleted Match {match_id}")
                return True