import asyncio
import csv
import os
from typing import Optional, List, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy import select, update, delete, func
from contextlib import asynccontextmanager

from bot.config import Config
from bot.database.models import Base, Player, Game, Challenge, Tournament, EloHistory, Ticket, ChallengeStatus, MatchResult, Cluster, Event
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
                self.logger.info("Initializing clusters and events from CSV...")
                await self.import_clusters_and_events_from_csv(session)
    
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
                             game_id: int, **kwargs) -> Challenge:
        """Create a new challenge"""
        async with self.get_session() as session:
            challenge = Challenge(
                challenger_id=challenger_id,
                challenged_id=challenged_id,
                game_id=game_id,
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
                    selectinload(Challenge.game)
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
                    selectinload(Challenge.game)
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
    async def record_elo_change(self, player_id: int, old_elo: int, new_elo: int,
                               challenge_id: int, opponent_id: int, result: MatchResult, k_factor: int):
        """Record an Elo rating change"""
        async with self.get_session() as session:
            elo_history = EloHistory(
                player_id=player_id,
                old_elo=old_elo,
                new_elo=new_elo,
                elo_change=new_elo - old_elo,
                challenge_id=challenge_id,
                opponent_id=opponent_id,
                match_result=result,
                k_factor=k_factor
            )
            session.add(elo_history)
            await session.commit()
    
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
                    selectinload(Challenge.game)
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
    
    async def import_clusters_and_events_from_csv(self, session):
        """Import clusters and events from CSV file"""
        csv_path = "LB Culling Games List.csv"
        
        if not os.path.exists(csv_path):
            self.logger.error(f"CSV file not found: {csv_path}")
            return
        
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
        """Get all clusters"""
        async with self.get_session() as session:
            query = select(Cluster)
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