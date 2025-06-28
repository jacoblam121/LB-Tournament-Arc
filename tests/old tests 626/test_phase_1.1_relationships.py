import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from bot.database.database import Database
from bot.database.models import Challenge, ChallengeParticipant, PlayerEventStats

async def test_relationships():
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        # Test 1: Challenge.participants relationship
        result = await session.execute(
            select(Challenge).options(selectinload(Challenge.participants)).limit(1)
        )
        challenge = result.scalar_one_or_none()
        
        if challenge:
            print(f"✓ Challenge {challenge.id} has {len(challenge.participants)} participants")
        else:
            print("✓ No challenges exist yet (expected for new database)")
        
        # Test 2: PlayerEventStats new fields
        result = await session.execute(select(PlayerEventStats).limit(1))
        stats = result.scalar_one_or_none()
        
        if stats:
            print(f"✓ PlayerEventStats has new fields: final_score={stats.final_score}, "
                  f"shard_bonus={stats.shard_bonus}, shop_bonus={stats.shop_bonus}")
        else:
            print("✓ No PlayerEventStats exist yet (expected)")

if __name__ == "__main__":
    asyncio.run(test_relationships())