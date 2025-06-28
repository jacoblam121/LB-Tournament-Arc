import asyncio
from bot.database.database import Database
from bot.database.models import Player, Event, Cluster, PlayerEventStats

async def concurrent_update(db, player_id, event_id, task_id):
    """Simulate concurrent Elo updates"""
    try:
        async with db.transaction() as session:
            stats = await db.get_or_create_player_event_stats(player_id, event_id, session)
            
            # Simulate some processing time
            await asyncio.sleep(0.1)
            
            # Update Elo
            old_elo = stats.raw_elo
            stats.raw_elo += 10
            stats.scoring_elo = max(stats.raw_elo, 1000)
            
            print(f"Task {task_id}: Updated Elo from {old_elo} to {stats.raw_elo}")
    except Exception as e:
        print(f"Task {task_id}: Failed with error: {type(e).__name__}")

async def test_concurrent_updates():
    db = Database()
    await db.initialize()
    
    # Setup test data
    async with db.transaction() as session:
        cluster = Cluster(number=98, name="Locking Test")
        session.add(cluster)
        await session.flush()
        
        event = Event(name="Locking Event", cluster_id=cluster.id)
        session.add(event)
        await session.flush()
        
        player = Player(discord_id=800000, username="LockTestPlayer")
        session.add(player)
        await session.flush()
        
        player_id = player.id
        event_id = event.id
    
    # Run concurrent updates
    print("Running 5 concurrent updates...")
    tasks = [
        concurrent_update(db, player_id, event_id, i) 
        for i in range(5)
    ]
    await asyncio.gather(*tasks)
    
    # Verify final result
    async with db.get_session() as session:
        stats = await db.get_or_create_player_event_stats(player_id, event_id, session)
        print(f"✓ Final Elo: {stats.raw_elo} (expected: 1050)")
        assert stats.raw_elo == 1050, f"Expected 1050, got {stats.raw_elo}"

if __name__ == "__main__":
    asyncio.run(test_concurrent_updates())