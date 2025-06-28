"""
Challenge Operations Service - Phase 2.2 Implementation

Handles all business logic for challenge creation and management,
supporting N-player challenges with proper role assignment.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import (
    Challenge, ChallengeStatus, ChallengeParticipant,
    ChallengeRole, ConfirmationStatus, Event, Player
)
from bot.database.database import Database
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


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
                expires_at=datetime.utcnow() + timedelta(hours=expires_in_hours),
                elo_at_stake=True  # Default to competitive
            )
            session.add(challenge)
            await session.flush()  # Get challenge ID
            
            # Create participants with roles
            for player in participants:
                participant = ChallengeParticipant(
                    challenge_id=challenge.id,
                    player_id=player.id,
                    status=ConfirmationStatus.PENDING,
                    role=(ChallengeRole.CHALLENGER if player.id == challenger.id 
                          else ChallengeRole.CHALLENGED),
                    team_id=team_assignments.get(player.discord_id) if team_assignments else None
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
        player: Player,
        session: Optional[AsyncSession] = None
    ) -> Challenge:
        """
        Mark a player as accepting the challenge.
        
        Args:
            challenge_id: ID of the challenge to accept
            player: Player accepting the challenge
            session: Optional existing database session
            
        Returns:
            Updated Challenge object
            
        Raises:
            ChallengeOperationError: If challenge not found or player not participant
        """
        async def _accept(session: AsyncSession) -> Challenge:
            # Get challenge with participants
            challenge = await self._load_challenge_with_participants(challenge_id, session)
            if not challenge:
                raise ChallengeOperationError(f"Challenge {challenge_id} not found")
            
            # Find participant record
            participant = None
            for p in challenge.participants:
                if p.player_id == player.id:
                    participant = p
                    break
            
            if not participant:
                raise ChallengeOperationError(
                    f"Player {player.id} is not a participant in challenge {challenge_id}"
                )
            
            # Update participant status
            participant.status = ConfirmationStatus.CONFIRMED
            participant.responded_at = datetime.utcnow()
            
            # Check if all participants have accepted
            all_accepted = all(
                p.status == ConfirmationStatus.CONFIRMED 
                for p in challenge.participants
            )
            
            if all_accepted:
                challenge.status = ChallengeStatus.ACCEPTED
                challenge.accepted_at = datetime.utcnow()
                self.logger.info(f"Challenge {challenge_id} fully accepted by all participants")
            
            await session.flush()
            return challenge
        
        if session:
            return await _accept(session)
        else:
            async with self.db.transaction() as txn_session:
                return await _accept(txn_session)
    
    async def decline_challenge(
        self,
        challenge_id: int,
        player: Player,
        session: Optional[AsyncSession] = None
    ) -> Challenge:
        """
        Mark a player as declining the challenge.
        
        Args:
            challenge_id: ID of the challenge to decline
            player: Player declining the challenge
            session: Optional existing database session
            
        Returns:
            Updated Challenge object
            
        Raises:
            ChallengeOperationError: If challenge not found or player not participant
        """
        async def _decline(session: AsyncSession) -> Challenge:
            # Get challenge with participants
            challenge = await self._load_challenge_with_participants(challenge_id, session)
            if not challenge:
                raise ChallengeOperationError(f"Challenge {challenge_id} not found")
            
            # Find participant record
            participant = None
            for p in challenge.participants:
                if p.player_id == player.id:
                    participant = p
                    break
            
            if not participant:
                raise ChallengeOperationError(
                    f"Player {player.id} is not a participant in challenge {challenge_id}"
                )
            
            # Update participant status
            participant.status = ConfirmationStatus.REJECTED
            participant.responded_at = datetime.utcnow()
            
            # Mark challenge as declined
            challenge.status = ChallengeStatus.DECLINED
            
            await session.flush()
            
            self.logger.info(
                f"Challenge {challenge_id} declined by player {player.id}"
            )
            
            return challenge
        
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
    
    # Private helper methods
    
    def _validate_player_count(self, match_type: str, player_count: int) -> bool:
        """Validate player count for match type"""
        match_type_lower = match_type.lower()
        
        if match_type_lower == "1v1":
            return player_count == 2
        elif match_type_lower == "ffa":
            return 3 <= player_count <= 8
        elif match_type_lower == "team":
            return player_count >= 2 and player_count % 2 == 0  # Even number for teams
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
                selectinload(Challenge.event),
                selectinload(Challenge.participants).selectinload(
                    ChallengeParticipant.player
                )
            )
        )
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()