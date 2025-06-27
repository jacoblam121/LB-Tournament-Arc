# Test Documentation: Subphase 2 - EventBrowserView Foundation

## Overview
This document provides manual testing procedures for the EventBrowserView foundation implementation in Subphase 2. The EventBrowserView replaces the static `/list-events` command with an interactive UI featuring filtering and pagination.

## Prerequisites
- Bot is running with active database connection
- CSV data has been populated (use `/admin-populate-data` if needed)
- Test user has appropriate permissions
- At least 15+ events across multiple clusters for comprehensive testing

## Test Suite

### Test 1: Basic Interactive View Launch
**Objective:** Verify the EventBrowserView launches correctly via slash command

**Steps:**
1. Use slash command: `/list-events`
2. Wait for initial response

**Expected Results:**
- Interactive embed appears with "Tournament Events" title
- Two dropdown menus appear: "Filter by cluster..." and "Filter by event type..."
- Navigation buttons appear: "◀ Previous", "Next ▶", "🏠 Home"
- Events are displayed with numbered list (1-10 if more than 10 exist)
- Admin users see status indicators (🟢/🔴) and "(Admin View)" in title
- Footer shows pagination info if more than 10 events exist

**Pass/Fail:** ___

### Test 2: Cluster Filtering
**Objective:** Test cluster dropdown filtering functionality

**Steps:**
1. Launch `/list-events`
2. Click "Filter by cluster..." dropdown
3. Select a specific cluster (not "All Clusters")
4. Wait for view update

**Expected Results:**
- Dropdown shows "All Clusters" option at top
- All available clusters listed with numbers (e.g., "Cluster 1")
- Admin users see status indicators (🟢/🔴) in cluster names
- After selection, events filtered to only show from selected cluster
- Title updates to show filter: "Tournament Events - Cluster: [Name]"
- Page resets to 1
- Previous button disabled if on first page

**Pass/Fail:** ___

### Test 3: Event Type Filtering
**Objective:** Test event type dropdown filtering functionality

**Steps:**
1. Launch `/list-events`
2. Click "Filter by event type..." dropdown
3. Select a specific type (e.g., "1v1", "FFA", "Team", or "Leaderboard")
4. Wait for view update

**Expected Results:**
- Dropdown shows "All Types" option at top
- Available event types listed: "1v1", "FFA", "Team", "Leaderboard"
- After selection, events filtered to only show selected type
- Title updates to show filter: "Tournament Events - Type: [Type]"
- Page resets to 1
- Event count adjusts based on filter

**Pass/Fail:** ___

### Test 4: Combined Filtering
**Objective:** Test using both cluster and event type filters simultaneously

**Steps:**
1. Launch `/list-events`
2. Select a specific cluster from cluster dropdown
3. Select a specific event type from event type dropdown
4. Verify combined filtering works

**Expected Results:**
- Title shows both filters: "Tournament Events - Cluster: [Name], Type: [Type]"
- Only events matching BOTH criteria are displayed
- Pagination adjusts to filtered results
- Home button becomes enabled (no longer disabled)

**Pass/Fail:** ___

### Test 5: Pagination Navigation
**Objective:** Test Previous/Next button functionality

**Prerequisites:** Ensure test data has 15+ events

**Steps:**
1. Launch `/list-events` (ensure multiple pages exist)
2. Click "Next ▶" button
3. Verify page 2 content
4. Click "◀ Previous" button
5. Verify return to page 1

**Expected Results:**
- Next button advances to page 2
- Event numbers update (11-20 on page 2)
- Previous button becomes enabled on page 2
- Footer updates: "Page 2 of X"
- Previous button returns to page 1 correctly
- Previous button disabled on page 1
- Next button disabled on final page

**Pass/Fail:** ___

### Test 6: Home/Reset Functionality
**Objective:** Test the Home button that clears all filters

**Steps:**
1. Launch `/list-events`
2. Apply cluster filter
3. Apply event type filter
4. Navigate to page 2+ (if available)
5. Click "🏠 Home" button

**Expected Results:**
- All filters cleared (cluster and event type reset to "All")
- Page resets to 1
- Title returns to "Tournament Events" (no filter text)
- Home button becomes disabled again
- Full event list displayed without filters

**Pass/Fail:** ___

### Test 7: Permission-Based Display (Admin View)
**Objective:** Verify admin users see enhanced information

**Prerequisites:** Test with bot owner account

**Steps:**
1. Launch `/list-events` with admin account
2. Observe enhanced features
3. Compare with regular user view

**Expected Results (Admin View):**
- Title includes "(Admin View)"
- Status indicators visible: 🟢 for active, 🔴 for inactive
- Cluster dropdown shows status indicators for clusters
- Event list shows status indicators for events
- Footer includes count summary: "Showing X events (Y active)"
- Inactive events/clusters visible if they exist

**Pass/Fail:** ___

### Test 8: Empty States
**Objective:** Test behavior when no events match filters

**Steps:**
1. Launch `/list-events`
2. Apply filters that result in no matches (e.g., very specific cluster + event type combination)

**Expected Results:**
- Message displays: "No events match the current filters."
- Navigation buttons handle empty state gracefully
- Filters remain applied and functional
- Home button still works to reset

**Pass/Fail:** ___

### Test 9: Error Handling
**Objective:** Test error handling during interaction failures

**Steps:**
1. Launch `/list-events`
2. Rapidly click multiple buttons/dropdowns
3. Test interaction during potential database delays

**Expected Results:**
- No crashes or unhandled exceptions
- Error messages display as ephemeral responses if failures occur
- View remains functional after error recovery
- Timeout handled gracefully (5-minute limit)

**Pass/Fail:** ___

### Test 10: Hybrid Command Behavior
**Objective:** Verify prefix command falls back to static display

**Steps:**
1. Use prefix command: `!list-events`
2. Compare with slash command behavior
3. Test prefix command with cluster parameter: `!list-events "Cluster Name"`

**Expected Results (Prefix Command):**
- Static embed displayed (no interactive components)
- Simplified event list with cluster grouping
- Helpful tip about using slash command for interactive version
- Cluster parameter filtering works for prefix version
- No performance issues with static display

**Pass/Fail:** ___

### Test 11: Performance and Responsiveness
**Objective:** Verify UI responsiveness and reasonable load times

**Steps:**
1. Launch `/list-events` with large dataset
2. Test filter changes and pagination speed
3. Monitor for delays or timeouts

**Expected Results:**
- Initial load completes within 3 seconds
- Filter changes respond within 1 second
- Pagination changes respond within 1 second
- No Discord timeout errors (15-second interaction limit)
- Memory usage reasonable

**Pass/Fail:** ___

## Test Results Summary

| Test | Pass/Fail | Notes |
|------|-----------|-------|
| 1. Basic Launch | ___ | |
| 2. Cluster Filtering | ___ | |
| 3. Event Type Filtering | ___ | |
| 4. Combined Filtering | ___ | |
| 5. Pagination | ___ | |
| 6. Home/Reset | ___ | |
| 7. Admin View | ___ | |
| 8. Empty States | ___ | |
| 9. Error Handling | ___ | |
| 10. Hybrid Commands | ___ | |
| 11. Performance | ___ | |

## Known Issues to Address
Based on code review findings:

1. **Performance Issue (HIGH):** In-memory filtering may cause delays with large datasets
2. **Potential AttributeError (MEDIUM):** event.cluster.name access needs null check
3. **UI Polish (LOW):** Home button state logic could be cleaner

## Additional Notes
- If any test fails, document the specific behavior observed
- Note any console errors or exceptions in bot logs
- Test with various data sizes (empty, small, large datasets)
- Verify behavior with both active and inactive events/clusters

## Post-Testing Checklist
- [ ] All core functionality working as expected
- [ ] No critical bugs or crashes observed
- [ ] Performance acceptable for expected data volumes
- [ ] Error handling graceful and user-friendly
- [ ] Admin features properly restricted and functional
- [ ] Hybrid command approach working correctly