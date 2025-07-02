import asyncio
import csv
import os
from typing import Optional, List, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, delete, func
from contextlib import asynccontextmanager

from bot.config import Config
from bot.database.models import (
    Base, Player, Game, Challenge, Tournament, EloHistory, Ticket, 
    ChallengeStatus, MatchResult, Cluster, Event,
    Match, MatchParticipant, MatchStatus, MatchFormat,  # Phase 2A2: Match models
    ConfirmationStatus, MatchResultProposal, MatchConfirmation,  # Phase B: Confirmation models
    PlayerEventStats, PlayerEventPersonalBest, WeeklyScores, PlayerWeeklyLeaderboardElo, TicketLedger  # Phase 1.1: Per-event tracking
)
from bot.utils.logger import setup_logger

class Database:
    def __init__(self):
        self.logger = setup_logger(__name__)
        self.engine = None
        self.async_session = None
        
    async def initialize(self):
        """Initialize the database connection and create tables"""
        self.logger.info("Initializing database...")
        
        # Convert sqlite URL to async if needed
        database_url = Config.DATABASE_URL
        if database_url.startswith('sqlite:///'):
            database_url = database_url.replace('sqlite:///', 'sqlite+aiosqlite:///')
        
        self.engine = create_async_engine(
            database_url,
            echo=Config.DEBUG,
            future=True
        )
        
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Create all tables
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        self.logger.info("Database initialized successfully")
        
        # Initialize default data
        await self.initialize_default_data()
        
    async def initialize_default_data(self):
        """Initialize default games and other required data"""
        async with self.get_session() as session:
            # Check if we already have games
            result = await session.execute(select(func.count(Game.id)))
            game_count = result.scalar()
            
            if game_count == 0:
                self.logger.info("Initializing default games...")
                
                default_games = [
                    Game(name="Dragon Ball FighterZ", is_active=True),
                    Game(name="Guilty Gear Strive", is_active=True),
                    Game(name="Street Fighter 6", is_active=True),
                    Game(name="Tekken 8", is_active=True),
                    Game(name="King of Fighters XV", is_active=True),
                    Game(name="Granblue Fantasy Versus Rising", is_active=True),
                    Game(name="BlazBlue Central Fiction", is_active=True),
                    Game(name="Melty Blood Type Lumina", is_active=True),
                    Game(name="Under Night In-Birth", is_active=True),
                    Game(name="Mortal Kombat 1", is_active=True),
                ]
                
                for game in default_games:
                    session.add(game)
                
                await session.commit()
                self.logger.info(f"Added {len(default_games)} default games")
            
            # Check if we already have clusters
            result = await session.execute(select(func.count(Cluster.id)))
            cluster_count = result.scalar()
            
            if cluster_count == 0:
                # Phase 2.4.1: Disabled automatic CSV import
                # Use standalone populate_from_csv.py script instead for unified event creation
                self.logger.info("No clusters found. Run populate_from_csv.py to initialize data.")
                # await self.import_clusters_and_events_from_csv(session)
    
    @asynccontextmanager
    async def get_session(self):
        """Get a database session"""
        async with self.async_session() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    @asynccontextmanager
    async def transaction(self):
        """
        Create a transaction boundary for atomic operations.
        
        This context manager provides a database session with transaction control.
        All operations within the context will be committed together on success,
        or rolled back together on failure.
        
        Usage:
            async with db.transaction() as session:
                await player_ops.create_player(..., session=session)
                await event_ops.create_event(..., session=session)
                await match_ops.create_match(..., session=session)
                # All operations commit together here
        
        Important: The caller is responsible for passing the yielded session to
        all participating operations. Exceptions must be allowed to propagate
        out of the context for rollback to occur.
        """
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def close(self):
        """Close the database connection"""
        if self.engine:
            await self.engine.dispose()
            self.logger.info("Database connection closed")
    
    # Player operations
    async def get_player_by_discord_id(self, discord_id: int) -> Optional[Player]:
        """Get a player by their Discord ID"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Player).where(Player.discord_id == discord_id)
            )
            return result.scalar_one_or_none()
    
    async def create_player(self, discord_id: int, username: str, display_name: str = None) -> Player:
        """Create a new player"""
        async with self.get_session() as session:
            player = Player(
                discord_id=discord_id,
                username=username,
                display_name=display_name or username,
                elo_rating=Config.STARTING_ELO,
                tickets=Config.STARTING_TICKETS
            )
            session.add(player)
            await session.commit()
            await session.refresh(player)
            return player
    
    async def update_player_activity(self, discord_id: int):
        """Update a player's last activity timestamp"""
        async with self.get_session() as session:
            await session.execute(
                update(Player)
                .where(Player.discord_id == discord_id)
                .values(last_active=func.now())
            )
            await session.commit()
    
    async def get_leaderboard(self, limit: int = 10) -> List[Player]:
        """Get the top players by Elo rating"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Player)
                .where(Player.is_active == True)
                .order_by(Player.elo_rating.desc())
                .limit(limit)
            )
            return result.scalars().all()
    
    # Game operations
    async def get_all_games(self, active_only: bool = True) -> List[Game]:
        """Get all games"""
        async with self.get_session() as session:
            query = select(Game)
            if active_only:
                query = query.where(Game.is_active == True)
            query = query.order_by(Game.name)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_game_by_name(self, name: str) -> Optional[Game]:
        """Get a game by name (case insensitive)"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Game).where(func.lower(Game.name) == func.lower(name))
            )
            return result.scalar_one_or_none()
    
    # Challenge operations
    async def create_challenge(self, challenger_id: int, challenged_id: int, 
                             event_id: int, **kwargs) -> Challenge:
        """Create a new challenge"""
        async with self.get_session() as session:
            # Get a default game_id for legacy compatibility
            games = await self.get_all_games()
            default_game_id = games[0].id if games else 1
            
            challenge = Challenge(
                challenger_id=challenger_id,
                challenged_id=challenged_id,
                event_id=event_id,
                game_id=default_game_id,  # Legacy compatibility
                **kwargs
            )
            session.add(challenge)
            await session.commit()
            await session.refresh(challenge)
            return challenge
    
    async def get_challenge_by_id(self, challenge_id: int) -> Optional[Challenge]:
        """Get a challenge by ID with related data"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Challenge)
                .options(
                    selectinload(Challenge.challenger),
                    selectinload(Challenge.challenged),
                    selectinload(Challenge.event)
                )
                .where(Challenge.id == challenge_id)
            )
            return result.scalar_one_or_none()
    
    async def get_active_challenges_for_player(self, player_id: int) -> List[Challenge]:
        """Get all active challenges for a player (sent or received)"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Challenge)
                .options(
                    selectinload(Challenge.challenger),
                    selectinload(Challenge.challenged),
                    selectinload(Challenge.event)
                )
                .where(
                    ((Challenge.challenger_id == player_id) | (Challenge.challenged_id == player_id)) &
                    (Challenge.status.in_([ChallengeStatus.PENDING, ChallengeStatus.ACCEPTED]))
                )
                .order_by(Challenge.created_at.desc())
            )
            return result.scalars().all()
    
    async def update_challenge_status(self, challenge_id: int, status: str, **kwargs):
        """Update a challenge's status and other fields"""
        async with self.get_session() as session:
            update_data = {'status': status, **kwargs}
            await session.execute(
                update(Challenge)
                .where(Challenge.id == challenge_id)
                .values(**update_data)
            )
            await session.commit()
    
    # Elo and ticket operations
    async def add_ticket_transaction(self, player_id: int, amount: int, 
                                   transaction_type: str, **kwargs):
        """Add a ticket transaction"""
        async with self.get_session() as session:
            ticket = Ticket(
                player_id=player_id,
                amount=amount,
                transaction_type=transaction_type,
                **kwargs
            )
            session.add(ticket)
            
            # Update player's ticket count
            await session.execute(
                update(Player)
                .where(Player.id == player_id)
                .values(tickets=Player.tickets + amount)
            )
            
            await session.commit()
    
    async def get_player_stats(self, player_id: int) -> dict:
        """Get comprehensive stats for a player"""
        async with self.get_session() as session:
            # Get player
            player_result = await session.execute(
                select(Player).where(Player.id == player_id)
            )
            player = player_result.scalar_one_or_none()
            
            if not player:
                return None
            
            # Get recent matches
            recent_matches_result = await session.execute(
                select(Challenge)
                .options(
                    selectinload(Challenge.challenger),
                    selectinload(Challenge.challenged),
                    selectinload(Challenge.event)
                )
                .where(
                    ((Challenge.challenger_id == player_id) | (Challenge.challenged_id == player_id)) &
                    (Challenge.status == ChallengeStatus.COMPLETED)
                )
                .order_by(Challenge.completed_at.desc())
                .limit(10)
            )
            recent_matches = recent_matches_result.scalars().all()
            
            # Get Elo history
            elo_history_result = await session.execute(
                select(EloHistory)
                .where(EloHistory.player_id == player_id)
                .order_by(EloHistory.recorded_at.desc())
                .limit(20)
            )
            elo_history = elo_history_result.scalars().all()
            
            return {
                'player': player,
                'recent_matches': recent_matches,
                'elo_history': elo_history
            }
    
    async def clear_clusters_and_events(self, session):
        """Clear all existing clusters and events for clean import"""
        from sqlalchemy import delete
        
        self.logger.info("Clearing existing clusters and events...")
        
        # Delete events first (foreign key constraint)
        await session.execute(delete(Event))
        await session.execute(delete(Cluster))
        await session.flush()
        
        self.logger.info("Existing data cleared successfully")

    async def import_clusters_and_events_from_csv(self, session, clear_existing: bool = True):
        """
        Import clusters and events from CSV file with enhanced parsing.
        
        Uses the same parsing logic as populate_from_csv.py to handle complex
        scoring types, event name suffixes, and score direction inference.
        
        Args:
            session: Database session
            clear_existing: Whether to clear existing data before import
        """
        csv_path = "LB Culling Games List.csv"
        
        if not os.path.exists(csv_path):
            self.logger.error(f"CSV file not found: {csv_path}")
            return
        
        # Import parsing functions
        try:
            from populate_from_csv import parse_scoring_types, create_event_name_with_suffix, infer_score_direction
        except ImportError:
            self.logger.error("Could not import parsing functions from populate_from_csv.py")
            # Fall back to basic parsing if populate_from_csv.py not available
            return await self._import_clusters_and_events_basic(session)
        
        # Clear existing data if requested
        if clear_existing:
            await self.clear_clusters_and_events(session)
        
        clusters_created = {}
        events_created = 0
        events_skipped = 0
        current_cluster = None
        event_name_counts = {}
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                for row_num, row in enumerate(reader, start=2):
                    cluster_number = row.get('Cluster Number', '').strip()
                    cluster_name = row.get('Cluster', '').strip()
                    event_name = row.get('Game Mode', '').strip()
                    scoring_type = row.get('Scoring Type', '').strip()
                    notes = row.get('Notes', '').strip()
                    
                    # Skip empty rows
                    if not event_name or not scoring_type:
                        continue
                    
                    # Handle cluster creation
                    if cluster_number and cluster_name:
                        try:
                            cluster_num = int(cluster_number)
                            if cluster_num not in clusters_created:
                                cluster = Cluster(
                                    number=cluster_num,
                                    name=cluster_name,
                                    is_active=True
                                )
                                session.add(cluster)
                                await session.flush()  # Get the ID
                                clusters_created[cluster_num] = cluster
                                current_cluster = cluster
                                self.logger.info(f"Created cluster {cluster_num}: {cluster_name}")
                        except ValueError:
                            self.logger.warning(f"Line {row_num}: Invalid cluster number: {cluster_number}")
                            continue
                    
                    # Use current cluster if no cluster specified in this row
                    if current_cluster is None:
                        self.logger.warning(f"Line {row_num}: No cluster defined for event: {event_name}")
                        continue
                    
                    # Parse scoring types using enhanced parser
                    parsed_scoring_types = parse_scoring_types(scoring_type)
                    if not parsed_scoring_types:
                        self.logger.warning(f"Line {row_num}: No valid scoring types for event '{event_name}', skipping")
                        events_skipped += 1
                        continue
                    
                    # Create events for each scoring type
                    for normalized_scoring_type in parsed_scoring_types:
                        # Track duplicates for naming
                        base_name = event_name
                        event_name_counts[base_name] = event_name_counts.get(base_name, 0) + 1
                        is_duplicate = len(parsed_scoring_types) > 1 or event_name_counts[base_name] > 1
                        
                        # Create event name with suffix
                        final_event_name = create_event_name_with_suffix(
                            base_name, normalized_scoring_type, is_duplicate
                        )
                        
                        # Set player limits based on scoring type
                        if normalized_scoring_type == '1v1':
                            min_players, max_players = 2, 2
                        elif normalized_scoring_type == 'Team':
                            min_players, max_players = 4, 10
                        elif normalized_scoring_type in ['FFA', 'Leaderboard']:
                            min_players, max_players = 3, 16
                        else:
                            min_players, max_players = 2, 8  # Default
                        
                        # Infer score direction for leaderboard events
                        score_direction = None
                        if normalized_scoring_type == 'Leaderboard':
                            score_direction = infer_score_direction(event_name, notes)
                        
                        # Create event
                        event = Event(
                            name=final_event_name,
                            cluster_id=current_cluster.id,
                            scoring_type=normalized_scoring_type,
                            score_direction=score_direction,
                            crownslayer_pool=300,
                            is_active=True,
                            allow_challenges=True,
                            min_players=min_players,
                            max_players=max_players
                        )
                        
                        session.add(event)
                        events_created += 1
                        
                        self.logger.debug(
                            f"Created event: {final_event_name} "
                            f"({normalized_scoring_type}, cluster: {current_cluster.name})"
                            f"{f', direction: {score_direction}' if score_direction else ''}"
                        )
                
                await session.commit()
                self.logger.info(
                    f"Successfully imported {len(clusters_created)} clusters and {events_created} events "
                    f"({events_skipped} events skipped)"
                )
                
        except Exception as e:
            self.logger.error(f"Error importing CSV data: {e}")
            await session.rollback()
            raise

    async def _import_clusters_and_events_basic(self, session):
        """Fallback basic import method (original implementation)"""
        csv_path = "LB Culling Games List.csv"
        
        # Valid scoring types for validation
        VALID_SCORING_TYPES = {'1v1', 'FFA', 'Team', 'Leaderboard'}
        
        clusters_created = {}
        events_created = 0
        current_cluster = None
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                for row in reader:
                    cluster_number = row.get('Cluster Number', '').strip()
                    cluster_name = row.get('Cluster', '').strip()
                    event_name = row.get('Game Mode', '').strip()
                    scoring_type = row.get('Scoring Type', '').strip()
                    
                    # Skip empty or invalid rows
                    if not event_name or not scoring_type:
                        continue
                    
                    # Handle cluster creation
                    if cluster_number and cluster_name:
                        # New cluster
                        try:
                            cluster_num = int(cluster_number)
                            if cluster_num not in clusters_created:
                                cluster = Cluster(
                                    number=cluster_num,
                                    name=cluster_name,
                                    is_active=True
                                )
                                session.add(cluster)
                                await session.flush()  # Get the ID
                                clusters_created[cluster_num] = cluster
                                current_cluster = cluster
                                self.logger.info(f"Created cluster {cluster_num}: {cluster_name}")
                        except ValueError:
                            self.logger.warning(f"Invalid cluster number: {cluster_number}")
                            continue
                    
                    # Use current cluster if no cluster specified in this row
                    if current_cluster is None:
                        self.logger.warning(f"No cluster defined for event: {event_name}")
                        continue
                    
                    # Create event
                    # Handle multiple scoring types (e.g., "1v1/FFA")
                    primary_scoring_type = scoring_type.split('/')[0]
                    
                    # Validate scoring type
                    if primary_scoring_type not in VALID_SCORING_TYPES:
                        self.logger.warning(f"Invalid scoring type '{primary_scoring_type}' for event '{event_name}', skipping")
                        continue
                    
                    event = Event(
                        name=event_name,
                        cluster_id=current_cluster.id,
                        scoring_type=primary_scoring_type,
                        crownslayer_pool=300,
                        is_active=True,
                        allow_challenges=True
                    )
                    
                    # Set appropriate player limits based on scoring type
                    if primary_scoring_type == '1v1':
                        event.min_players = 2
                        event.max_players = 2
                    elif primary_scoring_type == 'Team':
                        event.min_players = 4
                        event.max_players = 10
                    elif primary_scoring_type in ['FFA', 'Leaderboard']:
                        event.min_players = 3
                        event.max_players = 16
                    
                    session.add(event)
                    events_created += 1
                    self.logger.debug(f"Created event: {event_name} ({primary_scoring_type})")
                
                await session.commit()
                self.logger.info(f"Successfully imported {len(clusters_created)} clusters and {events_created} events")
                
        except Exception as e:
            self.logger.error(f"Error importing CSV data: {e}")
            await session.rollback()
            raise
    
    # Cluster operations
    async def get_all_clusters(self, active_only: bool = True) -> List[Cluster]:
        """Get all clusters with their events"""
        async with self.get_session() as session:
            query = select(Cluster).options(selectinload(Cluster.events))
            if active_only:
                query = query.where(Cluster.is_active == True)
            query = query.order_by(Cluster.number)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_cluster_by_id(self, cluster_id: int) -> Optional[Cluster]:
        """Get a cluster by ID with its events"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Cluster)
                .options(selectinload(Cluster.events))
                .where(Cluster.id == cluster_id)
            )
            return result.scalar_one_or_none()
    
    async def get_cluster_by_name(self, name: str) -> Optional[Cluster]:
        """Get a cluster by name (case insensitive)"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Cluster).where(func.lower(Cluster.name) == func.lower(name))
            )
            return result.scalar_one_or_none()
    
    # Event operations
    async def get_all_events(self, cluster_id: Optional[int] = None, active_only: bool = True) -> List[Event]:
        """Get all events, optionally filtered by cluster"""
        async with self.get_session() as session:
            query = select(Event).options(selectinload(Event.cluster))
            
            if cluster_id:
                query = query.where(Event.cluster_id == cluster_id)
            if active_only:
                query = query.where(Event.is_active == True)
            
            query = query.order_by(Event.cluster_id, Event.name)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_event_by_id(self, event_id: int) -> Optional[Event]:
        """Get an event by ID with its cluster"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Event)
                .options(selectinload(Event.cluster))
                .where(Event.id == event_id)
            )
            return result.scalar_one_or_none()
    
    async def get_event_by_name(self, name: str, cluster_id: Optional[int] = None) -> Optional[Event]:
        """Get an event by name (case insensitive), optionally within a specific cluster"""
        async with self.get_session() as session:
            query = select(Event).options(selectinload(Event.cluster)).where(
                func.lower(Event.name) == func.lower(name)
            )
            
            if cluster_id:
                query = query.where(Event.cluster_id == cluster_id)
            
            result = await session.execute(query)
            return result.scalar_one_or_none()
    
    async def get_event_for_challenge(self, event_name: str, cluster_id: Optional[int] = None) -> Optional[Event]:
        """Get an event suitable for challenges (helper method for backwards compatibility)"""
        return await self.get_event_by_name(event_name, cluster_id)
    
    # ============================================================================
    # Phase 1.5: UI Aggregation Operations
    # ============================================================================
    
    async def get_aggregated_events(self, cluster_id: Optional[int] = None, active_only: bool = True) -> List[dict]:
        """Get events aggregated by base_event_name for UI display"""
        async with self.get_session() as session:
            # Build base query
            query = select(
                Event.base_event_name,
                func.count(Event.id).label('variation_count'),
                func.group_concat(Event.supported_scoring_types, ', ').label('scoring_types'),
                func.min(Event.id).label('primary_event_id'),
                Event.cluster_id
            ).group_by(Event.base_event_name, Event.cluster_id)
            
            # Apply filters
            if cluster_id:
                query = query.where(Event.cluster_id == cluster_id)
            if active_only:
                query = query.where(Event.is_active == True)
            
            # Filter out events without base_event_name
            query = query.where(Event.base_event_name.isnot(None))
            
            # Order by cluster and base name
            query = query.order_by(Event.cluster_id, Event.base_event_name)
            
            result = await session.execute(query)
            rows = result.all()
            
            # Convert to dictionaries with cluster info
            aggregated = []
            for row in rows:
                # Get cluster info for the primary event
                cluster_result = await session.execute(
                    select(Cluster).where(Cluster.id == row.cluster_id)
                )
                cluster = cluster_result.scalar_one_or_none()
                
                aggregated.append({
                    'base_event_name': row.base_event_name,
                    'variation_count': row.variation_count,
                    'scoring_types': row.scoring_types,
                    'primary_event_id': row.primary_event_id,
                    'cluster': cluster,
                    'cluster_name': cluster.name if cluster else 'Unknown'
                })
            
            return aggregated
    
    async def get_events_by_base_name(self, base_event_name: str, cluster_id: Optional[int] = None) -> List[Event]:
        """Get all event variations for a specific base event name"""
        async with self.get_session() as session:
            query = select(Event).options(selectinload(Event.cluster))
            query = query.where(Event.base_event_name == base_event_name)
            
            if cluster_id:
                query = query.where(Event.cluster_id == cluster_id)
            
            query = query.order_by(Event.name)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    # ============================================================================
    # Phase 1.1: PlayerEventStats Operations
    # ============================================================================
    
    async def get_or_create_player_event_stats(self, player_id: int, event_id: int, session: AsyncSession) -> PlayerEventStats:
        """Get or create PlayerEventStats for a player in an event (session-aware)"""
        # Try to get existing stats with a lock to prevent race conditions
        # NOTE: On SQLite, with_for_update() relies on the database-level write lock,
        # not true row-level locking. This is safe for atomicity but may limit
        # write concurrency as the application scales.
        result = await session.execute(
            select(PlayerEventStats).where(
                (PlayerEventStats.player_id == player_id) &
                (PlayerEventStats.event_id == event_id)
            ).with_for_update()
        )
        stats = result.scalar_one_or_none()
        
        if stats is None:
            # Create new stats with default values
            stats = PlayerEventStats(
                player_id=player_id,
                event_id=event_id,
                raw_elo=Config.STARTING_ELO,
                scoring_elo=Config.STARTING_ELO
            )
            session.add(stats)
            await session.flush()  # Use flush to get ID, let caller handle commit
            await session.refresh(stats)
        
        return stats
    
    async def get_or_create_player_event_stats_legacy(self, player_id: int, event_id: int) -> PlayerEventStats:
        """Legacy wrapper for backward compatibility - creates own transaction"""
        async with self.transaction() as session:
            return await self.get_or_create_player_event_stats(player_id, event_id, session)
    
    async def bulk_get_or_create_player_event_stats(self, player_ids: list[int], event_id: int, session: AsyncSession) -> dict[int, PlayerEventStats]:
        """
        Bulk get or create PlayerEventStats for multiple players in an event.
        
        Args:
            player_ids: List of player IDs to fetch/create stats for
            event_id: Event ID for the stats
            session: Database session for the operation
            
        Returns:
            Dict mapping player_id to PlayerEventStats object
        """
        # First, fetch all existing stats in one query
        existing_stats_query = select(PlayerEventStats).where(
            PlayerEventStats.player_id.in_(player_ids),
            PlayerEventStats.event_id == event_id
        ).with_for_update()
        
        result = await session.execute(existing_stats_query)
        existing_stats = result.scalars().all()
        
        # Create lookup dict
        stats_dict = {stats.player_id: stats for stats in existing_stats}
        
        # Identify missing players and create their stats
        existing_player_ids = set(stats_dict.keys())
        missing_player_ids = set(player_ids) - existing_player_ids
        
        for player_id in missing_player_ids:
            new_stats = PlayerEventStats(
                player_id=player_id,
                event_id=event_id,
                raw_elo=Config.STARTING_ELO,
                scoring_elo=Config.STARTING_ELO
            )
            session.add(new_stats)
            stats_dict[player_id] = new_stats
        
        # Flush to get IDs for new stats
        if missing_player_ids:
            await session.flush()
            # Refresh new stats to get their IDs
            for player_id in missing_player_ids:
                await session.refresh(stats_dict[player_id])
        
        return stats_dict
    
    async def update_event_elo(self, player_id: int, event_id: int, new_raw_elo: int, 
                              session: AsyncSession, match_result: MatchResult,
                              match_id: Optional[int] = None, challenge_id: Optional[int] = None) -> PlayerEventStats:
        """Update a player's Elo rating for a specific event (session-aware)"""
        # Get existing stats
        stats = await self.get_or_create_player_event_stats(player_id, event_id, session)
        
        # Update stats
        old_elo = stats.raw_elo
        stats.raw_elo = new_raw_elo
        # Remove manual scoring_elo calculation - handled by SQLAlchemy event listener
        
        # Record in EloHistory with CRITICAL event context
        elo_history = EloHistory(
            player_id=player_id,
            event_id=event_id,  # CRITICAL: Add event context for per-event audit trail
            old_elo=old_elo,
            new_elo=new_raw_elo,
            elo_change=new_raw_elo - old_elo,
            match_id=match_id,
            challenge_id=challenge_id,
            k_factor=stats.k_factor,
            match_result=match_result  # Accept as parameter - business logic moved to caller
        )
        
        session.add(elo_history)
        await session.flush()  # Use flush to get IDs, let caller handle commit
        await session.refresh(stats)
        
        return stats
    
    async def update_event_elo_legacy(self, player_id: int, event_id: int, new_raw_elo: int, 
                                     match_id: Optional[int] = None, challenge_id: Optional[int] = None) -> PlayerEventStats:
        """Legacy wrapper for backward compatibility - creates own transaction"""
        # Determine match result based on Elo change (simplified business logic)
        async with self.transaction() as session:
            # Get current stats to determine old Elo
            current_stats = await self.get_or_create_player_event_stats(player_id, event_id, session)
            old_elo = current_stats.raw_elo
            
            # Determine match result
            if new_raw_elo > old_elo:
                match_result = MatchResult.WIN
            elif new_raw_elo < old_elo:
                match_result = MatchResult.LOSS
            else:
                match_result = MatchResult.DRAW
            
            return await self.update_event_elo(
                player_id, event_id, new_raw_elo, session, match_result, match_id, challenge_id
            )
    
    async def get_event_leaderboard(self, event_id: int, scoring_type: str, limit: int = 20) -> List[PlayerEventStats]:
        """Get leaderboard for a specific event"""
        async with self.get_session() as session:
            # Use scoring_elo for display rankings
            query = select(PlayerEventStats).options(
                selectinload(PlayerEventStats.player)
            ).where(
                PlayerEventStats.event_id == event_id
            ).order_by(PlayerEventStats.scoring_elo.desc()).limit(limit)
            
            result = await session.execute(query)
            return result.scalars().all()
    
    async def get_player_event_stats(self, player_id: int, event_id: int) -> Optional[PlayerEventStats]:
        """Get PlayerEventStats for a specific player and event"""
        async with self.get_session() as session:
            result = await session.execute(
                select(PlayerEventStats).options(
                    selectinload(PlayerEventStats.player),
                    selectinload(PlayerEventStats.event)
                ).where(
                    (PlayerEventStats.player_id == player_id) &
                    (PlayerEventStats.event_id == event_id)
                )
            )
            return result.scalar_one_or_none()
    
    async def get_player_cluster_stats(self, player_id: int, cluster_id: int) -> List[PlayerEventStats]:
        """Get all PlayerEventStats for a player in a specific cluster"""
        async with self.get_session() as session:
            result = await session.execute(
                select(PlayerEventStats).options(
                    selectinload(PlayerEventStats.event)
                ).join(Event).where(
                    (PlayerEventStats.player_id == player_id) &
                    (Event.cluster_id == cluster_id)
                ).order_by(PlayerEventStats.scoring_elo.desc())
            )
            return result.scalars().all()
    
    async def get_comprehensive_player_stats(self, player_id: int) -> dict:
        """Get comprehensive stats for a player across all events and clusters"""
        async with self.get_session() as session:
            # Get player
            player_result = await session.execute(
                select(Player).options(
                    selectinload(Player.event_stats).selectinload(PlayerEventStats.event).selectinload(Event.cluster)
                ).where(Player.id == player_id)
            )
            player = player_result.scalar_one_or_none()
            
            if not player:
                return None
            
            # Organize stats by cluster
            cluster_stats = {}
            total_events = len(player.event_stats)
            
            for event_stat in player.event_stats:
                cluster_name = event_stat.event.cluster.name
                if cluster_name not in cluster_stats:
                    cluster_stats[cluster_name] = []
                cluster_stats[cluster_name].append(event_stat)
            
            return {
                'player': player,
                'total_events': total_events,
                'cluster_stats': cluster_stats,
                'event_stats': player.event_stats
            }
    
    # ============================================================================
    # Phase 1.1: TicketLedger Operations
    # ============================================================================
    
    async def add_ticket_transaction_atomic(self, player_id: int, amount: int, reason: str, 
                                           session: AsyncSession,
                                           match_id: Optional[int] = None, challenge_id: Optional[int] = None,
                                           admin_user_id: Optional[int] = None) -> TicketLedger:
        """
        Add a ticket transaction with atomic balance tracking (session-aware).
        
        This method ensures atomic ticket balance updates using SELECT FOR UPDATE
        to prevent race conditions in the ticket economy.
        """
        # Lock the player record for atomic balance update
        player_result = await session.execute(
            select(Player).where(Player.id == player_id).with_for_update()
        )
        player = player_result.scalar_one()
        
        # Calculate new balance
        new_balance = player.tickets + amount
        
        # Prevent negative balances for spending transactions
        if new_balance < 0 and amount < 0:
            raise ValueError(f"Insufficient tickets. Current: {player.tickets}, Attempted: {amount}")
        
        # Update player's ticket cache
        player.tickets = new_balance
        
        # Create ledger entry
        ledger_entry = TicketLedger(
            player_id=player_id,
            change_amount=amount,
            reason=reason,
            balance_after=new_balance,
            related_match_id=match_id,
            related_challenge_id=challenge_id,
            admin_user_id=admin_user_id
        )
        
        session.add(ledger_entry)
        await session.flush()  # Use flush to get ID, let caller handle commit
        await session.refresh(ledger_entry)
        
        return ledger_entry
    
    async def add_ticket_transaction_atomic_legacy(self, player_id: int, amount: int, reason: str, 
                                                  match_id: Optional[int] = None, challenge_id: Optional[int] = None,
                                                  admin_user_id: Optional[int] = None) -> TicketLedger:
        """Legacy wrapper for backward compatibility - creates own transaction"""
        async with self.transaction() as session:
            return await self.add_ticket_transaction_atomic(
                player_id, amount, reason, session, match_id, challenge_id, admin_user_id
            )
    
    async def get_player_ticket_balance(self, player_id: int) -> int:
        """Get current ticket balance for a player (atomic query)"""
        async with self.get_session() as session:
            result = await session.execute(
                select(Player.tickets).where(Player.id == player_id)
            )
            balance = result.scalar_one_or_none()
            return balance if balance is not None else 0
    
    async def get_ticket_history(self, player_id: int, limit: int = 20) -> List[TicketLedger]:
        """Get ticket transaction history for a player"""
        async with self.get_session() as session:
            result = await session.execute(
                select(TicketLedger).options(
                    selectinload(TicketLedger.match),
                    selectinload(TicketLedger.challenge),
                    selectinload(TicketLedger.admin_user)
                ).where(
                    TicketLedger.player_id == player_id
                ).order_by(TicketLedger.timestamp.desc()).limit(limit)
            )
            return result.scalars().all()
    
    async def verify_ticket_balance_integrity(self, player_id: int) -> dict:
        """Verify ticket balance integrity by comparing cache with ledger"""
        async with self.get_session() as session:
            # Get player's cached balance
            player_result = await session.execute(
                select(Player.tickets).where(Player.id == player_id)
            )
            cached_balance = player_result.scalar_one_or_none() or 0
            
            # Calculate actual balance from ledger
            ledger_result = await session.execute(
                select(func.sum(TicketLedger.change_amount)).where(TicketLedger.player_id == player_id)
            )
            calculated_balance = ledger_result.scalar_one_or_none() or 0
            
            return {
                'player_id': player_id,
                'cached_balance': cached_balance,
                'calculated_balance': calculated_balance,
                'integrity_check': cached_balance == calculated_balance
            }