"""
Elo Hierarchy Calculator - Phase 3.2 Implementation

Calculates cluster and overall Elo from event-level ratings using prestige weighting systems.
Implements the hierarchical tournament structure from planA.md lines 519-577.
"""

from typing import List, Dict, Optional
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from bot.database.models import Player, PlayerEventStats, Cluster, Event


class EloHierarchyCalculator:
    """Calculates cluster and overall Elo from event-level ratings"""
    
    # Prestige weighting constants for cluster calculations
    _EVENT_WEIGHTS = [4.0, 2.5, 1.5]  # Best, second-best, third-best events
    _REMAINDER_WEIGHT = 1.0            # Fourth+ events
    
    # Tiered weighting buckets for overall calculations
    _TIER_BUCKETS = [
        (10, 0.60),  # Top 10 clusters: 60% weight
        (5, 0.25),   # Clusters 11-15: 25% weight  
        (5, 0.15),   # Clusters 16-20: 15% weight
    ]
    
    def __init__(self, session):
        """
        Initialize the calculator with a database session.
        
        Args:
            session: SQLAlchemy async session
        """
        self.session = session
    
    async def _fetch_event_stats(self, player_id: int, cluster_id: Optional[int] = None) -> List[PlayerEventStats]:
        """
        Fetch all event stats for a player with event and cluster relationships.
        
        Args:
            player_id: The player's ID
            cluster_id: Optional specific cluster ID to filter by
            
        Returns:
            List of PlayerEventStats with eagerly loaded event and cluster data
        """
        result = await self.session.execute(
            select(PlayerEventStats)
            .join(PlayerEventStats.event)
            .join(Event.cluster)
            .options(
                joinedload(PlayerEventStats.event)
                .joinedload(Event.cluster)
            )
            .where(
                PlayerEventStats.player_id == player_id,
                # Include all events - the calculation will handle them correctly
                *([Event.cluster_id == cluster_id] if cluster_id is not None else [])
            )
            .order_by(
                Event.cluster_id,
                PlayerEventStats.scoring_elo.desc()  # Pre-sort for deterministic ordering
            )
        )
        return result.scalars().all()
    
    @staticmethod
    def _weighted_average(values: List[float], weights: List[float]) -> float:
        """
        Calculate weighted average of values.
        
        Args:
            values: List of values to average
            weights: List of weights corresponding to values
            
        Returns:
            Weighted average
        """
        if not values or not weights:
            return 0.0
        
        assert len(values) == len(weights), f"Length mismatch: {len(values)} values vs {len(weights)} weights"
        
        total_weighted = sum(v * w for v, w in zip(values, weights))
        total_weight = sum(weights)
        
        return total_weighted / total_weight if total_weight > 0 else 0.0
    
    async def calculate_cluster_elo(
        self, 
        player_id: int, 
        cluster_id: Optional[int] = None
    ) -> Dict[int, int]:
        """
        Calculate cluster Elo using prestige weighting system.
        
        From planA.md lines 519-557:
        - Best event: 4.0x weight
        - Second best: 2.5x weight  
        - Third best: 1.5x weight
        - Fourth+: 1.0x weight
        
        Args:
            player_id: The player's ID
            cluster_id: Optional specific cluster ID to calculate (if None, calculates all)
            
        Returns:
            Dictionary mapping cluster_id to calculated cluster Elo
        """
        # Input validation
        if player_id is None:
            raise ValueError("player_id cannot be None")
        if not isinstance(player_id, int):
            raise TypeError("player_id must be an integer")
            
        event_stats = await self._fetch_event_stats(player_id, cluster_id)
        
        # Group event stats by cluster
        clusters = defaultdict(list)
        for stat in event_stats:
            clusters[stat.event.cluster_id].append(stat.raw_elo)
        
        cluster_elos = {}
        
        for cid, elos in clusters.items():
            if not elos:
                cluster_elos[cid] = 1000  # Default floor
                continue
            
            # Sort Elos in descending order for prestige ranking
            elos.sort(reverse=True)
            
            # Apply prestige multipliers
            weights = []
            for i in range(len(elos)):
                if i < len(self._EVENT_WEIGHTS):
                    weights.append(self._EVENT_WEIGHTS[i])
                else:
                    weights.append(self._REMAINDER_WEIGHT)
            
            # Calculate weighted average
            cluster_elo = self._weighted_average(elos, weights)
            
            # Return raw value (floor will be applied separately for scoring_elo)
            cluster_elos[cid] = round(cluster_elo)
        
        return cluster_elos
    
    def _calculate_overall_from_cluster_elos(self, cluster_elos: Dict[int, int]) -> int:
        """
        Calculate overall Elo from pre-computed cluster Elos.
        
        Args:
            cluster_elos: Dictionary mapping cluster_id to cluster Elo
            
        Returns:
            Calculated overall Elo rating
        """
        if not cluster_elos:
            return 1000  # Default if no events
        
        # Ensure we have 20 cluster values (fill missing with 1000)
        all_cluster_elos = []
        for cluster_id in range(1, 21):  # Clusters 1-20
            all_cluster_elos.append(cluster_elos.get(cluster_id, 1000))
        
        # Sort cluster Elos in descending order
        ranked_elos = sorted(all_cluster_elos, reverse=True)
        
        # Calculate tier averages
        # Tier 1: Ranks 1-10 (indices 0-9)
        tier1_elos = ranked_elos[0:10]
        avg_t1 = sum(tier1_elos) / len(tier1_elos) if tier1_elos else 1000
        
        # Tier 2: Ranks 11-15 (indices 10-14)
        tier2_elos = ranked_elos[10:15]
        avg_t2 = sum(tier2_elos) / len(tier2_elos) if tier2_elos else 1000
        
        # Tier 3: Ranks 16-20 (indices 15-19)
        tier3_elos = ranked_elos[15:20]
        avg_t3 = sum(tier3_elos) / len(tier3_elos) if tier3_elos else 1000
        
        # Apply weights to tier averages
        overall_elo = (avg_t1 * 0.60) + (avg_t2 * 0.25) + (avg_t3 * 0.15)
        
        # Return raw value (floor will be applied separately for scoring_elo)
        return round(overall_elo)
    
    async def calculate_overall_elo(self, player_id: int) -> int:
        """
        Calculate overall Elo using tiered weighting.
        
        From planA.md lines 559-577:
        - Top 10 clusters: 60% weight
        - Clusters 11-15: 25% weight
        - Clusters 16-20: 15% weight
        
        Args:
            player_id: The player's ID
            
        Returns:
            Calculated overall Elo rating
        """
        cluster_elos = await self.calculate_cluster_elo(player_id)
        return self._calculate_overall_from_cluster_elos(cluster_elos)
    
    async def calculate_player_hierarchy(self, player_id: int) -> Dict:
        """
        Calculate complete hierarchy for a player (convenience method).
        
        Args:
            player_id: The player's ID
            
        Returns:
            Dictionary containing cluster Elos and overall Elo
        """
        cluster_elos = await self.calculate_cluster_elo(player_id)
        overall_elo = self._calculate_overall_from_cluster_elos(cluster_elos)
        
        return {
            'cluster_elos': cluster_elos,
            'overall_elo': overall_elo,  # Keep for backward compatibility
            'overall_raw_elo': overall_elo,  # Actual calculated value (can be < 1000)
            'overall_scoring_elo': max(1000, overall_elo),  # Floored for display/ranking
            'total_clusters': len(cluster_elos)
        }