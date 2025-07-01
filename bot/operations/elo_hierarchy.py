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
                PlayerEventStats.scoring_elo > 1000,  # Exclude floor ratings (exactly 1000)
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
            clusters[stat.event.cluster_id].append(stat.scoring_elo)
        
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
            
            # Apply dual-track floor rule (round to nearest integer)
            cluster_elos[cid] = max(1000, round(cluster_elo))
        
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
        
        # Sort cluster Elos in descending order
        ranked_elos = sorted(cluster_elos.values(), reverse=True)
        
        # Apply tiered weighting
        idx = 0
        contributions = []
        total_allocated_weight = 0.0
        
        for bucket_size, bucket_weight in self._TIER_BUCKETS:
            # Get slice of cluster Elos for this tier
            tier_slice = ranked_elos[idx:idx + bucket_size]
            
            if tier_slice:
                # Distribute bucket weight equally among clusters in this tier
                per_cluster_weight = bucket_weight / len(tier_slice)
                contributions.extend([elo * per_cluster_weight for elo in tier_slice])
                total_allocated_weight += bucket_weight
            
            idx += bucket_size
        
        # Calculate overall Elo
        if contributions:
            # If we used less than full weight (< 20 clusters), renormalize
            if total_allocated_weight < 1.0:
                # Scale up contributions to use full weight
                scale_factor = 1.0 / total_allocated_weight
                overall_elo = sum(contributions) * scale_factor
            else:
                overall_elo = sum(contributions)
        else:
            overall_elo = 1000
        
        # Apply dual-track floor rule (round to nearest integer)
        return max(1000, round(overall_elo))
    
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
            'overall_elo': overall_elo,
            'total_clusters': len(cluster_elos)
        }