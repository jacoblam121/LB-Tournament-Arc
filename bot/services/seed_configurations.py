"""
Configuration seed data for LB Tournament Arc bot.

Phase 1.2.2: Complete configuration parameters (52+) across 7 categories
as specified in planC_phase1.md.
"""

import json
import asyncio
from bot.database.models import Configuration
from bot.database.database import Database

# Complete Configuration Categories (52+ Parameters) from planC.md
INITIAL_CONFIGS = {
    # Elo System (6 parameters)
    'elo.k_factor_provisional': 40,
    'elo.k_factor_standard': 20,
    'elo.starting_elo': 1000,
    'elo.provisional_match_threshold': 5,
    'elo.raw_elo_threshold': 1000,
    'elo.leaderboard_base_elo': 1000,
    
    # Metagame (5 parameters)
    'metagame.cluster_multipliers': [4.0, 2.5, 1.5, 1.0],
    'metagame.overall_tier_weights': {
        'ranks_1_10': 0.60,
        'ranks_11_15': 0.25,
        'ranks_16_20': 0.15
    },
    'metagame.shard_bonus_pool': 300,
    'metagame.event_formula_weights': {
        'all_time_weight': 0.5,
        'weekly_weight': 0.5
    },
    'metagame.elo_per_sigma': 200,
    
    # Earning (13 parameters)
    'earning.participation_reward': 5,
    'earning.first_blood_reward': 50,
    'earning.hot_tourist_reward': 250,
    'earning.warm_tourist_reward': 50,
    'earning.social_butterfly_reward': 50,
    'earning.lightfalcon_bounty': 50,
    'earning.giant_slayer_reward': 25,
    'earning.hot_streak_reward': 50,
    'earning.frying_streak_reward': 75,
    'earning.party_pooper_reward': 50,
    'earning.golden_road_reward': 500,
    'earning.win_reward': 10,
    'earning.first_match_of_day_bonus': 10,
    
    # Shop (25+ parameters)
    'shop.drop_lowest_cost': 1000,
    'shop.inflation_base_cost': 200,
    'shop.inflation_bonus_points': 10,
    'shop.bounty_costs': {'50': 100, '100': 200, '200': 400},
    'shop.leverage_costs': {'0.5x': 50, '2x': 150, '3x': 300, '5x': 500},
    'shop.forced_leverage_costs': {'0.5x': 100, '1.5x': 300},
    'shop.veto_cost': 300,
    'shop.lifesteal_cost': 200,
    'shop.insider_info_cost': 100,
    'shop.booster_shot_cost': 100,
    'shop.loot_box_cost': 100,
    'shop.ticket_wager_minimum': 1,
    'shop.sponsorship_cost_per_point': 1,
    'shop.tournament_cost': 500,
    'shop.tournament_prize_split': {'first': 0.70, 'second': 0.20, 'third': 0.10},
    'shop.collusion_insurance_cost': 300,
    'shop.random_chaos_cost': 150,
    'shop.gambling_addiction_cost': 100,
    'shop.bounty_protection_cost': 200,
    'shop.leverage_insurance_cost': 250,
    'shop.strategic_timeout_cost': 400,
    
    # System (12 parameters)
    'system.match_expiry_hours': 24,
    'system.bounty_duration_hours': 48,
    'system.giant_slayer_elo_threshold': 200,
    'system.hot_streak_threshold': 3,
    'system.vig_percentage': 0.10,
    'system.elo_per_sigma': 200,
    'system.cache_ttl_hierarchy': 900,
    'system.cache_ttl_shop': 300,
    'system.cache_ttl_profile': 30,
    'system.cache_max_size': 1000,
    'system.owner_discord_id': None,
    'system.admin_role_name': 'tournament-admin',
    'system.moderator_role_name': 'tournament-mod',
    
    # Leaderboard System (17 parameters)
    'leaderboard_system.base_elo': 1000,
    'leaderboard_system.elo_per_sigma': 200,
    'leaderboard_system.min_population_size': 3,
    'leaderboard_system.default_std_dev_fallback': 1.0,
    'leaderboard_system.max_z_score_limit': 5.0,
    'leaderboard_system.statistical_confidence_level': 0.95,
    'leaderboard_system.weekly_reset_day': 6,
    'leaderboard_system.weekly_reset_hour': 23,
    'leaderboard_system.weekly_reset_timezone': 'UTC',
    'leaderboard_system.automated_processing_enabled': False,
    'leaderboard_system.cache_ttl_scores': 300,
    'leaderboard_system.cache_ttl_statistics': 900,
    'leaderboard_system.batch_calculation_size': 100,
    'leaderboard_system.max_concurrent_calculations': 5,
    'leaderboard_system.score_submission_rate_limit': 10,
    'leaderboard_system.outlier_detection_enabled': True,
    'leaderboard_system.historical_data_retention_weeks': 52,
    
    # Rate Limits (5 parameters)
    'rate_limits.detailed_profile_cooldown': 30,
    'rate_limits.head_to_head_cooldown': 60,
    'rate_limits.recent_form_cooldown': 45,
    'rate_limits.performance_trends_cooldown': 90,
    'rate_limits.admin_bypass_enabled': True,
    
    # Game Mechanics (12 parameters)
    'game_mechanics.lifesteal_percentage': 0.20,
    'game_mechanics.lifesteal_max_steal': 500,
    'game_mechanics.forced_leverage_gain_mult': 1.5,
    'game_mechanics.forced_leverage_loss_mult': 0.5,
    'game_mechanics.veto_decision_timeout': 30,
    'game_mechanics.booster_shot_payout_bonus': 0.10,
    'game_mechanics.insider_info_max_uses': 3,
    'game_mechanics.loot_box_min_reward': 1,
    'game_mechanics.loot_box_max_reward': 200,
    'game_mechanics.bounty_duration_hours': 48,
    'game_mechanics.match_effect_reveal_delay': 2,
    'game_mechanics.effect_animation_duration': 5,
}

async def seed_configurations():
    """Seed all initial configuration values."""
    db = Database()
    await db.initialize()
    
    async with db.get_session() as session:
        for key, value in INITIAL_CONFIGS.items():
            # Use merge to insert or update
            config = Configuration(key=key, value=json.dumps(value))
            await session.merge(config)
        
        await session.commit()
        print(f"Seeded {len(INITIAL_CONFIGS)} configuration parameters")

def get_categories_summary():
    """Get summary of configuration categories."""
    categories = {}
    for key in INITIAL_CONFIGS.keys():
        if '.' in key:
            category = key.split('.', 1)[0]
            categories[category] = categories.get(category, 0) + 1
    return categories

if __name__ == "__main__":
    print("Configuration Categories Summary:")
    for category, count in get_categories_summary().items():
        print(f"  {category}: {count} parameters")
    print(f"\nTotal: {len(INITIAL_CONFIGS)} parameters")
    
    # Run seeding
    asyncio.run(seed_configurations())