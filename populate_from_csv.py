#!/usr/bin/env python3
"""
Phase 1.3: CSV Parsing and Data Population

Standalone script for populating clusters and events from "LB Culling Games List.csv"
with support for complex scoring types, event name suffixes, and score direction inference.

This script can be run independently or imported by the Discord bot for admin commands.
"""

import os
import sys
import csv
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# Add bot directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from bot.config import Config
from bot.database.database import Database
from bot.database.models import Cluster, Event
from bot.utils.event_name_parser import extract_base_event_name


def setup_logging() -> logging.Logger:
    """Setup logging for the population script"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'logs/csv_population_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def parse_scoring_types(scoring_type_str: str) -> List[str]:
    """
    Parse complex scoring type strings into individual scoring types.
    
    Examples:
        "1v1/FFA" → ["1v1", "FFA"]
        "1v1, 2v2" → ["1v1", "Team"]
        "2v2" → ["Team"]
        "???" → []
    
    Args:
        scoring_type_str: Raw scoring type from CSV
        
    Returns:
        List of normalized scoring types
    """
    if not scoring_type_str or scoring_type_str.strip() in ['', '???']:
        return []
    
    # Clean and split on common separators
    scoring_type_str = scoring_type_str.strip()
    
    # Handle comma-separated values
    if ',' in scoring_type_str:
        parts = [part.strip() for part in scoring_type_str.split(',')]
    # Handle slash-separated values
    elif '/' in scoring_type_str:
        parts = [part.strip() for part in scoring_type_str.split('/')]
    else:
        parts = [scoring_type_str]
    
    # Normalize each part
    normalized_types = []
    valid_types = {'1v1', 'FFA', 'Team', 'Leaderboard'}
    
    for part in parts:
        # Normalize team variations
        if part in ['2v2', '4v4', 'Team']:
            normalized_types.append('Team')
        elif part in valid_types:
            normalized_types.append(part)
        else:
            # Log unknown types but don't fail
            logging.getLogger(__name__).warning(f"Unknown scoring type: '{part}' in '{scoring_type_str}'")
    
    # Remove duplicates while preserving order
    return list(dict.fromkeys(normalized_types))


def create_event_name_with_suffix(base_name: str, scoring_type: str, is_duplicate: bool = False) -> str:
    """
    Create event name with appropriate suffix for clarity.
    
    Args:
        base_name: Base event name from CSV
        scoring_type: Normalized scoring type
        is_duplicate: True if this is not the first event with this base name
        
    Returns:
        Event name with suffix if needed
    """
    if not is_duplicate and scoring_type in ['1v1', 'FFA']:
        # For single events that are common types, no suffix needed
        return base_name
    
    # Always add suffix for mixed events or team events
    return f"{base_name} ({scoring_type})"


def infer_score_direction(event_name: str, notes: str = "") -> Optional[str]:
    """
    Infer score direction for leaderboard events based on name and notes.
    
    Args:
        event_name: Name of the event
        notes: Additional notes from CSV
        
    Returns:
        "HIGH" for higher-is-better, "LOW" for lower-is-better, None for non-leaderboard
    """
    combined_text = f"{event_name} {notes}".lower()
    
    # Time-based events (lower is better)
    time_keywords = ['time', 'sprint', 'dash', 'run', 'completion time', 'any%', 'speedrun']
    if any(keyword in combined_text for keyword in time_keywords):
        return "LOW"
    
    # Score-based events (higher is better)
    score_keywords = ['score', 'points', 'kills', 'home run', 'quiz', 'puzzle']
    if any(keyword in combined_text for keyword in score_keywords):
        return "HIGH"
    
    # Default to HIGH for ambiguous leaderboard events
    return "HIGH"


async def clear_existing_data(db: Database) -> None:
    """
    Clear all existing clusters and events for a clean import.
    
    Args:
        db: Database instance
    """
    logger = logging.getLogger(__name__)
    logger.info("Clearing existing clusters and events...")
    
    async with db.transaction() as session:
        # Delete events first (foreign key constraint)
        from sqlalchemy import delete
        await session.execute(delete(Event))
        await session.execute(delete(Cluster))
        await session.flush()
    
    logger.info("Existing data cleared successfully")


async def populate_clusters_and_events(csv_path: str = "LB Culling Games List.csv") -> Dict[str, int]:
    """
    Main population function that reads CSV and creates database records.
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        Dictionary with counts of created records
    """
    logger = logging.getLogger(__name__)
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    # Initialize database
    db = Database()
    await db.initialize()
    
    # Clear existing data
    await clear_existing_data(db)
    
    # Track created records
    clusters_created = {}
    events_created = 0
    events_skipped = 0
    current_cluster = None
    
    # Track event names to handle duplicates
    event_name_counts = {}
    
    try:
        async with db.transaction() as session:
            with open(csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 for CSV line numbers
                    cluster_number = row.get('Cluster Number', '').strip()
                    cluster_name = row.get('Cluster', '').strip()
                    event_name = row.get('Game Mode', '').strip()
                    scoring_type = row.get('Scoring Type', '').strip()
                    notes = row.get('Notes', '').strip()
                    
                    # Skip empty rows
                    if not event_name or not scoring_type:
                        logger.debug(f"Line {row_num}: Skipping empty row")
                        continue
                    
                    # Handle cluster creation
                    if cluster_number and cluster_name:
                        try:
                            cluster_num = int(cluster_number)
                            if cluster_num not in clusters_created:
                                cluster = Cluster(
                                    number=cluster_num,
                                    name=cluster_name,
                                    is_active=True
                                )
                                session.add(cluster)
                                await session.flush()  # Get the ID
                                clusters_created[cluster_num] = cluster
                                current_cluster = cluster
                                logger.info(f"Created cluster {cluster_num}: {cluster_name}")
                        except ValueError:
                            logger.warning(f"Line {row_num}: Invalid cluster number: {cluster_number}")
                            continue
                    
                    # Use current cluster if no cluster specified in this row
                    if current_cluster is None:
                        logger.warning(f"Line {row_num}: No cluster defined for event: {event_name}")
                        continue
                    
                    # Parse scoring types
                    parsed_scoring_types = parse_scoring_types(scoring_type)
                    if not parsed_scoring_types:
                        logger.warning(f"Line {row_num}: No valid scoring types for event '{event_name}', skipping")
                        events_skipped += 1
                        continue
                    
                    # Create events for each scoring type
                    for i, normalized_scoring_type in enumerate(parsed_scoring_types):
                        # Track duplicates for naming
                        base_name = event_name
                        event_name_counts[base_name] = event_name_counts.get(base_name, 0) + 1
                        is_duplicate = len(parsed_scoring_types) > 1 or event_name_counts[base_name] > 1
                        
                        # Create event name with suffix
                        final_event_name = create_event_name_with_suffix(
                            base_name, normalized_scoring_type, is_duplicate
                        )
                        
                        # Set player limits based on scoring type
                        if normalized_scoring_type == '1v1':
                            min_players, max_players = 2, 2
                        elif normalized_scoring_type == 'Team':
                            min_players, max_players = 4, 10
                        elif normalized_scoring_type in ['FFA', 'Leaderboard']:
                            min_players, max_players = 3, 16
                        else:
                            min_players, max_players = 2, 8  # Default
                        
                        # Infer score direction for leaderboard events
                        score_direction = None
                        if normalized_scoring_type == 'Leaderboard':
                            score_direction = infer_score_direction(event_name, notes)
                        
                        # Extract base event name for UI aggregation
                        base_name_for_aggregation = extract_base_event_name(final_event_name)
                        
                        # Create event
                        event = Event(
                            name=final_event_name,
                            base_event_name=base_name_for_aggregation,
                            cluster_id=current_cluster.id,
                            scoring_type=normalized_scoring_type,
                            score_direction=score_direction,
                            crownslayer_pool=300,
                            is_active=True,
                            allow_challenges=True,
                            min_players=min_players,
                            max_players=max_players
                        )
                        
                        session.add(event)
                        events_created += 1
                        
                        logger.debug(
                            f"Created event: {final_event_name} "
                            f"({normalized_scoring_type}, cluster: {current_cluster.name})"
                            f"{f', direction: {score_direction}' if score_direction else ''}"
                        )
            
            # Commit all changes
            await session.commit()
            
    except Exception as e:
        logger.error(f"Error during CSV population: {e}")
        raise
    finally:
        await db.close()
    
    results = {
        'clusters_created': len(clusters_created),
        'events_created': events_created,
        'events_skipped': events_skipped
    }
    
    logger.info(
        f"CSV population completed: "
        f"{results['clusters_created']} clusters, "
        f"{results['events_created']} events created, "
        f"{results['events_skipped']} events skipped"
    )
    
    return results


async def main():
    """Main entry point for standalone script execution"""
    logger = setup_logging()
    
    try:
        logger.info("Starting CSV population script...")
        results = await populate_clusters_and_events()
        
        print("\n" + "="*50)
        print("CSV POPULATION COMPLETED SUCCESSFULLY")
        print("="*50)
        print(f"Clusters created: {results['clusters_created']}")
        print(f"Events created: {results['events_created']}")
        print(f"Events skipped: {results['events_skipped']}")
        print("="*50)
        
    except Exception as e:
        logger.error(f"CSV population failed: {e}")
        print(f"\nERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())