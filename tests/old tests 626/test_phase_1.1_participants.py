import asyncio
import time
import random
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from bot.database.database import Database
from bot.database.models import (
    Player, Event, Cluster, Challenge, ChallengeParticipant, 
    ChallengeStatus, ConfirmationStatus
)

async def test_challenge_participants():
    db = Database()
    await db.initialize()
    
    async with db.transaction() as session:
        # Create test data
        # Use unique cluster number to avoid conflicts
        cluster_num = 70000 + int(time.time()) % 10000
        cluster = Cluster(number=cluster_num, name=f"Participants Test {cluster_num}")
        session.add(cluster)
        await session.flush()
        
        event = Event(
            name="Test Event",
            cluster_id=cluster.id,
            scoring_type="FFA"
        )
        session.add(event)
        await session.flush()
        
        # Create test players with unique discord_ids
        # Use timestamp to ensure uniqueness across test runs
        base_discord_id = 900000000 + int(time.time() * 1000) % 1000000
        players = []
        for i in range(4):
            player = Player(
                discord_id=base_discord_id + i,  # Simple increment ensures uniqueness within test
                username=f"TestPlayer{i}_{base_discord_id}"
            )
            session.add(player)
            players.append(player)
        await session.flush()
        
        # Create FFA challenge
        # Note: Challenge model still requires challenger_id/challenged_id for backward compatibility
        # We'll use the first two players as legacy fields
        challenge = Challenge(
            challenger_id=players[0].id,
            challenged_id=players[1].id,
            event_id=event.id,
            status=ChallengeStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(hours=1)
        )
        session.add(challenge)
        await session.flush()
        
        # Add participants
        for i, player in enumerate(players):
            participant = ChallengeParticipant(
                challenge_id=challenge.id,
                player_id=player.id,
                status=ConfirmationStatus.PENDING,
                team_id="A" if i < 2 else "B"  # Team assignment for testing
            )
            session.add(participant)
        
        await session.commit()
        
        # Verify
        result = await session.execute(
            select(Challenge)
            .options(selectinload(Challenge.participants))
            .where(Challenge.id == challenge.id)
        )
        loaded_challenge = result.scalar_one()
        
        print(f"✓ Created FFA challenge with {len(loaded_challenge.participants)} participants")
        assert len(loaded_challenge.participants) == 4, f"Expected 4 participants, got {len(loaded_challenge.participants)}"
        
        for p in loaded_challenge.participants:
            print(f"  - Player {p.player_id}, Team {p.team_id}, Status: {p.status.value}")
            assert p.team_id in ["A", "B"], f"Invalid team_id: {p.team_id}"

if __name__ == "__main__":
    asyncio.run(test_challenge_participants())