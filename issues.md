# Known Issues & Technical Debt

## Performance Optimizations Needed

### Profile Command Performance (Priority: Medium)
**Issue**: Profile command works but has performance regressions introduced during Phase 3.2 fixes.

**Root Cause**: After fixing the missing `calculate_cluster_elo` method in `CachedEloHierarchyService`, profile generation now performs redundant calculations.

**Technical Details**:
1. **Double Calculations**: `ProfileService.get_profile_data()` calls both:
   - `elo_hierarchy_service.get_hierarchy()` (line 97) 
   - `elo_hierarchy_service.calculate_cluster_elo()` (line 173)
   - These trigger the same calculation chain internally, causing 2x database queries per profile view

2. **Discarded Values Bug**: Fresh calculations are computed (lines 98-99) but ignored:
   - `calculated_overall_raw_elo` and `calculated_overall_scoring_elo` calculated but unused
   - ProfileData construction (lines 128-129) uses stale database values instead
   - May show slightly outdated Elo values despite recalculating them

**Impact**: 
- Slower profile load times (~2x database overhead)
- Potential display of outdated Elo values
- Wasted computational resources

**Files Affected**:
- `/bot/services/profile.py` (lines 97, 173, 128-129)
- `/bot/services/elo_hierarchy_cache.py` (lines 72-85)
- `/bot/operations/elo_hierarchy.py` (line 247)

**Recommended Fix**: 
1. Reuse `cluster_elos` from `get_hierarchy()` call instead of recalculating
2. Use `calculated_overall_raw_elo`/`calculated_overall_scoring_elo` in ProfileData construction
3. Pass cluster data to `_fetch_cluster_stats()` to avoid second DB query

**Status**: Working but non-optimal - can be optimized in future iteration

---

## Code Quality Issues

### Code Duplication (Priority: Low)
**Issue**: Overall Elo calculation logic exists in two places:
- `ProfileService._calculate_overall_elo()` (lines 222-271)
- `EloHierarchyCalculator._calculate_overall_from_cluster_elos()` (lines 179-217)

**Impact**: Maintenance burden, potential algorithm drift

**Recommended Fix**: Remove duplicate implementation, centralize in EloHierarchyCalculator

### Minor Quality Issues
1. **Logger Creation**: `logging.getLogger(__name__)` created on every call in elo_hierarchy.py:171
2. **Production-Unsafe Assert**: Line 85 uses `assert` which can be stripped in production - should use `ValueError`
3. **Duplicate Helper Methods**: `_format_current_streak` and `_format_current_streak_value` implement identical logic

---

## Notes
- All core functionality works correctly
- Cluster Elo calculation fixes from Phase 3.2 are preserved and working
- These are optimization opportunities, not blocking issues
- Profile command is fully functional for users