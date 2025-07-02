"""
Challenge Operations Service - Phase 2.4.2 Implementation

Handles all business logic for challenge creation and management,
supporting N-player challenges with proper role assignment and 
auto-transition to Match creation when all participants accept.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    Challenge, ChallengeStatus, ChallengeParticipant,
    ChallengeRole, ConfirmationStatus, Event, Player, Match
)
from bot.database.database import Database
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class ChallengeAcceptanceResult:
    """Result of challenge acceptance operation"""
    success: bool
    challenge: Optional[Challenge] = None
    match: Optional[Match] = None
    match_created: bool = False
    error_message: Optional[str] = None


class ChallengeOperationError(Exception):
    """Base exception for challenge operation errors"""
    pass


class DuplicateChallengeError(ChallengeOperationError):
    """Raised when attempting to create a duplicate active challenge"""
    pass


class InvalidPlayerCountError(ChallengeOperationError):
    """Raised when player count doesn't match match type requirements"""
    pass


class ChallengeOperations:
    """
    Service class for challenge-related operations.
    
    Manages challenge creation, participant management, and business logic
    for N-player challenges with role-based participants.
    """
    
    def __init__(self, db: Database):
        """
        Initialize ChallengeOperations with database connection.
        
        Args:
            db: Database instance for persistence
        """
        self.db = db
        self.logger = setup_logger(f"{__name__}.ChallengeOperations")
    
    async def create_challenge(
        self,
        event: Event,
        participants: List[Player],
        challenger: Player,
        match_type: str,
        team_assignments: Optional[Dict[int, str]] = None,  # Maps discord_id to team_id
        expires_in_hours: int = 24,
        session: Optional[AsyncSession] = None
    ) -> Challenge:
        """
        Create a new challenge with N participants.
        
        Args:
            event: Event the challenge is for
            participants: List of all participants (including challenger)
            challenger: The player initiating the challenge
            match_type: Type of match (1v1, ffa, team)
            team_assignments: Optional dict mapping player_id to team_id
            expires_in_hours: Hours until challenge expires
            session: Optional existing database session
            
        Returns:
            Created Challenge object with participants
            
        Raises:
            DuplicateChallengeError: If active challenge already exists
            InvalidPlayerCountError: If player count invalid for match type
        """
        async def _create(session: AsyncSession) -> Challenge:
            # Validate player count for match type
            if not self._validate_player_count(match_type, len(participants)):
                raise InvalidPlayerCountError(
                    f"Invalid player count {len(participants)} for match type {match_type}"
                )
            
            # Check for duplicate active challenges
            if await self._has_active_challenge(event.id, participants, session):
                raise DuplicateChallengeError(
                    "An active challenge already exists for these participants in this event"
                )
            
            # Create challenge
            challenge = Challenge(
                event_id=event.id,
                status=ChallengeStatus.PENDING,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_in_hours),
                elo_at_stake=True  # Default to competitive
            )
            session.add(challenge)
            await session.flush()  # Get challenge ID
            
            # Create participants with roles
            for player in participants:
                # Challenger is auto-confirmed, others start as pending
                is_challenger = player.id == challenger.id
                participant = ChallengeParticipant(
                    challenge_id=challenge.id,
                    player_id=player.id,
                    status=(ConfirmationStatus.CONFIRMED if is_challenger 
                           else ConfirmationStatus.PENDING),
                    role=(ChallengeRole.CHALLENGER if is_challenger 
                          else ChallengeRole.CHALLENGED),
                    team_id=team_assignments.get(player.discord_id) if team_assignments else None,
                    responded_at=(datetime.now(timezone.utc) if is_challenger else None)
                )
                session.add(participant)
            
            await session.flush()
            
            # Load relationships for return
            challenge = await self._load_challenge_with_participants(challenge.id, session)
            
            self.logger.info(
                f"Created challenge {challenge.id} for event {event.id} "
                f"with {len(participants)} participants"
            )
            
            return challenge
        
        # Use provided session or create new transaction
        if session:
            return await _create(session)
        else:
            async with self.db.transaction() as txn_session:
                return await _create(txn_session)
    
    async def get_challenge_by_id(
        self, 
        challenge_id: int,
        session: Optional[AsyncSession] = None
    ) -> Optional[Challenge]:
        """
        Retrieve a challenge by ID with all relationships loaded.
        
        Args:
            challenge_id: ID of the challenge to retrieve
            session: Optional existing database session
            
        Returns:
            Challenge object with participants loaded, or None if not found
        """
        async def _get(session: AsyncSession) -> Optional[Challenge]:
            return await self._load_challenge_with_participants(challenge_id, session)
        
        if session:
            return await _get(session)
        else:
            async with self.db.get_session() as db_session:
                return await _get(db_session)
    
    async def accept_challenge(
        self,
        challenge_id: int,
        player_discord_id: int,
        session: Optional[AsyncSession] = None
    ) -> ChallengeAcceptanceResult:
        """
        Process challenge acceptance with auto-transition to match creation.
        
        Args:
            challenge_id: ID of the challenge to accept
            player_discord_id: Discord ID of player accepting the challenge
            session: Optional existing database session
            
        Returns:
            ChallengeAcceptanceResult with success status and optional match
        """
        async def _accept(session: AsyncSession) -> ChallengeAcceptanceResult:
            # 1. Validate challenge exists and is active
            challenge = await self._load_challenge_with_participants(challenge_id, session)
            if not challenge:
                return ChallengeAcceptanceResult(
                    success=False, 
                    error_message="Challenge not found or expired"
                )
            
            if challenge.status != ChallengeStatus.PENDING:
                return ChallengeAcceptanceResult(
                    success=False,
                    error_message=f"Challenge is {challenge.status.value}, cannot accept"
                )
            
            # 2. Validate player is a participant
            participant = None
            for p in challenge.participants:
                if p.player.discord_id == player_discord_id:
                    participant = p
                    break
            
            if not participant:
                return ChallengeAcceptanceResult(
                    success=False,
                    error_message="You are not invited to this challenge"
                )
                
            # 3. Validate player hasn't already responded
            if participant.status != ConfirmationStatus.PENDING:
                return ChallengeAcceptanceResult(
                    success=False,
                    error_message=f"You have already {participant.status.value} this challenge"
                )
            
            # 4. Update participant status
            participant.status = ConfirmationStatus.CONFIRMED
            participant.responded_at = datetime.now(timezone.utc)
            
            # 5. Check if all participants have accepted
            all_participants = challenge.participants
            all_accepted = all(p.status == ConfirmationStatus.CONFIRMED for p in all_participants)
            
            if all_accepted:
                # 6. Auto-transition to Match creation
                match = await self._create_match_from_challenge(challenge, session)
                challenge.status = ChallengeStatus.COMPLETED
                challenge.completed_at = datetime.now(timezone.utc)
                
                self.logger.info(f"Challenge {challenge_id} fully accepted - Match {match.id} created")
                
                return ChallengeAcceptanceResult(
                    success=True,
                    challenge=challenge,
                    match=match,
                    match_created=True
                )
            else:
                self.logger.info(f"Challenge {challenge_id} partially accepted by player {player_discord_id}")
                return ChallengeAcceptanceResult(
                    success=True,
                    challenge=challenge,
                    match_created=False
                )
        
        if session:
            return await _accept(session)
        else:
            async with self.db.transaction() as txn_session:
                return await _accept(txn_session)
    
    async def decline_challenge(
        self,
        challenge_id: int,
        player_discord_id: int,
        reason: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> ChallengeAcceptanceResult:
        """
        Process challenge decline - cancels entire challenge.
        
        Args:
            challenge_id: ID of the challenge to decline
            player_discord_id: Discord ID of player declining the challenge
            reason: Optional reason for declining
            session: Optional existing database session
            
        Returns:
            ChallengeAcceptanceResult with success status
        """
        async def _decline(session: AsyncSession) -> ChallengeAcceptanceResult:
            # 1. Validate challenge exists and is active
            challenge = await self._load_challenge_with_participants(challenge_id, session)
            if not challenge:
                return ChallengeAcceptanceResult(
                    success=False, 
                    error_message="Challenge not found or expired"
                )
            
            if challenge.status != ChallengeStatus.PENDING:
                return ChallengeAcceptanceResult(
                    success=False,
                    error_message=f"Challenge is {challenge.status.value}, cannot decline"
                )
            
            # 2. Validate player is a participant
            participant = None
            for p in challenge.participants:
                if p.player.discord_id == player_discord_id:
                    participant = p
                    break
            
            if not participant:
                return ChallengeAcceptanceResult(
                    success=False,
                    error_message="You are not invited to this challenge"
                )
                
            # 3. Validate player hasn't already responded
            if participant.status != ConfirmationStatus.PENDING:
                return ChallengeAcceptanceResult(
                    success=False,
                    error_message=f"You have already {participant.status.value} this challenge"
                )
            
            # 4. Update participant status
            participant.status = ConfirmationStatus.REJECTED
            participant.responded_at = datetime.now(timezone.utc)
            
            # 5. Cancel entire challenge (any decline cancels the whole challenge)
            challenge.status = ChallengeStatus.CANCELLED
            if reason:
                current_notes = challenge.admin_notes or ""
                note = f"Declined by {player_discord_id}: {reason}"
                challenge.admin_notes = f"{current_notes}\n{note}".strip() if current_notes else note
            
            await session.flush()
            
            self.logger.info(
                f"Challenge {challenge_id} declined by player {player_discord_id}" + 
                (f" - Reason: {reason}" if reason else "")
            )
            
            return ChallengeAcceptanceResult(
                success=True,
                challenge=challenge,
                match_created=False
            )
        
        if session:
            return await _decline(session)
        else:
            async with self.db.transaction() as txn_session:
                return await _decline(txn_session)
    
    async def expire_challenge(
        self,
        challenge_id: int,
        session: Optional[AsyncSession] = None
    ) -> Challenge:
        """
        Mark a challenge as expired.
        
        Args:
            challenge_id: ID of the challenge to expire
            session: Optional existing database session
            
        Returns:
            Updated Challenge object
            
        Raises:
            ChallengeOperationError: If challenge not found
        """
        async def _expire(session: AsyncSession) -> Challenge:
            challenge = await self._load_challenge_with_participants(challenge_id, session)
            if not challenge:
                raise ChallengeOperationError(f"Challenge {challenge_id} not found")
            
            challenge.status = ChallengeStatus.EXPIRED
            await session.flush()
            
            self.logger.info(f"Challenge {challenge_id} marked as expired")
            return challenge
        
        if session:
            return await _expire(session)
        else:
            async with self.db.transaction() as txn_session:
                return await _expire(txn_session)
    
    async def get_active_challenges_for_player(
        self,
        player: Player,
        session: Optional[AsyncSession] = None
    ) -> List[Challenge]:
        """
        Get all active challenges for a player.
        
        Args:
            player: Player to get challenges for
            session: Optional existing database session
            
        Returns:
            List of active Challenge objects
        """
        async def _get(session: AsyncSession) -> List[Challenge]:
            # Query for challenges where player is a participant
            stmt = (
                select(Challenge)
                .join(ChallengeParticipant)
                .where(
                    and_(
                        ChallengeParticipant.player_id == player.id,
                        Challenge.status.in_([
                            ChallengeStatus.PENDING,
                            ChallengeStatus.ACCEPTED
                        ])
                    )
                )
                .options(
                    selectinload(Challenge.event),
                    selectinload(Challenge.participants).selectinload(
                        ChallengeParticipant.player
                    )
                )
                .distinct()
            )
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
        
        if session:
            return await _get(session)
        else:
            async with self.db.get_session() as db_session:
                return await _get(db_session)
    
    async def get_pending_challenges_for_player(
        self,
        player_discord_id: int,
        session: Optional[AsyncSession] = None
    ) -> List[Challenge]:
        """
        Get all pending challenges for a player by Discord ID.
        Only includes challenges where player has PENDING status (needs to respond).
        Challengers who are auto-confirmed won't appear in this list.
        
        Args:
            player_discord_id: Discord ID of the player
            session: Optional existing database session
            
        Returns:
            List of pending Challenge objects where player needs to respond
        """
        async def _get(session: AsyncSession) -> List[Challenge]:
            # Query for challenges where player has PENDING status (needs to respond)
            # Challengers who are auto-confirmed don't appear in pending list
            stmt = (
                select(Challenge)
                .join(ChallengeParticipant)
                .join(Player)
                .where(
                    and_(
                        Player.discord_id == player_discord_id,
                        ChallengeParticipant.status == ConfirmationStatus.PENDING,
                        Challenge.status == ChallengeStatus.PENDING
                    )
                )
                .options(
                    selectinload(Challenge.event),
                    selectinload(Challenge.participants).selectinload(
                        ChallengeParticipant.player
                    )
                )
                .distinct()
                .order_by(Challenge.created_at.desc())  # Most recent first for auto-discovery
            )
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
        
        if session:
            return await _get(session)
        else:
            async with self.db.get_session() as db_session:
                return await _get(db_session)
    
    async def cleanup_expired_challenges(
        self,
        session: Optional[AsyncSession] = None
    ) -> int:
        """
        Mark expired challenges as EXPIRED and return count of challenges processed.
        
        Args:
            session: Optional existing database session
            
        Returns:
            Number of challenges marked as expired
        """
        async def _cleanup(session: AsyncSession) -> int:
            # Find pending challenges past their expiration time
            now = datetime.now(timezone.utc)
            stmt = (
                select(Challenge)
                .where(
                    and_(
                        Challenge.status == ChallengeStatus.PENDING,
                        Challenge.expires_at < now
                    )
                )
            )
            
            result = await session.execute(stmt)
            expired_challenges = result.scalars().all()
            
            # Mark as expired
            count = 0
            for challenge in expired_challenges:
                challenge.status = ChallengeStatus.EXPIRED
                count += 1
                self.logger.info(f"Expired challenge {challenge.id}")
            
            await session.flush()
            return count
        
        if session:
            return await _cleanup(session)
        else:
            async with self.db.transaction() as txn_session:
                return await _cleanup(txn_session)
    
    async def get_outgoing_challenges(
        self,
        player_discord_id: int,
        include_expired: bool = True,
        show_cancelled: bool = False,
        show_completed: bool = False,
        session: Optional[AsyncSession] = None
    ) -> List[Challenge]:
        """
        Get all challenges created by a player (where they are the CHALLENGER).
        
        Args:
            player_discord_id: Discord ID of the player
            include_expired: Whether to include expired challenges
            show_cancelled: Whether to include cancelled challenges
            show_completed: Whether to include completed challenges
            session: Optional existing database session
            
        Returns:
            List of Challenge objects created by the player
        """
        async def _get(session: AsyncSession) -> List[Challenge]:
            stmt = (
                select(Challenge)
                .join(ChallengeParticipant)
                .join(Player)
                .where(
                    and_(
                        Player.discord_id == player_discord_id,
                        ChallengeParticipant.role == ChallengeRole.CHALLENGER
                    )
                )
                .options(
                    selectinload(Challenge.event).selectinload(Event.cluster),
                    selectinload(Challenge.participants).selectinload(
                        ChallengeParticipant.player
                    )
                )
                .distinct()
                .order_by(Challenge.created_at.desc())
            )
            
            # Optionally filter out expired challenges
            if not include_expired:
                stmt = stmt.where(Challenge.status != ChallengeStatus.EXPIRED)
            
            # Optionally filter out cancelled challenges  
            if not show_cancelled:
                stmt = stmt.where(Challenge.status != ChallengeStatus.CANCELLED)
                
            # Optionally filter out completed challenges
            if not show_completed:
                stmt = stmt.where(Challenge.status != ChallengeStatus.COMPLETED)
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
        
        if session:
            return await _get(session)
        else:
            async with self.db.get_session() as db_session:
                return await _get(db_session)
    
    async def get_incoming_challenges(
        self,
        player_discord_id: int,
        show_cancelled: bool = False,
        show_completed: bool = False,
        session: Optional[AsyncSession] = None
    ) -> List[Challenge]:
        """
        Get challenges where player is invited (CHALLENGED role).
        
        Args:
            player_discord_id: Discord ID of the player
            show_cancelled: Whether to include cancelled challenges
            show_completed: Whether to include completed challenges
            session: Optional existing database session
            
        Returns:
            List of Challenge objects where player is invited
        """
        async def _get(session: AsyncSession) -> List[Challenge]:
            # Base query for challenges where player has CHALLENGED role
            stmt = (
                select(Challenge)
                .join(ChallengeParticipant)
                .join(Player)
                .where(
                    and_(
                        Player.discord_id == player_discord_id,
                        ChallengeParticipant.role == ChallengeRole.CHALLENGED
                    )
                )
                .options(
                    selectinload(Challenge.event).selectinload(Event.cluster),
                    selectinload(Challenge.participants).selectinload(
                        ChallengeParticipant.player
                    )
                )
                .distinct()
                .order_by(Challenge.created_at.asc())  # Oldest first for FIFO
            )
            
            # Build filtering conditions based on parameters
            conditions = []
            
            # Always include pending challenges where player hasn't responded
            conditions.append(
                and_(
                    ChallengeParticipant.status == ConfirmationStatus.PENDING,
                    Challenge.status == ChallengeStatus.PENDING
                )
            )
            
            # Optionally include cancelled challenges
            if show_cancelled:
                conditions.append(Challenge.status == ChallengeStatus.CANCELLED)
            
            # Optionally include completed challenges
            if show_completed:
                conditions.append(Challenge.status == ChallengeStatus.COMPLETED)
            
            # Apply combined conditions
            stmt = stmt.where(or_(*conditions))
            
            result = await session.execute(stmt)
            return list(result.scalars().all())
        
        if session:
            return await _get(session)
        else:
            async with self.db.get_session() as db_session:
                return await _get(db_session)
    
    async def get_active_challenges(
        self,
        player_discord_id: int,
        show_cancelled: bool = False,
        session: Optional[AsyncSession] = None
    ) -> List[Challenge]:
        """
        Get all active challenges where player is a participant.
        Includes both ACCEPTED challenges (waiting for match creation) and 
        COMPLETED challenges with associated matches.
        
        Args:
            player_discord_id: Discord ID of the player
            show_cancelled: Whether to include cancelled challenges
            session: Optional existing database session
            
        Returns:
            List of active Challenge objects (ACCEPTED + COMPLETED with matches)
        """
        async def _get(session: AsyncSession) -> List[Challenge]:
            # Query for ACCEPTED challenges (waiting for match creation)
            accepted_stmt = (
                select(Challenge)
                .join(ChallengeParticipant)
                .join(Player)
                .where(
                    and_(
                        Player.discord_id == player_discord_id,
                        Challenge.status == ChallengeStatus.ACCEPTED
                    )
                )
                .options(
                    selectinload(Challenge.event).selectinload(Event.cluster),
                    selectinload(Challenge.participants).selectinload(
                        ChallengeParticipant.player
                    )
                )
                .distinct()
            )
            
            # Query for COMPLETED challenges that have associated matches
            completed_stmt = (
                select(Challenge)
                .join(ChallengeParticipant)
                .join(Player)
                .join(Match, Challenge.id == Match.challenge_id)
                .where(
                    and_(
                        Player.discord_id == player_discord_id,
                        Challenge.status == ChallengeStatus.COMPLETED
                    )
                )
                .options(
                    selectinload(Challenge.event).selectinload(Event.cluster),
                    selectinload(Challenge.participants).selectinload(
                        ChallengeParticipant.player
                    )
                )
                .distinct()
            )
            
            # Execute both queries
            accepted_result = await session.execute(accepted_stmt)
            completed_result = await session.execute(completed_stmt)
            
            # Combine results and sort by most recent activity
            accepted_challenges = list(accepted_result.scalars().all())
            completed_challenges = list(completed_result.scalars().all())
            
            all_challenges = accepted_challenges + completed_challenges
            
            # Sort by most recent activity (accepted_at for ACCEPTED, completed_at for COMPLETED)
            all_challenges.sort(
                key=lambda c: c.completed_at if c.status == ChallengeStatus.COMPLETED else c.accepted_at,
                reverse=True
            )
            
            return all_challenges
        
        if session:
            return await _get(session)
        else:
            async with self.db.get_session() as db_session:
                return await _get(db_session)
    
    async def cancel_challenge(
        self,
        challenge_id: int,
        player_discord_id: int,
        session: Optional[AsyncSession] = None
    ) -> Challenge:
        """
        Cancel a pending challenge. Uses atomic UPDATE to prevent race conditions.
        
        Args:
            challenge_id: ID of the challenge to cancel
            player_discord_id: Discord ID of the player attempting to cancel
            session: Optional existing database session
            
        Returns:
            Updated Challenge object
            
        Raises:
            ChallengeOperationError: If challenge not found, not pending, or user not challenger
        """
        async def _cancel(session: AsyncSession) -> Challenge:
            from sqlalchemy import update
            
            # First check if user is the challenger using a subquery
            challenger_check = (
                select(ChallengeParticipant.challenge_id)
                .join(Player)
                .where(
                    and_(
                        ChallengeParticipant.challenge_id == challenge_id,
                        Player.discord_id == player_discord_id,
                        ChallengeParticipant.role == ChallengeRole.CHALLENGER
                    )
                )
            )
            
            # Atomic UPDATE with all conditions - prevents race conditions
            stmt = (
                update(Challenge)
                .where(
                    and_(
                        Challenge.id == challenge_id,
                        Challenge.status == ChallengeStatus.PENDING,
                        Challenge.id.in_(challenger_check)
                    )
                )
                .values(
                    status=ChallengeStatus.CANCELLED,
                    admin_notes=func.concat(
                        func.coalesce(Challenge.admin_notes, ''),
                        f'\nCancelled by player {player_discord_id} at {datetime.now(timezone.utc).isoformat()}'
                    )
                )
            )
            
            result = await session.execute(stmt)
            
            # Check if update succeeded
            if result.rowcount != 1:
                # Determine specific error for better user feedback
                challenge = await self._load_challenge_with_participants(challenge_id, session)
                if not challenge:
                    raise ChallengeOperationError("Challenge not found")
                elif challenge.status != ChallengeStatus.PENDING:
                    raise ChallengeOperationError(
                        f"Cannot cancel - challenge is {challenge.status.value}"
                    )
                else:
                    # User is not the challenger
                    raise ChallengeOperationError(
                        "You can only cancel challenges you created"
                    )
            
            # Reload the updated challenge with all relationships
            challenge = await self._load_challenge_with_participants(challenge_id, session)
            
            self.logger.info(
                f"Challenge {challenge_id} cancelled by player {player_discord_id}"
            )
            
            return challenge
        
        if session:
            return await _cancel(session)
        else:
            async with self.db.transaction() as txn_session:
                return await _cancel(txn_session)
    
    async def cancel_latest_pending_challenge(
        self,
        player_discord_id: int,
        session: Optional[AsyncSession] = None
    ) -> Optional[Challenge]:
        """
        Cancel the most recent pending challenge created by the player.
        Used for auto-cancel functionality.
        
        Args:
            player_discord_id: Discord ID of the player
            session: Optional existing database session
            
        Returns:
            Cancelled Challenge object or None if no pending challenges
        """
        async def _cancel_latest(session: AsyncSession) -> Optional[Challenge]:
            # Get most recent pending challenge where user is challenger
            outgoing_challenges = await self.get_outgoing_challenges(
                player_discord_id, 
                include_expired=False,
                session=session
            )
            
            # Filter to only pending challenges
            pending_challenges = [
                c for c in outgoing_challenges 
                if c.status == ChallengeStatus.PENDING
            ]
            
            if not pending_challenges:
                return None
            
            # Cancel the most recent (first in list since ordered desc)
            latest_challenge = pending_challenges[0]
            return await self.cancel_challenge(
                latest_challenge.id,
                player_discord_id,
                session=session
            )
        
        if session:
            return await _cancel_latest(session)
        else:
            async with self.db.transaction() as txn_session:
                return await _cancel_latest(txn_session)
    
    async def clear_active_challenges(
        self,
        statuses: Optional[List[ChallengeStatus]] = None,
        batch_size: int = 250
    ) -> Dict[str, int]:
        """
        Delete challenges matching specified statuses in batches.
        
        Args:
            statuses: List of challenge statuses to delete (default: PENDING, ACCEPTED)
            batch_size: Number of challenges to process per batch
            
        Returns:
            Dictionary with status counts and error information
        """
        from sqlalchemy import func, delete
        
        if statuses is None:
            statuses = [ChallengeStatus.PENDING, ChallengeStatus.ACCEPTED]
        
        results = {'total_deleted': 0, 'errors': 0}
        
        # Pre-count challenges by status using database count
        async with self.db.get_session() as session:
            for status in statuses:
                count_stmt = select(func.count(Challenge.id)).where(Challenge.status == status)
                status_count = await session.scalar(count_stmt) or 0
                results[f'{status.value}_count'] = status_count
        
        # Process deletions in batches, each in its own transaction
        for status in statuses:
            processed_in_status = 0
            while True:
                try:
                    async with self.db.transaction() as session:
                        # Get batch of challenge IDs to delete
                        batch_stmt = (
                            select(Challenge.id)
                            .where(Challenge.status == status)
                            .limit(batch_size)
                        )
                        challenge_ids = (await session.execute(batch_stmt)).scalars().all()
                        
                        if not challenge_ids:
                            break  # No more challenges for this status
                        
                        # Bulk delete participants first (FK constraint)
                        delete_participants_stmt = delete(ChallengeParticipant).where(
                            ChallengeParticipant.challenge_id.in_(challenge_ids)
                        )
                        await session.execute(delete_participants_stmt)
                        
                        # Bulk delete challenges
                        delete_challenges_stmt = delete(Challenge).where(
                            Challenge.id.in_(challenge_ids)
                        )
                        await session.execute(delete_challenges_stmt)
                        
                        # Transaction commits automatically when exiting this block
                        
                        batch_count = len(challenge_ids)
                        processed_in_status += batch_count
                        results['total_deleted'] += batch_count
                        
                        self.logger.info(
                            f"Deleted batch of {batch_count} {status.value} challenges "
                            f"(total {processed_in_status} for this status)"
                        )
                        
                except Exception as e:
                    results['errors'] += 1
                    self.logger.error(f"Error processing batch of {status.value} challenges: {e}", exc_info=True)
                    # Stop processing this status on error to prevent infinite loops
                    break
        
        return results
    
    # Private helper methods
    
    async def _create_match_from_challenge(
        self, 
        challenge: Challenge, 
        session: AsyncSession
    ) -> Match:
        """
        Bridge function: Create Match from accepted Challenge.
        
        Note: The existing MatchOperations.create_match_from_challenge() expects 
        legacy Challenge data and manages its own session. For now, we'll create
        a basic Match record directly to maintain transaction integrity.
        """
        from bot.database.models import Match, MatchParticipant, MatchStatus, MatchFormat
        
        # CRITICAL: Check if a match already exists for this challenge
        existing_match_stmt = select(Match).where(Match.challenge_id == challenge.id)
        existing_match_result = await session.execute(existing_match_stmt)
        existing_match = existing_match_result.scalar_one_or_none()
        
        if existing_match:
            self.logger.info(f"Match {existing_match.id} already exists for Challenge {challenge.id}")
            return existing_match
        
        # Determine match format based on participant count and challenge data
        participant_count = len(challenge.participants)
        if participant_count == 2:
            match_format = MatchFormat.ONE_V_ONE
            scoring_type = "1v1"
        elif participant_count > 2:
            # Check if there are teams assigned
            has_teams = any(p.team_id for p in challenge.participants)
            if has_teams:
                match_format = MatchFormat.TEAM
                scoring_type = "Team"
            else:
                match_format = MatchFormat.FFA
                scoring_type = "FFA"
        else:
            raise ChallengeOperationError(f"Invalid participant count: {participant_count}")
        
        # Create Match record
        match = Match(
            event_id=challenge.event_id,
            match_format=match_format,
            scoring_type=scoring_type,
            status=MatchStatus.PENDING,
            challenge_id=challenge.id,
            created_by=next(
                (p.player_id for p in challenge.participants if p.role == ChallengeRole.CHALLENGER),
                challenge.participants[0].player_id  # Fallback
            ),
            started_at=datetime.now(timezone.utc)
        )
        session.add(match)
        await session.flush()  # Get match ID
        
        # Create MatchParticipant records from ChallengeParticipant
        # First, gather all Elo data in a single query to avoid N+1
        from bot.database.models import PlayerEventStats
        participant_ids = [p.player_id for p in challenge.participants]
        
        elo_stmt = (
            select(PlayerEventStats.player_id, PlayerEventStats.scoring_elo)
            .where(
                PlayerEventStats.player_id.in_(participant_ids),
                PlayerEventStats.event_id == challenge.event_id
            )
        )
        elo_results = await session.execute(elo_stmt)
        # Create a dictionary of player_id -> elo
        participant_elos = {player_id: elo for player_id, elo in elo_results}
        
        # Use default Elo for players without existing stats
        for participant in challenge.participants:
            if participant.player_id not in participant_elos:
                participant_elos[participant.player_id] = 1000  # Default Elo
        
        # Check for existing participants to prevent orphaned data conflicts
        existing_participants_stmt = select(MatchParticipant).where(MatchParticipant.match_id == match.id)
        existing_participants_result = await session.execute(existing_participants_stmt)
        existing_participants = existing_participants_result.scalars().all()
        
        if existing_participants:
            self.logger.warning(f"Match {match.id} already has {len(existing_participants)} participants, skipping participant creation")
        else:
            # Now create all participants with the gathered data
            for challenge_participant in challenge.participants:
                match_participant = MatchParticipant(
                    match_id=match.id,
                    player_id=challenge_participant.player_id,
                    team_id=challenge_participant.team_id,  # Preserve team assignments
                    elo_before=participant_elos[challenge_participant.player_id]
                )
                session.add(match_participant)
            
            await session.flush()
        
        self.logger.info(
            f"Created Match {match.id} from Challenge {challenge.id} "
            f"with {participant_count} participants ({scoring_type})"
        )
        
        return match
    
    def _validate_player_count(self, match_type: str, player_count: int) -> bool:
        """Validate player count for match type"""
        match_type_lower = match_type.lower()
        
        if match_type_lower == "1v1":
            return player_count == 2
        elif match_type_lower == "ffa":
            return 3 <= player_count <= 8
        elif match_type_lower == "team":
            return player_count >= 2 and player_count <= 8  # Allow uneven teams
        else:
            return False
    
    async def _has_active_challenge(
        self,
        event_id: int,
        participants: List[Player],
        session: AsyncSession
    ) -> bool:
        """Check if an active challenge exists for these participants"""
        participant_ids = {p.id for p in participants}
        
        # Query for active challenges in this event
        stmt = (
            select(Challenge)
            .where(
                and_(
                    Challenge.event_id == event_id,
                    Challenge.status.in_([
                        ChallengeStatus.PENDING,
                        ChallengeStatus.ACCEPTED
                    ])
                )
            )
            .options(selectinload(Challenge.participants))
        )
        
        result = await session.execute(stmt)
        active_challenges = result.scalars().all()
        
        # Check if any active challenge has the same participant set
        for challenge in active_challenges:
            challenge_participant_ids = {p.player_id for p in challenge.participants}
            if challenge_participant_ids == participant_ids:
                return True
        
        return False
    
    async def _load_challenge_with_participants(
        self,
        challenge_id: int,
        session: AsyncSession
    ) -> Optional[Challenge]:
        """Load a challenge with all relationships"""
        stmt = (
            select(Challenge)
            .where(Challenge.id == challenge_id)
            .options(
                selectinload(Challenge.event).selectinload(Event.cluster),
                selectinload(Challenge.participants).selectinload(
                    ChallengeParticipant.player
                )
            )
        )
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()