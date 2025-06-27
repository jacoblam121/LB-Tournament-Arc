#!/usr/bin/env python3
"""
Phase B Confirmation System Test Suite

This test suite validates the confirmation system infrastructure including:
- New models and enums
- Migration execution
- MatchOperations confirmation methods
- Edge cases and error handling

Run this after executing the migration script.
"""

import asyncio
import json
from datetime import datetime, timedelta
from sqlalchemy import text
from bot.database.database import Database
from bot.database.models import (
    Match, MatchParticipant, MatchStatus, MatchFormat,
    ConfirmationStatus, MatchResultProposal, MatchConfirmation,
    Player, Event, Cluster
)
from bot.database.match_operations import MatchOperations
from bot.operations.player_operations import PlayerOperations
from bot.operations.event_operations import EventOperations


class TestPhaseB:
    """Test suite for Phase B confirmation system"""
    
    def __init__(self):
        self.db = Database()
        self.match_ops = None
        self.player_ops = None
        self.event_ops = None
        self.test_players = []
        self.test_event = None
        self.test_match = None
        
    async def setup(self):
        """Initialize database and operations"""
        print("🔧 Setting up test environment...")
        await self.db.initialize()
        
        self.match_ops = MatchOperations(self.db)
        self.player_ops = PlayerOperations(self.db)
        self.event_ops = EventOperations(self.db)
        
        # Create test data
        await self._create_test_data()
        print("✅ Test environment ready")
    
    async def teardown(self):
        """Clean up test data"""
        print("\n🧹 Cleaning up test data...")
        
        async with self.db.get_session() as session:
            # Clean up in reverse order of dependencies
            if self.test_match:
                # Delete confirmations
                await session.execute(
                    text("DELETE FROM match_confirmations WHERE match_id = :match_id"),
                    {"match_id": self.test_match.id}
                )
                # Delete proposals
                await session.execute(
                    text("DELETE FROM match_result_proposals WHERE match_id = :match_id"),
                    {"match_id": self.test_match.id}
                )
                # Delete participants
                await session.execute(
                    text("DELETE FROM match_participants WHERE match_id = :match_id"),
                    {"match_id": self.test_match.id}
                )
                # Delete match
                await session.execute(
                    text("DELETE FROM matches WHERE id = :id"),
                    {"id": self.test_match.id}
                )
            
            # Delete test players
            for player in self.test_players:
                await session.execute(
                    text("DELETE FROM players WHERE id = :id"),
                    {"id": player.id}
                )
            
            # Delete test event
            if self.test_event:
                await session.execute(
                    text("DELETE FROM events WHERE id = :id"),
                    {"id": self.test_event.id}
                )
            
            await session.commit()
        
        await self.db.close()
        print("✅ Cleanup complete")
    
    async def _create_test_data(self):
        """Create test players, event, and match"""
        # Create test players
        for i in range(4):
            player = await self.db.create_player(
                discord_id=900000 + i,
                username=f"testplayer{i}",
                display_name=f"Test Player {i}"
            )
            self.test_players.append(player)
        
        # Create test event
        self.test_event = await self.event_ops.create_ffa_event(
            participant_count=4,
            event_name_suffix="Phase B Test"
        )
        
        # Create test match
        player_ids = [p.id for p in self.test_players]
        self.test_match = await self.match_ops.create_ffa_match(
            event_id=self.test_event.id,
            participant_ids=player_ids,
            created_by_id=player_ids[0]
        )
    
    async def test_1_model_creation(self):
        """Test that new models and enums are properly created"""
        print("\n📋 Test 1: Model Creation")
        
        try:
            # Test enum values
            assert hasattr(MatchStatus, 'AWAITING_CONFIRMATION'), "MatchStatus missing AWAITING_CONFIRMATION"
            assert MatchStatus.AWAITING_CONFIRMATION.value == "awaiting_confirmation"
            
            # Test ConfirmationStatus enum
            assert hasattr(ConfirmationStatus, 'PENDING')
            assert hasattr(ConfirmationStatus, 'CONFIRMED')
            assert hasattr(ConfirmationStatus, 'REJECTED')
            
            # Test model imports
            from bot.database.models import MatchResultProposal, MatchConfirmation
            
            print("✅ All models and enums created successfully")
            return True
            
        except Exception as e:
            print(f"❌ Model creation test failed: {e}")
            return False
    
    async def test_2_create_proposal(self):
        """Test creating a result proposal"""
        print("\n📋 Test 2: Create Result Proposal")
        
        try:
            # Prepare results
            results = [
                {"player_id": self.test_players[0].id, "placement": 1},
                {"player_id": self.test_players[1].id, "placement": 2},
                {"player_id": self.test_players[2].id, "placement": 3},
                {"player_id": self.test_players[3].id, "placement": 4}
            ]
            
            # Create proposal
            proposal = await self.match_ops.create_result_proposal(
                match_id=self.test_match.id,
                proposer_id=self.test_players[0].id,
                results=results,
                expires_in_hours=24
            )
            
            # Verify proposal
            assert proposal.match_id == self.test_match.id
            assert proposal.proposer_id == self.test_players[0].id
            assert proposal.is_active == True
            assert json.loads(proposal.proposed_results) == results
            
            # Verify match status changed
            async with self.db.get_session() as session:
                match = await session.get(Match, self.test_match.id)
                assert match.status == MatchStatus.AWAITING_CONFIRMATION
            
            # Verify confirmations created
            all_confirmed, confirmations = await self.match_ops.check_all_confirmed(self.test_match.id)
            assert len(confirmations) == 4
            
            # Verify proposer auto-confirmed
            proposer_confirmation = next(
                c for c in confirmations 
                if c.player_id == self.test_players[0].id
            )
            assert proposer_confirmation.status == ConfirmationStatus.CONFIRMED
            
            print("✅ Proposal created successfully with auto-confirmation")
            return True
            
        except Exception as e:
            print(f"❌ Create proposal test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_3_duplicate_proposal(self):
        """Test that duplicate proposals are rejected based on match status"""
        print("\n📋 Test 3: Duplicate Proposal Prevention")
        
        try:
            # Try to create another proposal (should fail because match is AWAITING_CONFIRMATION)
            results = [
                {"player_id": self.test_players[0].id, "placement": 2},
                {"player_id": self.test_players[1].id, "placement": 1}
            ]
            
            try:
                await self.match_ops.create_result_proposal(
                    match_id=self.test_match.id,
                    proposer_id=self.test_players[1].id,
                    results=results
                )
                print("❌ Duplicate proposal was allowed!")
                return False
            except Exception as e:
                if "not in PENDING status" in str(e):
                    print("✅ Duplicate proposal correctly rejected (match not PENDING)")
                    return True
                else:
                    raise
                    
        except Exception as e:
            print(f"❌ Duplicate proposal test failed: {e}")
            return False
    
    async def test_4_record_confirmation(self):
        """Test recording player confirmations"""
        print("\n📋 Test 4: Record Confirmations")
        
        try:
            # Player 1 confirms (should fail - already auto-confirmed)
            try:
                await self.match_ops.record_confirmation(
                    match_id=self.test_match.id,
                    player_id=self.test_players[0].id,
                    status=ConfirmationStatus.CONFIRMED
                )
                print("❌ Allowed double confirmation!")
                return False
            except Exception as e:
                if "already responded" in str(e):
                    print("✅ Double confirmation correctly prevented")
                else:
                    raise
            
            # Player 2 confirms
            confirmation = await self.match_ops.record_confirmation(
                match_id=self.test_match.id,
                player_id=self.test_players[1].id,
                status=ConfirmationStatus.CONFIRMED
            )
            assert confirmation.status == ConfirmationStatus.CONFIRMED
            assert confirmation.responded_at is not None
            
            # Player 3 rejects with reason
            confirmation = await self.match_ops.record_confirmation(
                match_id=self.test_match.id,
                player_id=self.test_players[2].id,
                status=ConfirmationStatus.REJECTED,
                reason="Placements are wrong"
            )
            assert confirmation.status == ConfirmationStatus.REJECTED
            assert confirmation.rejection_reason == "Placements are wrong"
            
            # Check not all confirmed
            all_confirmed, confirmations = await self.match_ops.check_all_confirmed(self.test_match.id)
            assert all_confirmed == False
            
            print("✅ Confirmations recorded correctly")
            return True
            
        except Exception as e:
            print(f"❌ Record confirmation test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_5_finalize_with_rejection(self):
        """Test that finalization fails with rejections"""
        print("\n📋 Test 5: Finalization with Rejection")
        
        try:
            # Try to finalize with a rejection
            try:
                await self.match_ops.finalize_confirmed_results(self.test_match.id)
                print("❌ Finalization succeeded with rejection!")
                return False
            except Exception as e:
                if "Not all players have confirmed" in str(e):
                    print("✅ Finalization correctly blocked by rejection")
                    return True
                else:
                    raise
                    
        except Exception as e:
            print(f"❌ Finalization rejection test failed: {e}")
            return False
    
    async def test_6_cleanup_and_retry(self):
        """Test cleanup and retry workflow"""
        print("\n📋 Test 6: Cleanup and Retry")
        
        try:
            # Manually expire the proposal
            async with self.db.get_session() as session:
                proposal = await self.match_ops.get_pending_proposal(self.test_match.id)
                proposal.expires_at = datetime.utcnow() - timedelta(hours=1)
                session.add(proposal)
                await session.commit()
            
            # Run cleanup
            cleaned = await self.match_ops.cleanup_expired_proposals()
            assert cleaned >= 1
            
            # Verify match reset to PENDING
            async with self.db.get_session() as session:
                match = await session.get(Match, self.test_match.id)
                assert match.status == MatchStatus.PENDING
            
            # Verify confirmations deleted
            all_confirmed, confirmations = await self.match_ops.check_all_confirmed(self.test_match.id)
            assert len(confirmations) == 0
            
            # Now create a new proposal
            results = [
                {"player_id": self.test_players[0].id, "placement": 1},
                {"player_id": self.test_players[1].id, "placement": 2},
                {"player_id": self.test_players[2].id, "placement": 3},
                {"player_id": self.test_players[3].id, "placement": 4}
            ]
            
            proposal = await self.match_ops.create_result_proposal(
                match_id=self.test_match.id,
                proposer_id=self.test_players[1].id,
                results=results
            )
            
            assert proposal is not None
            print("✅ Cleanup and retry successful")
            return True
            
        except Exception as e:
            print(f"❌ Cleanup test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_7_full_confirmation_flow(self):
        """Test complete confirmation and finalization flow"""
        print("\n📋 Test 7: Full Confirmation Flow")
        
        try:
            # All players confirm (skip player 1 who is the proposer and already auto-confirmed)
            for player in [self.test_players[0]] + self.test_players[2:]:  # Skip player 1 (proposer)
                await self.match_ops.record_confirmation(
                    match_id=self.test_match.id,
                    player_id=player.id,
                    status=ConfirmationStatus.CONFIRMED
                )
            
            # Check all confirmed
            all_confirmed, confirmations = await self.match_ops.check_all_confirmed(self.test_match.id)
            assert all_confirmed == True
            assert all(c.status == ConfirmationStatus.CONFIRMED for c in confirmations)
            
            # Finalize results
            completed_match = await self.match_ops.finalize_confirmed_results(self.test_match.id)
            
            # Verify match completed
            assert completed_match.status == MatchStatus.COMPLETED
            assert completed_match.completed_at is not None
            
            # Verify participants have results
            assert len(completed_match.participants) == 4
            for i, participant in enumerate(sorted(completed_match.participants, key=lambda p: p.placement)):
                assert participant.placement == i + 1
            
            # Verify proposal marked inactive
            proposal = await self.match_ops.get_pending_proposal(self.test_match.id)
            assert proposal is None  # No active proposal
            
            print("✅ Full confirmation flow completed successfully")
            return True
            
        except Exception as e:
            print(f"❌ Full flow test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_8_non_participant_proposal(self):
        """Test that non-participants cannot create proposals"""
        print("\n📋 Test 8: Non-Participant Validation")
        
        try:
            # Create a new FFA match with fewer players for this test
            player_ids = [self.test_players[0].id, self.test_players[1].id, self.test_players[2].id]
            match = await self.match_ops.create_ffa_match(
                event_id=self.test_event.id,
                participant_ids=player_ids,
                created_by_id=player_ids[0]
            )
            
            # Non-participant tries to create proposal
            results = [
                {"player_id": player_ids[0], "placement": 1},
                {"player_id": player_ids[1], "placement": 2},
                {"player_id": player_ids[2], "placement": 3}
            ]
            
            try:
                await self.match_ops.create_result_proposal(
                    match_id=match.id,
                    proposer_id=self.test_players[3].id,  # Not a participant
                    results=results
                )
                print("❌ Non-participant was allowed to propose!")
                return False
            except Exception as e:
                if "not a participant" in str(e):
                    print("✅ Non-participant correctly rejected")
                    return True
                else:
                    raise
                    
        except Exception as e:
            print(f"❌ Non-participant test failed: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all test cases"""
        print("\n" + "="*60)
        print("🧪 Phase B Confirmation System Test Suite")
        print("="*60)
        
        await self.setup()
        
        tests = [
            self.test_1_model_creation,
            self.test_2_create_proposal,
            self.test_3_duplicate_proposal,
            self.test_4_record_confirmation,
            self.test_5_finalize_with_rejection,
            self.test_6_cleanup_and_retry,
            self.test_7_full_confirmation_flow,
            self.test_8_non_participant_proposal
        ]
        
        results = []
        for test in tests:
            try:
                result = await test()
                results.append(result)
            except Exception as e:
                print(f"❌ Test crashed: {e}")
                results.append(False)
        
        await self.teardown()
        
        # Summary
        print("\n" + "="*60)
        print("📊 Test Summary")
        print("="*60)
        passed = sum(1 for r in results if r)
        total = len(results)
        print(f"✅ Passed: {passed}/{total}")
        print(f"❌ Failed: {total - passed}/{total}")
        
        if passed == total:
            print("\n🎉 All tests passed! Phase B infrastructure is working correctly.")
            print("\nNext steps:")
            print("1. Run the migration in production: python migration_phase_b_confirmation_system.py")
            print("2. Implement Phase C: Discord UI with confirmation buttons")
            print("3. Update match-report command to use proposals")
        else:
            print("\n⚠️  Some tests failed. Please review the errors above.")
        
        return passed == total


async def main():
    """Run the test suite"""
    tester = TestPhaseB()
    success = await tester.run_all_tests()
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    import sys
    sys.exit(0 if result else 1)