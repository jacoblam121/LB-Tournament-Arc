import asyncio
import time
import random
from bot.database.database import Database
from bot.database.models import Player, Event, Cluster, PlayerEventStats

async def sequential_updates(db, player_id, event_id):
    """Test that updates are properly serialized by SQLite's database-level locking"""
    results = []
    
    async def update_task(task_id):
        async with db.transaction() as session:
            # Get or create stats
            stats = await db.get_or_create_player_event_stats(player_id, event_id, session)
            
            # Record the starting value
            start_elo = stats.raw_elo
            
            # Simulate some processing
            await asyncio.sleep(0.05)
            
            # Initialize raw_elo if None
            if stats.raw_elo is None:
                stats.raw_elo = 1000
            
            # Update Elo
            stats.raw_elo += 10
            stats.scoring_elo = max(stats.raw_elo, 1000)
            
            # Record result
            results.append((task_id, start_elo, stats.raw_elo))
            print(f"Task {task_id}: {start_elo} -> {stats.raw_elo}")
    
    # Run 5 concurrent tasks
    tasks = [update_task(i) for i in range(5)]
    await asyncio.gather(*tasks)
    
    return results

async def test_sqlite_locking():
    db = Database()
    await db.initialize()
    
    # Setup test data
    async with db.transaction() as session:
        # Use a unique cluster number based on timestamp to avoid conflicts
        cluster_num = 90000 + int(time.time()) % 10000
        cluster = Cluster(number=cluster_num, name="Locking Test")
        session.add(cluster)
        await session.flush()
        
        event = Event(name="Locking Event", cluster_id=cluster.id)
        session.add(event)
        await session.flush()
        
        # Use unique discord_id to avoid conflicts
        base_discord_id = 800000000 + int(time.time() * 1000) % 1000000
        player = Player(
            discord_id=base_discord_id, 
            username=f"LockTestPlayer_{base_discord_id}"
        )
        session.add(player)
        await session.flush()
        
        player_id = player.id
        event_id = event.id
    
    print("Testing SQLite database-level locking...")
    print("(Note: SQLite serializes all writes at the database level)")
    print()
    
    # Run the test
    results = await sequential_updates(db, player_id, event_id)
    
    # Verify results
    print("\nResults:")
    for task_id, start, end in results:
        print(f"  Task {task_id}: {start} -> {end}")
    
    # Check final value
    async with db.get_session() as session:
        stats = await db.get_or_create_player_event_stats(player_id, event_id, session)
        print(f"\n✓ Final Elo: {stats.raw_elo}")
        
        # With SQLite's database-level locking, all 5 updates should be serialized
        # Starting from 1000, each task adds 10, so final should be exactly 1050
        expected_elo = 1050
        assert stats.raw_elo == expected_elo, f"Expected {expected_elo}, got {stats.raw_elo}"
        print(f"✓ Locking worked correctly (value is the expected {expected_elo})")

if __name__ == "__main__":
    asyncio.run(test_sqlite_locking())