import math
from typing import Tuple
from bot.config import Config

class EloCalculator:
    """Handles Elo rating calculations for the tournament system"""
    
    @staticmethod
    def calculate_expected_score(rating_a: int, rating_b: int) -> float:
        """
        Calculate the expected score for player A against player B
        
        Args:
            rating_a: Player A's current Elo rating
            rating_b: Player B's current Elo rating
            
        Returns:
            Expected score (0.0 to 1.0) for player A
        """
        return 1 / (1 + math.pow(10, (rating_b - rating_a) / 400))
    
    @staticmethod
    def get_k_factor(matches_played: int) -> int:
        """
        Get the K-factor based on number of matches played
        
        Args:
            matches_played: Number of matches the player has played
            
        Returns:
            K-factor to use in Elo calculation
        """
        if matches_played < Config.PROVISIONAL_MATCH_COUNT:
            return Config.K_FACTOR_PROVISIONAL
        return Config.K_FACTOR_STANDARD
    
    @staticmethod
    def calculate_elo_change(current_rating: int, opponent_rating: int, 
                           actual_score: float, matches_played: int) -> int:
        """
        Calculate the Elo rating change for a player
        
        Args:
            current_rating: Player's current Elo rating
            opponent_rating: Opponent's current Elo rating
            actual_score: Actual score (1.0 for win, 0.5 for draw, 0.0 for loss)
            matches_played: Number of matches the player has played
            
        Returns:
            Elo rating change (can be positive or negative)
        """
        expected_score = EloCalculator.calculate_expected_score(current_rating, opponent_rating)
        k_factor = EloCalculator.get_k_factor(matches_played)
        
        elo_change = k_factor * (actual_score - expected_score)
        return round(elo_change)
    
    @staticmethod
    def calculate_match_elo_changes(player1_rating: int, player1_matches: int,
                                  player2_rating: int, player2_matches: int,
                                  player1_won: bool, is_draw: bool = False) -> Tuple[int, int]:
        """
        Calculate Elo changes for both players in a match
        
        Args:
            player1_rating: Player 1's current Elo rating
            player1_matches: Player 1's matches played
            player2_rating: Player 2's current Elo rating
            player2_matches: Player 2's matches played
            player1_won: True if player 1 won, False if player 2 won
            is_draw: True if the match was a draw
            
        Returns:
            Tuple of (player1_elo_change, player2_elo_change)
        """
        if is_draw:
            player1_score = 0.5
            player2_score = 0.5
        elif player1_won:
            player1_score = 1.0
            player2_score = 0.0
        else:
            player1_score = 0.0
            player2_score = 1.0
        
        player1_change = EloCalculator.calculate_elo_change(
            player1_rating, player2_rating, player1_score, player1_matches
        )
        
        player2_change = EloCalculator.calculate_elo_change(
            player2_rating, player1_rating, player2_score, player2_matches
        )
        
        return player1_change, player2_change
    
    
    @staticmethod
    def calculate_win_probability(rating_a: int, rating_b: int) -> float:
        """
        Calculate win probability for player A against player B
        
        Args:
            rating_a: Player A's Elo rating
            rating_b: Player B's Elo rating
            
        Returns:
            Win probability as percentage (0.0 to 100.0)
        """
        expected_score = EloCalculator.calculate_expected_score(rating_a, rating_b)
        return expected_score * 100
    
    @staticmethod
    def format_elo_change(elo_change: int) -> str:
        """
        Format Elo change for display
        
        Args:
            elo_change: The Elo change value
            
        Returns:
            Formatted string with appropriate sign and color indicators
        """
        if elo_change > 0:
            return f"+{elo_change}"
        elif elo_change < 0:
            return str(elo_change)
        else:
            return "±0"