"""
Scoring Strategy Pattern for Multi-Player Rating Calculations

This module implements the Strategy pattern for different scoring algorithms,
allowing the system to support various rating calculations while maintaining
clean separation of concerns.

Based on expert analysis, includes:
- K-factor scaling for FFA to prevent rating volatility
- Placement tie handling (draws)
- Performance optimization for large player counts
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from bot.utils.elo import EloCalculator
from bot.config import Config
import logging

logger = logging.getLogger(__name__)

@dataclass
class ParticipantResult:
    """Represents a participant's result in a match"""
    player_id: int
    current_elo: int
    matches_played: int
    placement: int  # 1 = first place, 2 = second place, etc.
    team_id: Optional[str] = None

@dataclass
class ScoringResult:
    """Result of scoring calculation for a participant"""
    player_id: int
    elo_change: int
    pp_change: int = 0  # Performance Points change
    points_earned: int = 0  # Leaderboard points

class ScoringStrategy(ABC):
    """
    Abstract base class for scoring strategies.
    
    Each strategy implements a different approach to calculating rating changes
    based on match results and participant placements.
    """
    
    @abstractmethod
    def calculate_results(self, participants: List[ParticipantResult]) -> Dict[int, ScoringResult]:
        """
        Calculate scoring results for all participants.
        
        Args:
            participants: List of participant results with placements
            
        Returns:
            Dictionary mapping player_id to their ScoringResult
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get human-readable name of this strategy"""
        pass

class Elo1v1Strategy(ScoringStrategy):
    """
    Traditional 1v1 Elo calculation strategy.
    
    Uses the existing EloCalculator for standard head-to-head matches.
    Validates that exactly 2 participants are provided.
    """
    
    def calculate_results(self, participants: List[ParticipantResult]) -> Dict[int, ScoringResult]:
        """Calculate 1v1 Elo changes using existing EloCalculator"""
        if len(participants) != 2:
            raise ValueError(f"1v1 strategy requires exactly 2 participants, got {len(participants)}")
        
        p1, p2 = participants
        
        # Determine winner based on placement
        if p1.placement == p2.placement:
            # Draw
            is_draw = True
            p1_won = False
        elif p1.placement < p2.placement:
            # p1 won (lower placement number = better)
            is_draw = False
            p1_won = True
        else:
            # p2 won
            is_draw = False
            p1_won = False
        
        # Calculate Elo changes using existing calculator
        p1_change, p2_change = EloCalculator.calculate_match_elo_changes(
            p1.current_elo, p1.matches_played,
            p2.current_elo, p2.matches_played,
            p1_won, is_draw
        )
        
        logger.info(f"1v1 Elo calculation: P1({p1.player_id}): {p1_change}, P2({p2.player_id}): {p2_change}")
        
        return {
            p1.player_id: ScoringResult(p1.player_id, p1_change),
            p2.player_id: ScoringResult(p2.player_id, p2_change)
        }
    
    def get_strategy_name(self) -> str:
        return "1v1 Elo"

class EloFfaStrategy(ScoringStrategy):
    """
    Free-For-All Elo calculation using pairwise comparison approach.
    
    Based on expert analysis:
    - Uses N*(N-1)/2 pairwise comparisons
    - Scales K-factor by (N-1) to prevent rating volatility
    - Handles placement ties as draws
    - Optimized for performance with large player counts
    """
    
    def calculate_results(self, participants: List[ParticipantResult]) -> Dict[int, ScoringResult]:
        """Calculate FFA Elo changes using pairwise comparison method"""
        n = len(participants)
        
        if n < 2:
            raise ValueError(f"FFA strategy requires at least 2 participants, got {n}")
        
        if n > 50:  # Sanity check for performance
            logger.warning(f"Large FFA calculation with {n} participants ({n*(n-1)//2} comparisons)")
        
        # Initialize rating changes
        rating_changes = {p.player_id: 0.0 for p in participants}
        comparison_count = 0
        
        # Pairwise comparisons - O(N²) but acceptable for reasonable N
        for i, p1 in enumerate(participants):
            for j, p2 in enumerate(participants[i+1:], i+1):
                comparison_count += 1
                
                # Determine outcome based on placement
                if p1.placement < p2.placement:
                    # p1 wins (better placement)
                    p1_score, p2_score = 1.0, 0.0
                elif p1.placement > p2.placement:
                    # p2 wins (better placement)
                    p1_score, p2_score = 0.0, 1.0
                else:
                    # Tie (same placement) - critical for handling ties correctly
                    p1_score, p2_score = 0.5, 0.5
                
                # Get K-factors for each player
                p1_k = EloCalculator.get_k_factor(p1.matches_played)
                p2_k = EloCalculator.get_k_factor(p2.matches_played)
                
                # Calculate scaled Elo changes
                # CRITICAL: Scale by (n-1) to prevent rating volatility
                scaling_factor = n - 1
                
                p1_change = self._calculate_scaled_elo_change(
                    p1.current_elo, p2.current_elo, p1_k, p1_score, scaling_factor
                )
                p2_change = self._calculate_scaled_elo_change(
                    p2.current_elo, p1.current_elo, p2_k, p2_score, scaling_factor
                )
                
                rating_changes[p1.player_id] += p1_change
                rating_changes[p2.player_id] += p2_change
        
        logger.info(f"FFA Elo calculation: {n} players, {comparison_count} comparisons, scaling factor: {n-1}")
        
        # Convert to ScoringResult objects with rounded values
        results = {}
        for participant in participants:
            change = round(rating_changes[participant.player_id])
            results[participant.player_id] = ScoringResult(participant.player_id, change)
            logger.debug(f"Player {participant.player_id}: placement {participant.placement}, Elo change: {change}")
        
        return results
    
    def _calculate_scaled_elo_change(self, player_rating: int, opponent_rating: int, 
                                   k_factor: int, score: float, scaling_factor: int) -> float:
        """
        Calculate Elo change with K-factor scaling to prevent volatility.
        
        Args:
            player_rating: Player's current Elo rating
            opponent_rating: Opponent's current Elo rating  
            k_factor: Base K-factor for this player
            score: Match score (0.0, 0.5, or 1.0)
            scaling_factor: Factor to scale K by (usually N-1)
            
        Returns:
            Scaled Elo change (float for precision, round later)
        """
        expected_score = EloCalculator.calculate_expected_score(player_rating, opponent_rating)
        scaled_k = k_factor / scaling_factor
        return scaled_k * (score - expected_score)
    
    def get_strategy_name(self) -> str:
        return "FFA Elo (Pairwise)"

class PerformancePointsStrategy(ScoringStrategy):
    """
    Performance Points strategy for leaderboard-style events.
    
    Awards points based on placement without any point loss,
    encouraging participation and progression.
    """
    
    def __init__(self, base_points: int = 100):
        """
        Initialize PP strategy.
        
        Args:
            base_points: Base points awarded for participation
        """
        self.base_points = base_points
    
    def calculate_results(self, participants: List[ParticipantResult]) -> Dict[int, ScoringResult]:
        """Calculate Performance Points based on placement"""
        n = len(participants)
        results = {}
        
        for participant in participants:
            # Award points based on placement (higher placement = fewer points)
            # Formula: base_points * (n - placement + 1) / n
            # This ensures 1st place gets most points, last place gets least
            placement_multiplier = (n - participant.placement + 1) / n
            pp_change = round(self.base_points * placement_multiplier)
            
            results[participant.player_id] = ScoringResult(
                participant.player_id, 
                elo_change=0,  # No Elo change for PP events
                pp_change=pp_change,
                points_earned=pp_change
            )
        
        logger.info(f"PP calculation: {n} players, base points: {self.base_points}")
        return results
    
    def get_strategy_name(self) -> str:
        return "Performance Points"

class ScoringStrategyFactory:
    """Factory for creating scoring strategies based on event configuration"""
    
    @staticmethod
    def create_strategy(scoring_type: str, **kwargs) -> ScoringStrategy:
        """
        Create appropriate scoring strategy based on type.
        
        Args:
            scoring_type: Type of scoring ("1v1", "FFA", "Team", "Leaderboard")
            **kwargs: Additional configuration for specific strategies
            
        Returns:
            Configured ScoringStrategy instance
        """
        scoring_type = scoring_type.upper()
        
        if scoring_type == "1V1":
            return Elo1v1Strategy()
        elif scoring_type == "FFA":
            return EloFfaStrategy()
        elif scoring_type == "TEAM":
            # For now, treat team matches as FFA (individual ratings within teams)
            # Future enhancement: implement team-specific Elo calculations
            return EloFfaStrategy()
        elif scoring_type == "LEADERBOARD":
            base_points = kwargs.get('base_points', 100)
            return PerformancePointsStrategy(base_points)
        else:
            raise ValueError(f"Unknown scoring type: {scoring_type}")
    
    @staticmethod
    def get_available_strategies() -> List[str]:
        """Get list of available strategy types"""
        return ["1v1", "FFA", "Team", "Leaderboard"]