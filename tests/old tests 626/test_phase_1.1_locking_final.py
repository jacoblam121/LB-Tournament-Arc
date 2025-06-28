import asyncio
import time
import uuid
from sqlalchemy import select, update
from bot.database.database import Database
from bot.database.models import Player, Event, Cluster, PlayerEventStats

async def atomic_increment(db, player_id, event_id, increment_amount, task_id):
    """Perform atomic database-level increment - no race condition possible"""
    async with db.transaction() as session:
        # Use SQLAlchemy update() for true atomicity
        result = await session.execute(
            update(PlayerEventStats)
            .where(
                PlayerEventStats.player_id == player_id,
                PlayerEventStats.event_id == event_id
            )
            .values(
                raw_elo=PlayerEventStats.raw_elo + increment_amount,
                scoring_elo=PlayerEventStats.raw_elo + increment_amount
            )
            .returning(PlayerEventStats.raw_elo)
        )
        
        new_elo = result.scalar()
        print(f"Task {task_id}: Incremented Elo to {new_elo}")

async def test_atomic_locking():
    """Test SQLite locking with truly atomic database operations"""
    db = Database()
    await db.initialize()
    
    # Use UUID-based IDs for guaranteed uniqueness
    unique_suffix = uuid.uuid4().int & ((1 << 31) - 1)  # 31-bit positive int
    
    # Setup test data
    async with db.transaction() as session:
        cluster = Cluster(
            number=95000000 + unique_suffix, 
            name=f"Atomic Test {unique_suffix}"
        )
        session.add(cluster)
        await session.flush()
        
        event = Event(name="Atomic Locking Event", cluster_id=cluster.id)
        session.add(event)
        await session.flush()
        
        player = Player(
            discord_id=750000000000000000 + unique_suffix,
            username=f"AtomicTestPlayer_{unique_suffix}"
        )
        session.add(player)
        await session.flush()
        
        # Pre-create PlayerEventStats with known starting value
        stats = PlayerEventStats(
            player_id=player.id,
            event_id=event.id,
            raw_elo=1000,
            scoring_elo=1000
        )
        session.add(stats)
        await session.commit()
        
        player_id = player.id
        event_id = event.id
    
    print("Testing atomic database-level increments...")
    print("Each task will atomically increment Elo by 10")
    
    # Run 5 concurrent atomic updates
    increment_amount = 10
    num_tasks = 5
    tasks = [
        atomic_increment(db, player_id, event_id, increment_amount, i)
        for i in range(num_tasks)
    ]
    await asyncio.gather(*tasks)
    
    # Verify final result with direct query (no get_or_create)
    async with db.get_session() as session:
        result = await session.execute(
            select(PlayerEventStats).where(
                PlayerEventStats.player_id == player_id,
                PlayerEventStats.event_id == event_id
            )
        )
        stats = result.scalar_one()
        
        # Calculate expected value dynamically
        starting_elo = 1000
        expected_elo = starting_elo + (num_tasks * increment_amount)
        
        print(f"\n✓ Final Elo: {stats.raw_elo}")
        print(f"✓ Expected: {expected_elo}")
        
        assert stats.raw_elo == expected_elo, f"Expected {expected_elo}, got {stats.raw_elo}"
        print(f"✓ Atomic locking test PASSED - all {num_tasks} updates applied correctly!")

if __name__ == "__main__":
    asyncio.run(test_atomic_locking())