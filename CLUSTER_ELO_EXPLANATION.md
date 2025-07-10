# Cluster Elo Calculation - Technical Explanation

## Summary

After deep analysis with both Gemini 2.5 Pro and O3, we've determined that **the cluster Elo matching event Elo (1000→1020) is CORRECT behavior**, not a bug.

## Why Cluster Elo = Event Elo for New Players

When a player has **only one event** in a cluster, the prestige-weighted calculation works as follows:

### Prestige Weighting Formula
- Best event: 4.0x weight
- Second best: 2.5x weight  
- Third best: 1.5x weight
- Fourth+: 1.0x weight

### Single Event Calculation
With only one event:
```
cluster_elo = (event_elo * 4.0) / 4.0 = event_elo
```

Therefore, `1000 → 1020` for both event and cluster Elo is mathematically correct.

## Debug Logging Added

I've added debug logging to help clarify this:

1. **EloHierarchyCalculator** now logs when single-event scenarios are detected:
   ```
   [EloHierarchy] Cluster X: Single event detected. Event Elo=1020, Cluster Elo=1020 (correctly equal due to prestige weighting)
   ```

2. **EloCalculator** now logs k-factor values being used:
   ```
   [EloCalculator] K-factor calculation: matches_played=0, provisional_count=10, k_provisional=40, k_standard=16
   [EloCalculator] Using provisional K-factor: 40
   ```

## Configuration System

The configuration system is working correctly:
- `/config-set` saves values to database
- Cache is automatically reloaded after updates (line 111 in configuration.py)
- Values are retrieved via `config_service.get()`

## How Cluster Elo Will Diverge

As players participate in more events within a cluster:
1. The prestige weighting will apply different multipliers to each event
2. Better performances get higher weights (4.0x, 2.5x, 1.5x)
3. Cluster Elo will represent a weighted average of all events in that cluster

## Example with Multiple Events

Player has 3 events in a cluster:
- Event 1: 1100 Elo (best) → 4.0x weight
- Event 2: 1050 Elo → 2.5x weight
- Event 3: 1000 Elo → 1.5x weight

Cluster Elo = ((1100 * 4.0) + (1050 * 2.5) + (1000 * 1.5)) / (4.0 + 2.5 + 1.5) = 1065

## No Code Regression

The investigation confirmed:
- EloHierarchyCalculator is being used correctly
- Config service is properly wired through the system
- No code duplication or deprecated code paths
- Implementation follows the intended Phase 2 design