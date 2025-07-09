"""
Elo Service Module - Phase 5.4.2

Centralized Elo calculation logic used by both normal match flow and
administrative operations (undo/recalculation). Provides pure functions
for testability and consistent Elo calculations across the system.

Key functionality:
- calculate_single_match_elo(): Calculate Elo changes for any match type
- recalculate_player_elo(): Recalculate player Elo from match history
- calculate_ffa_elo_changes(): Multi-player FFA Elo calculations
- validate_elo_calculation(): Verify Elo calculation integrity
- get_elo_rating_stats(): Generate Elo statistics for analysis

Architecture Benefits:
- Pure functions for easy testing and verification
- Centralized logic eliminates calculation inconsistencies
- Supports all match types (1v1, FFA, Team)
- Used by both normal operations and admin undo/recalculation
- Compatible with existing EloCalculator utility class
"""

import json
import math
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from bot.utils.elo import EloCalculator
from bot.config import Config
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class PlayerEloData:
    """Data structure for player Elo information"""
    player_id: int
    current_elo: int
    matches_played: int
    placement: int  # 1 = first place, 2 = second place, etc.
    

@dataclass
class EloCalculationResult:
    """Result of Elo calculation with detailed breakdown"""
    player_id: int
    old_elo: int
    new_elo: int
    elo_change: int
    k_factor: int
    expected_score: float
    actual_score: float
    calculation_method: str  # "1v1", "ffa", "team"


class EloService:
    """
    Centralized Elo calculation service for all match types.
    
    Provides pure, testable functions for Elo calculations that can be
    used by both normal match operations and administrative operations.
    """
    
    @staticmethod
    def calculate_single_match_elo(
        players_data: List[PlayerEloData],
        match_type: str = "1v1",
        config_service=None
    ) -> List[EloCalculationResult]:
        """
        Calculate Elo changes for a single match of any type.
        
        Args:
            players_data: List of PlayerEloData with current ratings and placements
            match_type: Type of match ("1v1", "ffa", "team")
            
        Returns:
            List of EloCalculationResult for each player
            
        Raises:
            ValueError: If match_type is unsupported or players_data is invalid
        """
        if not players_data:
            raise ValueError("players_data cannot be empty")
        
        if match_type == "1v1":
            return EloService._calculate_1v1_elo(players_data, config_service)
        elif match_type == "ffa":
            return EloService._calculate_ffa_elo(players_data, config_service)
        elif match_type == "team":
            return EloService._calculate_team_elo(players_data, config_service)
        else:
            raise ValueError(f"Unsupported match type: {match_type}")
    
    @staticmethod
    def _calculate_1v1_elo(players_data: List[PlayerEloData], config_service=None) -> List[EloCalculationResult]:
        """Calculate Elo changes for 1v1 match"""
        if len(players_data) != 2:
            raise ValueError("1v1 match must have exactly 2 players")
        
        player1, player2 = players_data
        
        # Determine winner based on placement (1 = winner, 2 = loser)
        player1_won = player1.placement < player2.placement
        is_draw = player1.placement == player2.placement
        
        # Use existing EloCalculator for 1v1 calculations
        player1_change, player2_change = EloCalculator.calculate_match_elo_changes(
            player1.current_elo, player1.matches_played,
            player2.current_elo, player2.matches_played,
            player1_won, is_draw, config_service
        )
        
        # Calculate expected and actual scores for reporting
        expected_score_1 = EloCalculator.calculate_expected_score(player1.current_elo, player2.current_elo)
        expected_score_2 = 1.0 - expected_score_1
        
        if is_draw:
            actual_score_1 = actual_score_2 = 0.5
        elif player1_won:
            actual_score_1, actual_score_2 = 1.0, 0.0
        else:
            actual_score_1, actual_score_2 = 0.0, 1.0
        
        return [
            EloCalculationResult(
                player_id=player1.player_id,
                old_elo=player1.current_elo,
                new_elo=player1.current_elo + player1_change,
                elo_change=player1_change,
                k_factor=EloCalculator.get_k_factor(player1.matches_played, config_service),
                expected_score=expected_score_1,
                actual_score=actual_score_1,
                calculation_method="1v1"
            ),
            EloCalculationResult(
                player_id=player2.player_id,
                old_elo=player2.current_elo,
                new_elo=player2.current_elo + player2_change,
                elo_change=player2_change,
                k_factor=EloCalculator.get_k_factor(player2.matches_played, config_service),
                expected_score=expected_score_2,
                actual_score=actual_score_2,
                calculation_method="1v1"
            )
        ]
    
    @staticmethod
    def _calculate_ffa_elo(players_data: List[PlayerEloData], config_service=None) -> List[EloCalculationResult]:
        """
        Calculate Elo changes for FFA match using N*(N-1)/2 pairwise comparisons.
        
        Uses K/(N-1) scaling to prevent excessive volatility in large FFAs.
        """
        n_players = len(players_data)
        if n_players < 3:
            raise ValueError("FFA match must have at least 3 players")
        
        # Sort players by placement (1st place = placement 1, etc.)
        players_sorted = sorted(players_data, key=lambda p: p.placement)
        
        results = []
        
        for i, player in enumerate(players_sorted):
            total_elo_change = 0
            total_expected_score = 0
            total_actual_score = 0
            
            # Calculate K-factor with FFA scaling (once per player)
            base_k_factor = EloCalculator.get_k_factor(player.matches_played, config_service)
            scaled_k_factor = base_k_factor / (n_players - 1)
            
            # Calculate pairwise comparisons against all other players
            for j, opponent in enumerate(players_sorted):
                if i == j:
                    continue
                
                # Calculate expected score for this pairing
                expected_score = EloCalculator.calculate_expected_score(
                    player.current_elo, opponent.current_elo
                )
                
                # Actual score: 1.0 if player placed better, 0.5 for tie, 0.0 if worse
                if player.placement < opponent.placement:
                    actual_score = 1.0
                elif player.placement == opponent.placement:
                    actual_score = 0.5
                else:
                    actual_score = 0.0
                
                # Calculate Elo change for this pairing using scaled K-factor
                elo_change = scaled_k_factor * (actual_score - expected_score)
                
                total_elo_change += elo_change
                total_expected_score += expected_score
                total_actual_score += actual_score
            
            # Average scores for reporting
            avg_expected_score = total_expected_score / (n_players - 1)
            avg_actual_score = total_actual_score / (n_players - 1)
            
            results.append(EloCalculationResult(
                player_id=player.player_id,
                old_elo=player.current_elo,
                new_elo=player.current_elo + round(total_elo_change),
                elo_change=round(total_elo_change),
                k_factor=int(round(scaled_k_factor)),
                expected_score=avg_expected_score,
                actual_score=avg_actual_score,
                calculation_method="ffa"
            ))
        
        return results
    
    @staticmethod
    def _calculate_team_elo(players_data: List[PlayerEloData], config_service=None) -> List[EloCalculationResult]:
        """
        Calculate Elo changes for team match.
        
        For team matches, all players on the same team (same placement) get
        the same Elo change based on team vs team calculation.
        """
        if len(players_data) < 2:
            raise ValueError("Team match must have at least 2 players")
        
        # Group players by placement (team)
        teams = {}
        for player in players_data:
            if player.placement not in teams:
                teams[player.placement] = []
            teams[player.placement].append(player)
        
        if len(teams) < 2:
            raise ValueError("Team match must have at least 2 teams")
        
        # Calculate average team ratings
        team_ratings = {}
        team_match_counts = {}
        
        for placement, team_players in teams.items():
            total_rating = sum(p.current_elo for p in team_players)
            total_matches = sum(p.matches_played for p in team_players)
            team_ratings[placement] = total_rating // len(team_players)
            team_match_counts[placement] = total_matches // len(team_players)
        
        results = []
        
        # Calculate Elo changes for each team against all other teams
        for placement, team_players in teams.items():
            team_elo_change = 0
            team_expected_score = 0
            team_actual_score = 0
            comparisons = 0
            
            for opponent_placement, _ in teams.items():
                if placement == opponent_placement:
                    continue
                
                # Calculate expected score between teams
                expected_score = EloCalculator.calculate_expected_score(
                    team_ratings[placement], team_ratings[opponent_placement]
                )
                
                # Actual score based on team placement
                if placement < opponent_placement:
                    actual_score = 1.0
                elif placement == opponent_placement:
                    actual_score = 0.5
                else:
                    actual_score = 0.0
                
                # Use team's average K-factor
                base_k_factor = EloCalculator.get_k_factor(team_match_counts[placement], config_service)
                scaled_k_factor = base_k_factor / (len(teams) - 1)
                
                elo_change = scaled_k_factor * (actual_score - expected_score)
                
                team_elo_change += elo_change
                team_expected_score += expected_score
                team_actual_score += actual_score
                comparisons += 1
            
            # Apply same Elo change to all team members
            avg_expected_score = team_expected_score / comparisons if comparisons > 0 else 0
            avg_actual_score = team_actual_score / comparisons if comparisons > 0 else 0
            
            for player in team_players:
                results.append(EloCalculationResult(
                    player_id=player.player_id,
                    old_elo=player.current_elo,
                    new_elo=player.current_elo + round(team_elo_change),
                    elo_change=round(team_elo_change),
                    k_factor=int(round(scaled_k_factor)),
                    expected_score=avg_expected_score,
                    actual_score=avg_actual_score,
                    calculation_method="team"
                ))
        
        return results
    
    @staticmethod
    def recalculate_player_elo(
        player_id: int,
        event_id: int,
        match_history: List[Dict[str, Any]],
        starting_elo: int = None,
        config_service=None
    ) -> Dict[str, Any]:
        """
        Recalculate a player's Elo from scratch using match history.
        
        Used for admin undo operations and integrity verification.
        
        Args:
            player_id: ID of player to recalculate
            event_id: Event ID for context
            match_history: List of match data in chronological order
            starting_elo: Starting Elo (defaults to Config.STARTING_ELO)
            
        Returns:
            Dictionary with recalculation results
        """
        if starting_elo is None:
            starting_elo = Config.STARTING_ELO
        
        current_elo = starting_elo
        matches_played = 0
        elo_changes = []
        
        logger.info(f"Recalculating Elo for player {player_id} in event {event_id}")
        
        for match_data in match_history:
            # Extract match information
            match_id = match_data.get('match_id')
            match_type = match_data.get('match_type', '1v1')
            participants = match_data.get('participants', [])
            
            # Find this player's data in the match
            player_data = None
            other_players = []
            
            for participant in participants:
                if participant['player_id'] == player_id:
                    player_data = PlayerEloData(
                        player_id=player_id,
                        current_elo=current_elo,
                        matches_played=matches_played,
                        placement=participant['placement']
                    )
                else:
                    other_players.append(PlayerEloData(
                        player_id=participant['player_id'],
                        current_elo=participant['elo_before'],
                        matches_played=participant['matches_played'],
                        placement=participant['placement']
                    ))
            
            if not player_data:
                logger.warning(f"Player {player_id} not found in match {match_id}, skipping")
                continue
            
            # Calculate Elo change for this match
            all_players = [player_data] + other_players
            calculation_results = EloService.calculate_single_match_elo(all_players, match_type, config_service)
            
            # Find this player's result
            player_result = next((r for r in calculation_results if r.player_id == player_id), None)
            
            if player_result:
                current_elo = player_result.new_elo
                matches_played += 1
                
                elo_changes.append({
                    'match_id': match_id,
                    'match_type': match_type,
                    'old_elo': player_result.old_elo,
                    'new_elo': player_result.new_elo,
                    'elo_change': player_result.elo_change,
                    'expected_score': player_result.expected_score,
                    'actual_score': player_result.actual_score
                })
        
        return {
            'player_id': player_id,
            'event_id': event_id,
            'starting_elo': starting_elo,
            'final_elo': current_elo,
            'total_elo_change': current_elo - starting_elo,
            'matches_played': matches_played,
            'elo_changes': elo_changes
        }
    
    @staticmethod
    def validate_elo_calculation(
        expected_result: EloCalculationResult,
        actual_old_elo: int,
        actual_new_elo: int
    ) -> bool:
        """
        Validate that an Elo calculation matches expected results.
        
        Used for integrity checking and testing.
        
        Args:
            expected_result: Expected calculation result
            actual_old_elo: Actual old Elo from database
            actual_new_elo: Actual new Elo from database
            
        Returns:
            True if calculation is valid, False otherwise
        """
        return (
            expected_result.old_elo == actual_old_elo and
            expected_result.new_elo == actual_new_elo
        )
    
    @staticmethod
    def get_elo_rating_stats(elo_ratings: List[int]) -> Dict[str, Any]:
        """
        Generate statistical analysis of Elo ratings.
        
        Args:
            elo_ratings: List of Elo ratings to analyze
            
        Returns:
            Dictionary with statistical information
        """
        if not elo_ratings:
            return {
                'count': 0,
                'mean': 0,
                'median': 0,
                'min': 0,
                'max': 0,
                'std_deviation': 0
            }
        
        sorted_ratings = sorted(elo_ratings)
        count = len(sorted_ratings)
        mean_rating = sum(sorted_ratings) / count
        median_rating = sorted_ratings[count // 2] if count % 2 == 1 else (sorted_ratings[count // 2 - 1] + sorted_ratings[count // 2]) / 2
        
        # Calculate standard deviation
        variance = sum((r - mean_rating) ** 2 for r in sorted_ratings) / count
        std_deviation = math.sqrt(variance)
        
        return {
            'count': count,
            'mean': round(mean_rating, 2),
            'median': median_rating,
            'min': min(sorted_ratings),
            'max': max(sorted_ratings),
            'std_deviation': round(std_deviation, 2)
        }