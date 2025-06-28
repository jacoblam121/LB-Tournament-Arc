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
from collections import defaultdict

# Add bot directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'bot'))

from bot.config import Config
from bot.database.database import Database
from bot.database.models import Cluster, Event
from bot.utils.event_name_parser import extract_base_event_name
from sqlalchemy import select


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
        # Phase 2.4.1 Fix: Two-pass approach for complete scoring type aggregation
        
        # Pass 1: Aggregate all data from CSV
        logger.info("Pass 1: Reading and aggregating CSV data...")
        event_data_agg = defaultdict(lambda: {
            'scoring_types': set(),
            'notes': [],
            'cluster_info': None
        })
        
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            current_cluster_info = None
            
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
                
                # Update cluster context when new cluster is found
                if cluster_number and cluster_name:
                    try:
                        cluster_num = int(cluster_number)
                        current_cluster_info = {
                            'number': cluster_num,
                            'name': cluster_name
                        }
                    except ValueError:
                        logger.warning(f"Line {row_num}: Invalid cluster number: {cluster_number}")
                        continue
                
                # Skip if no cluster context
                if current_cluster_info is None:
                    logger.warning(f"Line {row_num}: No cluster defined for event: {event_name}")
                    continue
                
                # Parse scoring types
                parsed_scoring_types = parse_scoring_types(scoring_type)
                if not parsed_scoring_types:
                    logger.warning(f"Line {row_num}: No valid scoring types for event '{event_name}', skipping")
                    events_skipped += 1
                    continue
                
                # Aggregate data for this event
                cluster_key = (current_cluster_info['number'], current_cluster_info['name'])
                event_key = (cluster_key, event_name)
                
                event_agg = event_data_agg[event_key]
                event_agg['scoring_types'].update(parsed_scoring_types)
                if notes:
                    event_agg['notes'].append(notes)
                if event_agg['cluster_info'] is None:
                    event_agg['cluster_info'] = current_cluster_info
        
        logger.info(f"Pass 1 complete: Aggregated data for {len(event_data_agg)} unique events")
        
        # Pass 2: Create database records from aggregated data
        logger.info("Pass 2: Creating unified events in database...")
        
        async with db.transaction() as session:
            # Create clusters first
            for event_key, event_data in event_data_agg.items():
                cluster_key, event_name = event_key
                cluster_num, cluster_name = cluster_key
                
                # Create cluster if not exists
                if cluster_num not in clusters_created:
                    cluster = Cluster(
                        number=cluster_num,
                        name=cluster_name,
                        is_active=True
                    )
                    session.add(cluster)
                    await session.flush()  # Get the ID
                    clusters_created[cluster_num] = cluster
                    logger.info(f"Created cluster {cluster_num}: {cluster_name}")
                
                current_cluster = clusters_created[cluster_num]
                
                # Check if event already exists
                existing_event = await session.execute(
                    select(Event).where(
                        Event.cluster_id == current_cluster.id,
                        Event.name == event_name
                    )
                )
                existing_event = existing_event.scalar_one_or_none()
                
                if existing_event:
                    logger.debug(f"Event '{event_name}' already exists in cluster '{cluster_name}'")
                    continue
                
                # Get all unique scoring types (sorted for consistency)
                all_scoring_types = sorted(list(event_data['scoring_types']))
                primary_scoring_type = all_scoring_types[0]
                
                # Determine player limits based on all supported scoring types
                min_players = 2  # Minimum for any match type
                max_players = 16  # Maximum to support FFA
                
                # If only 1v1 is supported, use more restrictive limits
                if all_scoring_types == ['1v1']:
                    min_players, max_players = 2, 2
                elif 'Team' in all_scoring_types and 'FFA' not in all_scoring_types:
                    # Team only or Team + 1v1
                    min_players, max_players = 2, 10
                
                # Infer score direction for leaderboard events
                score_direction = None
                if 'Leaderboard' in all_scoring_types:
                    # Use first available notes for inference
                    first_notes = event_data['notes'][0] if event_data['notes'] else ''
                    score_direction = infer_score_direction(event_name, first_notes)
                
                # Create unified event with complete supported_scoring_types
                event = Event(
                    name=event_name,  # Unified name
                    base_event_name=event_name,  # Same as name for unified events
                    cluster_id=current_cluster.id,
                    scoring_type=primary_scoring_type,  # DEPRECATED: Will be moved to Match level
                    supported_scoring_types=','.join(all_scoring_types),  # Complete list!
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
                    f"Created unified event: {event_name} "
                    f"(supports: {','.join(all_scoring_types)}, cluster: {cluster_name})"
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