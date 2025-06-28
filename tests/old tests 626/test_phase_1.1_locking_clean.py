import asyncio
import time
import random
from bot.database.database import Database
from bot.database.models import Player, Event, Cluster, PlayerEventStats

async def concurrent_update(db, player_id, event_id, task_id):
    """Simulate concurrent Elo updates using the original simple design"""
    async with db.transaction() as session:
        stats = await db.get_or_create_player_event_stats(player_id, event_id, session)
        
        # Simulate some processing time
        await asyncio.sleep(0.1)
        
        # Update Elo - simple increment, let database handle locking
        old_elo = stats.raw_elo
        stats.raw_elo += 10
        stats.scoring_elo = max(stats.raw_elo, 1000)
        
        print(f"Task {task_id}: Updated Elo from {old_elo} to {stats.raw_elo}")

async def test_concurrent_updates():
    """Test SQLite's database-level locking with concurrent updates"""
    db = Database()
    await db.initialize()
    
    # Setup test data with unique IDs
    async with db.transaction() as session:
        # Use unique cluster number to avoid conflicts
        cluster_num = 95000 + int(time.time()) % 10000
        cluster = Cluster(number=cluster_num, name="Locking Test Clean")
        session.add(cluster)
        await session.flush()
        
        event = Event(name="Locking Event Clean", cluster_id=cluster.id)
        session.add(event)
        await session.flush()
        
        # Use unique discord_id to avoid conflicts  
        base_discord_id = 750000000 + int(time.time() * 1000) % 1000000
        player = Player(
            discord_id=base_discord_id,
            username=f"LockTestPlayer_{base_discord_id}"
        )
        session.add(player)
        await session.flush()
        
        player_id = player.id
        event_id = event.id
    
    # Run concurrent updates
    print("Running 5 concurrent updates...")
    print("Testing SQLite database-level locking...")
    tasks = [
        concurrent_update(db, player_id, event_id, i) 
        for i in range(5)
    ]
    await asyncio.gather(*tasks)
    
    # Verify final result
    async with db.get_session() as session:
        stats = await db.get_or_create_player_event_stats(player_id, event_id, session)
        print(f"\n✓ Final Elo: {stats.raw_elo}")
        
        # Should be exactly 1050 if SQLite locking worked correctly
        expected_elo = 1050
        assert stats.raw_elo == expected_elo, f"Expected {expected_elo}, got {stats.raw_elo}"
        print(f"✓ Locking worked correctly (value is the expected {expected_elo})")

if __name__ == "__main__":
    asyncio.run(test_concurrent_updates())