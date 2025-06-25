import logging
import sys
from datetime import datetime
from pathlib import Path

from bot.config import Config

def setup_logger(name: str) -> logging.Logger:
    """Setup a logger with consistent formatting"""
    
    logger = logging.getLogger(name)
    
    if logger.handlers:
        return logger
    
    # Set log level based on debug setting
    log_level = logging.DEBUG if Config.DEBUG else logging.INFO
    logger.setLevel(log_level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    file_handler = logging.FileHandler(
        log_dir / f'tournament_bot_{datetime.now().strftime("%Y%m%d")}.log',
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger