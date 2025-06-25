import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Bot configuration settings"""
    
    # Discord settings
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    DISCORD_GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', 0))
    OWNER_DISCORD_ID = int(os.getenv('OWNER_DISCORD_ID', 0))
    
    # Database settings
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///tournament.db')
    
    # Bot settings
    COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
    DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
    
    # Tournament settings
    CHALLENGE_ESCROW_AMOUNT = 10
    CHALLENGE_EXPIRY_HOURS = 24
    STARTING_ELO = 1000
    STARTING_TICKETS = 0
    
    # Elo calculation settings
    K_FACTOR_PROVISIONAL = 40  # First 5 matches
    K_FACTOR_STANDARD = 20     # All subsequent matches
    PROVISIONAL_MATCH_COUNT = 5
    
    # Cluster scoring settings
    CLUSTER_DECAY_FACTOR = 0.6
    
    @classmethod
    def validate(cls):
        """Validate that required configuration is present"""
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required")
        if not cls.DISCORD_GUILD_ID:
            raise ValueError("DISCORD_GUILD_ID is required")
        if not cls.OWNER_DISCORD_ID:
            raise ValueError("OWNER_DISCORD_ID is required")