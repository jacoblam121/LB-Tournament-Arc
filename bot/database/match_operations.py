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
from typing import List, Dict, Optional, Tuple, Union
from datetime import datetime, timedelta
from sqlalchemy import select, update, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from bot.database.models import (
    Match, MatchParticipant, MatchStatus, MatchFormat,
    Challenge, ChallengeStatus, MatchResult,
    Player, Event, EloHistory
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
    
    def __init__(self, database):
        """Initialize with database instance"""
        self.db = database
        self.logger = logger
    
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
                    .options(selectinload(Match.participants))
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
        admin_notes: Optional[str] = None
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
        async with self.db.get_session() as session:
            try:
                # Validate event exists and supports FFA
                result = await session.execute(
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
                
                player_result = await session.execute(
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
                
                session.add(match)
                await session.flush()  # Get Match ID
                
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
                    session.add(participant)
                
                await session.commit()
                
                # Reload match with relationships for return
                result = await session.execute(
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
                await session.rollback()
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
                
                for participant in match.participants:
                    if participant.player_id not in results_by_player:
                        raise MatchValidationError(
                            f"Missing result for participant {participant.player_id}"
                        )
                    
                    result_data = results_by_player[participant.player_id]
                    
                    participant_result = ParticipantResult(
                        player_id=participant.player_id,
                        current_elo=participant.player.elo_rating,
                        matches_played=participant.player.matches_played,
                        placement=result_data["placement"],
                        team_id=result_data.get("team_id")
                    )
                    participant_results.append(participant_result)
                
                # Calculate rating changes using appropriate scoring strategy
                scoring_strategy = await self._get_scoring_strategy(match.event.scoring_type)
                scoring_results = scoring_strategy.calculate_results(participant_results)
                
                # Update match status and timing
                now = datetime.utcnow()
                match.status = MatchStatus.COMPLETED
                match.completed_at = now
                if not match.started_at:
                    match.started_at = now  # Auto-set if not already set
                
                # Update MatchParticipant records with results and rating changes
                elo_history_records = []
                
                for participant in match.participants:
                    result_data = results_by_player[participant.player_id]
                    scoring_result = scoring_results[participant.player_id]
                    
                    # Update participant with results
                    participant.placement = result_data["placement"]
                    participant.elo_before = participant.player.elo_rating
                    participant.elo_change = scoring_result.elo_change
                    participant.pp_change = scoring_result.pp_change
                    participant.points_earned = scoring_result.points_earned
                    participant.elo_after = participant.elo_before + scoring_result.elo_change
                    
                    # Set team assignment if provided
                    if "team_id" in result_data:
                        participant.team_id = result_data["team_id"]
                    
                    # Update player's overall rating and stats
                    participant.player.elo_rating = participant.elo_after
                    participant.player.matches_played += 1
                    
                    # Update win/loss/draw stats
                    if match.match_format == MatchFormat.ONE_V_ONE:
                        if participant.placement == 1:
                            participant.player.wins += 1
                        elif participant.placement == 2:
                            participant.player.losses += 1
                        # Note: Draws handled when both players have placement=1
                    
                    # Create EloHistory record
                    elo_history = EloHistory(
                        player_id=participant.player_id,
                        old_elo=participant.elo_before,
                        new_elo=participant.elo_after,
                        elo_change=scoring_result.elo_change,
                        challenge_id=None,  # Match-based, not Challenge-based
                        match_id=match.id,
                        opponent_id=None,   # For multi-player, no single opponent
                        match_result=self._determine_match_result(participant.placement, len(match.participants)),
                        k_factor=scoring_strategy.get_k_factor(participant.player) if hasattr(scoring_strategy, 'get_k_factor') else 20,
                        recorded_at=now
                    )
                    elo_history_records.append(elo_history)
                    session.add(elo_history)
                
                # Sync to Challenge for backward compatibility (if bridged from Challenge)
                if match.challenge_id:
                    await self._sync_results_to_challenge(session, match)
                
                await session.commit()
                
                # Reload match with relationships for return
                result = await session.execute(
                    select(Match)
                    .options(selectinload(Match.participants))
                    .where(Match.id == match.id)
                )
                match = result.scalar_one()
                
                self.logger.info(
                    f"Successfully completed Match {match_id} with {len(results)} participants. "
                    f"Rating changes: {[(r['player_id'], scoring_results[r['player_id']].elo_change) for r in results]}"
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
    
    async def _get_scoring_strategy(self, scoring_type: str) -> ScoringStrategy:
        """Get appropriate scoring strategy based on event type"""
        if scoring_type == "1v1":
            return Elo1v1Strategy()
        elif scoring_type == "FFA":
            return EloFfaStrategy()
        elif scoring_type == "Team":
            return EloFfaStrategy()  # Team matches use FFA algorithm for now
        elif scoring_type == "Leaderboard":
            return PerformancePointsStrategy()
        else:
            raise MatchValidationError(f"Unknown scoring type: {scoring_type}")
    
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
        
        # Get Challenge
        result = await session.execute(
            select(Challenge).where(Challenge.id == match.challenge_id)
        )
        challenge = result.scalar_one_or_none()
        
        if not challenge:
            self.logger.warning(f"Challenge {match.challenge_id} not found for Match {match.id}")
            return
        
        # Get participants sorted by placement
        participants = sorted(match.participants, key=lambda p: p.placement)
        
        if len(participants) == 2:
            winner_participant = participants[0]  # placement = 1
            loser_participant = participants[1]   # placement = 2 (or 1 for tie)
            
            # Handle draws (both have same placement)
            if winner_participant.placement == loser_participant.placement:
                challenge.challenger_result = MatchResult.DRAW
                challenge.challenged_result = MatchResult.DRAW
            else:
                # Determine which participant is challenger vs challenged
                if winner_participant.player_id == challenge.challenger_id:
                    challenge.challenger_result = MatchResult.WIN
                    challenge.challenged_result = MatchResult.LOSS
                else:
                    challenge.challenger_result = MatchResult.LOSS
                    challenge.challenged_result = MatchResult.WIN
            
            # Update Elo changes (should already be set, but ensure consistency)
            challenger_participant = next(p for p in participants if p.player_id == challenge.challenger_id)
            challenged_participant = next(p for p in participants if p.player_id == challenge.challenged_id)
            
            challenge.challenger_elo_change = challenger_participant.elo_change
            challenge.challenged_elo_change = challenged_participant.elo_change
        
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