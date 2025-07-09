"""
Custom exceptions for leaderboard system with user-friendly error messages.
"""

class LeaderboardException(Exception):
    """Base exception for leaderboard-related errors."""
    def __init__(self, message: str, user_message: str = None):
        super().__init__(message)
        self.user_message = user_message or message

class EventNotFoundError(LeaderboardException):
    """Raised when an event is not found or not accessible."""
    def __init__(self, event_name: str):
        super().__init__(
            f"Event '{event_name}' not found",
            f"❌ Event '{event_name}' not found in this server!"
        )

class InvalidEventError(LeaderboardException):
    """Raised when an event is not configured for score submissions."""
    def __init__(self, event_name: str):
        super().__init__(
            f"Event '{event_name}' not configured for leaderboard",
            "❌ This event is not configured for score submissions!"
        )

class ScoreValidationError(LeaderboardException):
    """Raised when score validation fails."""
    def __init__(self, score: float, reason: str):
        super().__init__(
            f"Invalid score {score}: {reason}",
            f"❌ {reason}"
        )

class DatabaseError(LeaderboardException):
    """Raised when database operations fail."""
    def __init__(self, operation: str, details: str = None):
        super().__init__(
            f"Database error during {operation}: {details}",
            "❌ Database error occurred. Please try again later."
        )

class RateLimitError(LeaderboardException):
    """Raised when rate limit is exceeded."""
    def __init__(self, cooldown_remaining: int):
        super().__init__(
            f"Rate limit exceeded, {cooldown_remaining}s remaining",
            f"❌ Please wait {cooldown_remaining} seconds before submitting again."
        )

class GuildSecurityError(LeaderboardException):
    """Raised when guild security checks fail."""
    def __init__(self):
        super().__init__(
            "Command used outside of guild context",
            "❌ This command can only be used in a server!"
        )

class TransactionError(LeaderboardException):
    """Raised when transaction operations fail."""
    def __init__(self, operation: str, attempts: int):
        super().__init__(
            f"Transaction failed for {operation} after {attempts} attempts",
            "❌ Failed to save score. Please try again."
        )