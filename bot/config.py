import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Bot configuration settings"""
    
    # Discord settings
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    DISCORD_GUILD_ID = int(os.getenv('DISCORD_GUILD_ID', 0))
    DISCORD_GUILD_IDS = os.getenv('DISCORD_GUILD_IDS', '')  # Comma-separated for multi-guild support
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
    
    # Default cluster for auto-created events (FFA matches)
    DEFAULT_CLUSTER_ID = 19  # "Other" cluster for general FFA events
    
    @classmethod
    def get_guild_ids(cls):
        """Get list of guild IDs for command syncing"""
        if cls.DISCORD_GUILD_IDS:
            # Multi-guild support: comma-separated IDs
            try:
                return [int(guild_id.strip()) for guild_id in cls.DISCORD_GUILD_IDS.split(',') if guild_id.strip()]
            except ValueError:
                raise ValueError("DISCORD_GUILD_IDS must be comma-separated integers")
        elif cls.DISCORD_GUILD_ID:
            # Single guild support (backward compatibility)
            return [cls.DISCORD_GUILD_ID]
        else:
            # Global sync
            return []
    
    @classmethod
    def validate(cls):
        """Validate that required configuration is present"""
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required")
        if not cls.DISCORD_GUILD_ID and not cls.DISCORD_GUILD_IDS:
            raise ValueError("Either DISCORD_GUILD_ID or DISCORD_GUILD_IDS is required")
        if not cls.OWNER_DISCORD_ID:
            raise ValueError("OWNER_DISCORD_ID is required")