import asyncio
import time
import random
from bot.database.database import Database
from bot.database.models import Player, Event, Cluster, PlayerEventStats

async def test_metagame_fields():
    db = Database()
    await db.initialize()
    
    async with db.transaction() as session:
        # Create test player with unique discord_id
        base_discord_id = 700000000 + int(time.time() * 1000) % 1000000
        player = Player(
            discord_id=base_discord_id + random.randint(0, 999),
            username=f"MetaGamePlayer_{base_discord_id}"
        )
        session.add(player)
        await session.flush()
        
        # Use unique cluster number to avoid conflicts
        cluster_num = 80000 + int(time.time()) % 10000
        cluster = Cluster(number=cluster_num, name="Meta Test")
        session.add(cluster)
        await session.flush()
        
        event = Event(name="Meta Event", cluster_id=cluster.id)
        session.add(event)
        await session.flush()
        
        # Test meta-game fields
        stats = await db.get_or_create_player_event_stats(player.id, event.id, session)
        
        # Update meta-game fields
        stats.final_score = 1500
        stats.shard_bonus = 100
        stats.shop_bonus = 50
        
        await session.commit()
        
        # Verify
        loaded_stats = await db.get_or_create_player_event_stats(player.id, event.id, session)
        print(f"✓ Meta-game fields saved correctly:")
        print(f"  - Final Score: {loaded_stats.final_score}")
        print(f"  - Shard Bonus: {loaded_stats.shard_bonus}")
        print(f"  - Shop Bonus: {loaded_stats.shop_bonus}")
        
        assert loaded_stats.final_score == 1500
        assert loaded_stats.shard_bonus == 100
        assert loaded_stats.shop_bonus == 50

if __name__ == "__main__":
    asyncio.run(test_metagame_fields())