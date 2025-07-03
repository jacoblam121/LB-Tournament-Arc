Of course. This is the master plan.
Here is the complete, unabridged, and exceptionally detailed blueprint for the "Culling Games" Discord bot. This document consolidates every decision, formula, and workflow we have discussed, designed to be the single source of truth for the project.

***

## **The Culling Games: Master Project Blueprint**

### **Table of Contents**

1.  [**Part 1: The Vision & Philosophy**](#part-1-the-vision--philosophy)
    *   1.1. The Big Idea
    *   1.2. Guiding Principles
2.  [**Part 2: The Core Scoring Engine**](#part-2-the-core-scoring-engine)
    *   2.1. The Foundational Elo Formula
    *   2.2. The Dual-Track Elo System: Raw vs. Scoring Elo
    *   2.3. The Scoring Pyramid: A Hierarchical Overview
    *   2.4. Level 1: Event Elo & Match Types
    *   2.5. Level 2: Cluster Elo & "Prestige Weighting"
    *   2.6. Level 3: Overall Elo & "Weighted Generalist"
3.  [**Part 3: The Meta-Game Systems**](#part-3-the-meta-game-systems)
    *   3.1. The Shard of the Crown: The Activated King's Bounty
    *   3.2. The Ticket Economy: Fuel for Strategy
    *   3.3. The Leverage System: High-Stakes Manipulation
4.  [**Part 4: The Discord Bot Interface (UI/UX)**](#part-4-the-discord-bot-interface-uiux)
    *   4.1. The Profile Command: The Culling Games Passport
    *   4.2. The Leaderboard Command: The Sortable Data Hub
    *   4.3. The Match Command Suite
    *   4.4. The Economy Command Suite
5.  [**Part 5: Administration & Logistics**](#part-5-administration--logistics)
    *   5.1. The Game Master Role & Permissions
    *   5.2. The Revert Match Command: The Safety Net
    *   5.3. Season Management
6.  [**Part 6: Database & Technical Architecture**](#part-6-database--technical-architecture)
    *   6.1. Core Data Models
    *   6.2. Data Integrity Principles

***

### **Part 1: The Vision & Philosophy**

#### **1.1. The Big Idea**

The "Culling Games" is not merely a tournament bot; it is a framework for a season-long, server-wide meta-competition. Its purpose is to definitively crown a server champion by measuring skill across a vast and diverse range of activities. The system is built to reward both pure, specialized skill and clever, strategic manipulation of the game itself, creating a dynamic and engaging path to victory.

#### **1.2. Guiding Principles**

*   **Skill vs. Strategy:** The final victor will be the person who masters both the games themselves and the meta-game that surrounds them.
*   **The Ultimate Generalist:** The scoring systems are explicitly designed to reward players who are competent across many different genres, disincentivizing over-specialization in a single area.
*   **Total Transparency:** The path to victory must be clear. All scoring is broken down and made visible, allowing players to understand exactly where their points originate—raw skill, strategic purchases, or special bonuses.
*   **High-Stakes & High-Drama:** The mechanics are designed to create memorable moments, intense rivalries, and dramatic comebacks through features like bounties, forced high-stakes matches, and a king-of-the-hill style bonus.
*   **Player Morale & Engagement:** The system includes a "scoring floor" to prevent players from feeling overly punished by losses, encouraging continued participation even after a losing streak.

***

### **Part 2: The Core Scoring Engine**

This is the mathematical heart of the Culling Games. All scoring flows through this multi-layered, hierarchical system.

#### **2.1. The Foundational Elo Formula**

All competitive calculations are based on the standard Elo rating system.

*   **Expected Score Formula:**
    `E_A = 1 / (1 + 10^((R_B - R_A) / 400))`
    *   `E_A`: Player A's probability of winning (from 0.0 to 1.0).
    *   `R_A`: Player A's current rating.
    *   `R_B`: Player B's current rating.

*   **Rating Change Formula:**
    `ΔR_A = K × (S_A - E_A)`
    *   `ΔR_A`: The change in Player A's rating.
    *   `K`: The K-factor, determining rating volatility.
    *   `S_A`: The actual score of the match (1.0 for a win, 0.5 for a draw, 0.0 for a loss).
    *   `E_A`: The expected score calculated above.

*   **K-Factor System:**
    *   **Provisional ( < 5 matches in an Event):** `K = 40`. Allows new players to quickly approach their true rating.
    *   **Established ( ≥ 5 matches in an Event):** `K = 20`. Provides stability for experienced players.

#### **2.2. The Dual-Track Elo System: Raw vs. Scoring Elo**

To protect player morale while maintaining data integrity, every player has two parallel Elo values at every level.

1.  **Raw Elo:** The true, unfiltered skill rating. This value can drop indefinitely and is used for historical tracking and pure skill analysis. It represents what a player's skill *actually is*.
2.  **Scoring Elo:** The value used for all official leaderboard calculations and the final score. It is "floored" at the starting baseline Elo to prevent punitive scoring. It represents a player's *official standing* in the games.

*   **The Rule (The "Floor"):**
    `Scoring Elo = max(Raw Elo, STARTING_ELO)`
    *   `STARTING_ELO`: A global constant, set to `1000`.

This calculation is applied at the lowest level—the Event Elo—and propagates upward through the entire scoring pyramid.

#### **2.3. The Scoring Pyramid: A Hierarchical Overview**

The system is structured as a pyramid, with each level feeding into the next:
*   **Level 3 (Peak):** Overall Raw Elo & Overall Scoring Elo
*   **Level 2 (Mid-Tier):** Cluster Elo (Calculated from Events)
*   **Level 1 (Foundation):** Event Elo (Calculated from Matches)

#### **2.4. Level 1: Event Elo & Match Types**

This is the foundational layer where individual game results are processed. Each game in the "Culling Games List" is a unique `Event` with its own Elo leaderboard.

## Clarification on per-event elo ratings
Events are classfied as each game mode from the LB Culling Games List.csv. The match types are just multiple ways to gain elo in that event. So Diep (1v1), Diep(FFA), and Diep(Team) would NOT have separate elos. They would all share ONE elo under the Diep event. There are simply multiple ways to gain/lose elo in that event. 

*   **1v1 Matches:**
    *   **Calculation:** The standard Elo formula (`ΔR = K × (S - E)`) is applied directly. The winner gains points, the loser loses an equal amount.

*   **FFA (Free-For-All) Matches:**
    *   **Concept:** The match is broken down into a series of "pairwise" 1v1 duels.
    *   **Process:**
        1.  For an N-player match, `N * (N-1) / 2` pairwise comparisons are made.
        2.  For each pair of players (A, B), the higher-placing player gets a "win" (`S=1.0`) and the lower-placing player gets a "loss" (`S=0.0`).
        3.  The standard Elo formula is run for *each of these pairs*.
        4.  To prevent massive Elo swings, the K-factor is scaled: `K_scaled = K / (N - 1)`. This scaled K-factor is used in all calculations for this match.
        5.  Each player's total Elo change is the sum of the changes from all of their individual pairwise comparisons.

*   **Team Matches (e.g., 2v2):**
    *   **Concept:** Each team is treated as a single entity with an average rating.
    *   **Number of Teams:** There will only ever be two teams (3 teams is not necessary for any event)
    *   **Process:**
        1.  Calculate the average Elo of Team A (`R_TeamA = (R_PlayerA1 + R_PlayerA2) / 2`).
        2.  Calculate the average Elo of Team B (`R_TeamB = (R_PlayerB1 + R_PlayerB2) / 2`).
        3.  Run a single 1v1 Elo calculation between these two average ratings (`R_TeamA` vs. `R_TeamB`) to get a single Elo change value, `ΔR`.
        4.  Apply this change individually to every player. Winners: `R_new = R_old + ΔR`. Losers: `R_new = R_old - ΔR`.

*   **Leaderboard Events:**
    *   **Concept:** These are asynchronous events based on scores or times. The Elo calculation is unique.
    *   **Calculation:** `Event Elo = (All_Time_Best_Score_Elo * 0.5) + (Average_Weekly_Reset_Elo * 0.5)`
        *   A formula will be needed to convert raw scores (e.g., seconds, points) into an "Elo-equivalent" score for this calculation.
        *   If a player does not participate in a weekly reset, their score for that week is `0`, dragging down their average.

*   **Draws:** As per the design decision, draws are not explicitly handled. Players are expected to cancel the match report or replay the match.

#### **2.5. Level 2: Cluster Elo & "Prestige Weighting"**

The `Cluster Elo` aggregates a player's performance across all `Events` within a thematic `Cluster`. It uses a weighted average to heavily reward mastery in a player's top events.

*   **The "Prestige Multipliers":**
    *   **Rank 1 Event (Best score in cluster):** `4.0x`
    *   **Rank 2 Event:** `2.5x`
    *   **Rank 3 Event:** `1.5x`
    *   **Rank 4+ Events:** `1.0x`

*   **Calculation Process:**
    1.  **Sort:** For a player, sort all their Event Elo scores within a cluster from highest to lowest.
    2.  **Apply Multipliers:** Assign the appropriate Prestige Multiplier to each Elo score based on its rank.
    3.  **Calculate Raw Prestige:** For each event, `Raw Prestige Value = Event_Elo * Multiplier`.
    4.  **Sum & Normalize:**
        *   `Total Raw Prestige = Σ (All Raw Prestige Values)`
        *   `Total Multiplier = Σ (All Assigned Multipliers)`
    5.  **Final Cluster Elo:** `Cluster Elo = Total Raw Prestige / Total Multiplier`

*   **Example (5-Event Cluster):**
    *   Scores: 2000, 1900, 1750, 1600, 1550
    *   Multipliers: 4.0, 2.5, 1.5, 1.0, 1.0
    *   Total Multiplier: 10.0
    *   Total Raw Prestige: `(2000*4) + (1900*2.5) + (1750*1.5) + (1600*1) + (1550*1) = 8000 + 4750 + 2625 + 1600 + 1550 = 18525`
    *   Cluster Elo: `18525 / 10.0 = 1852.5`
    *   *Note:* This process is run twice—once with `Raw Event Elos` to get `Raw Cluster Elo`, and once with `Scoring Event Elos` to get `Scoring Cluster Elo`.

#### **2.6. Level 3: Overall Elo & "Weighted Generalist"**

The `Overall Elo` is the final aggregation, designed to reward players who are competent across many different clusters. It uses a tiered weighting system.

*   **The Tiers & Weights:**
    *   **Tier 1 (Ranks 1-10):** The average of a player's 10 best Cluster Elos. **Weight: 60%**.
    *   **Tier 2 (Ranks 11-15):** The average of the next 5 best Cluster Elos. **Weight: 25%**.
    *   **Tier 3 (Ranks 16-20):** The average of the final 5 Cluster Elos. **Weight: 15%**.
    *   *Note:* Any cluster a player has not participated in will use the `STARTING_ELO` (1000) for this calculation.

*   **Calculation Process:**
    1.  **Sort:** Take all 20 of a player's Cluster Elo scores and sort them from highest to lowest.
    2.  **Calculate Tier Averages:**
        *   `Avg_T1 = Average(Scores at Ranks 1-10)`
        *   `Avg_T2 = Average(Scores at Ranks 11-15)`
        *   `Avg_T3 = Average(Scores at Ranks 16-20)`
    3.  **Final Overall Elo:**
        `Overall Elo = (Avg_T1 * 0.60) + (Avg_T2 * 0.25) + (Avg_T3 * 0.15)`
    *   *Note:* This process is run twice—once with `Raw Cluster Elos` to get `Overall Raw Elo`, and once with `Scoring Cluster Elos` to get `Overall Scoring Elo`.

***

### **Part 3: The Meta-Game Systems**

These systems sit on top of the core scoring engine and allow for strategic manipulation of the game.

#### **3.1. The Shard of the Crown: The Activated King's Bounty**

A special system designed to challenge the server owner (the "King").

*   **Mechanism:** Each of the 20+ `Events` has a dormant `300 Elo` bonus pool.
*   **Activation:** The bonus pool for an event is **activated only when the first match against the King is played in that event.**
*   **King's Claim:** If, after activation, the King remains undefeated in that event for the entire season, they claim the full `300 Elo` bonus at the final tally.
*   **Player's Claim:** The moment any player beats the King in that event, the King's potential claim is permanently voided. The bonus pool is now owned by the players.
*   **Distribution:** At the end of the season, the `300 Elo` pool for an event is divided equally among all players who have beaten the King in that event. This bonus is added directly to their `Final Score` calculation.

#### **3.2. The Ticket Economy: Fuel for Strategy**

Tickets are the in-game currency, earned through participation and skillful play, and spent on game-altering advantages.

*   **Earning Tickets (Examples):**
    *   **Participation:** Playing a match (`+5`), playing your first match (`+50`).
    *   **Skill:** Winning against a much higher-rated opponent (`+25`), winning 3 matches in a row (`+50`).
    *   **Milestones:** Playing a match in every cluster (`+250`).

*   **Spending Tickets (Examples):**
    *   **Score Manipulation:** Directly buying points towards the `Final Score`.
    *   **Social Engineering:** Placing bounties on other players.
    *   **System Influence:** Sponsoring tournaments, hiding your Elo, using Leverage.

#### **3.3. The Leverage System: High-Stakes Manipulation**

This system allows players to raise the stakes of a match.

*   **Database Requirement:** The `Player` model needs an `active_leverage_token` field.
*   **Workflow:**
    1.  **Purchase & Activation:** A player buys a leverage token from the `/shop` and activates it via `/toggle-leverage`. The `active_leverage_token` field is updated (e.g., to `2x_standard` or `1.5x_forced`).
    2.  **Consumption:** The token is consumed when the player **initiates** their next match.
    3.  **The Reveal:**
        *   **Standard Leverage:** The match creation message explicitly states the leverage (e.g., "This is a 2x Elo Match!"). The multiplied Elo is shown in the final result.
        *   **Forced Leverage:** The match creation message is normal. The final result embed shows the *base* Elo change, followed by a separate, dramatic message revealing the forced leverage and the adjusted final scores.
    4.  **Cleanup:** After the match is finalized, the player's `active_leverage_token` is set back to `NULL`.

***

### **Part 4: The Discord Bot Interface (UI/UX)**

This section details the user-facing commands and interactive menus.

#### **4.1. The Profile Command: The Culling Games Passport**

*   **Command:** `/profile [@user]`
*   **Initial View (The "Passport"):** A high-level summary embed showing:
    *   Final Score, Server Rank, Ticket Balance.
    *   Overall Scoring Elo, Overall Raw Elo.
    *   Season Record (W-L-D) and conditional Streak (only shows if >= 3).
    *   Top 3 and Bottom 3 Clusters for a quick glance at strengths/weaknesses.
*   **Interactive Components:**
    *   **Buttons:** `[Clusters Overview]`, `[Match History]`, `[Ticket Ledger]`, `[View on Leaderboard]`.
    *   **Select Menu:** A dropdown listing all clusters to drill down into.
*   **Drill-Down Views:** Clicking a button or menu item edits the original message to show a detailed, paginated view of Cluster Elos, individual Event Elos (with 💀 emoji for sub-1000 Raw Elo), Match History, or Ticket Ledger. A `[Back to Main Profile]` button allows for easy navigation.

#### **4.2. The Leaderboard Command: The Sortable Data Hub**

*   **Command:** `/leaderboard [--sort=column_name]`
*   **Display:** A paginated embed showing the top players. Each row contains:
    *   `Rank`
    *   `Player Name`
    *   `Final Score` (Default sort)
    *   `Overall Scoring Elo`
    *   `Overall Raw Elo`
    *   `Shard Bonus`
    *   `Shop Bonus`
*   **Functionality:** The `--sort` parameter (or interactive buttons) allows users to re-rank the view by any of the displayed columns, providing deep analytical insight into the state of the competition.

#### **4.3. The Match Command Suite**

*   **Creation:** `/challenge`,  will create a `Match` record and return a `match_id`.
*   **Reporting (`/match-report [match_id]`):**
    *   This is an intelligent, context-aware command.
    *   The bot looks up the `match_id`, determines the `scoring_type`, and presents the appropriate interface (buttons for 1v1/Team, placement modal for FFA, score input for Leaderboard).

#### **4.4. The Economy Command Suite**

*   `/shop`: Displays a paginated list of purchasable items from the Ticket System.
*   `/buy [item_id]`: Initiates the purchase workflow for a specific item.
*   `/toggle-leverage`: Allows a player to arm or disarm a purchased leverage token.
*   `/inventory`: Shows a player their currently owned/active items.

***

### **Part 5: Administration & Logistics**

These are the essential tools for the Game Master to run the competition smoothly.

#### **5.1. The Game Master Role & Permissions**

*   All administrative commands are locked to a specific Discord UID (the Game Master), ensuring only the authorized user can modify the game state.

#### **5.2. The Revert Match Command: The Safety Net**

*   **Command:** `!admin-revert-match [match_id]`
*   **Function:** An atomic, all-or-nothing database transaction that:
    1.  Finds the match and all associated data.
    2.  Reverses all Elo changes, ticket transactions, and W/L/D stats for all participants.
    3.  Re-calculates player streaks.
    4.  Deletes the `Match`, `MatchParticipant`, `EloHistory`, and `TicketLedger` records associated with the match ID.
    5.  Confirms the successful rollback to the Game Master.

#### **5.3. Season Management**

*   **`!season-end`:** Freezes all scoring and match reporting. Calculates final bonuses and declares the winner.
*   **`!season-archive`:** Saves the final state of all leaderboards and player stats to historical tables.
*   **`!season-reset`:** Resets all `Player` Elo scores to `STARTING_ELO`, wipes match history, and clears ticket balances to prepare for a new season.

***

### **Part 6: Database & Technical Architecture**

#### **6.1. Core Data Models (Simplified)**

*   **`Player`:** `discord_id`, `display_name`, `tickets`, `active_leverage_token`, streak data.
*   **`Cluster`:** `cluster_id`, `name`.
*   **`Event`:** `event_id`, `name`, `cluster_id`, `scoring_type`.
*   **`PlayerEventStats`:** `player_id`, `event_id`, `raw_elo`, `scoring_elo`, `matches_played`, `wins`, `losses`.
*   **`Match`:** `match_id`, `event_id`, `status`, `timestamp`.
*   **`MatchParticipant`:** `match_participant_id`, `match_id`, `player_id`, `placement`, `elo_before`, `elo_after`, `elo_change`.
*   **`TicketLedger`:** `transaction_id`, `player_id`, `amount`, `reason`, `timestamp`.
*   **`EloHistory`:** `history_id`, `player_id`, `event_id`, `match_id`, `elo_before`, `elo_after`, `change_amount`.

#### **6.2. Data Integrity Principles**

*   **Atomic Transactions:** All operations that modify multiple tables (like reporting a match or reverting it) are wrapped in atomic transactions to prevent partial updates and data corruption.
*   **Player Retention (The "Ghost Player" Policy):** When a user leaves the Discord server, their `Player` data is **never deleted**. It is preserved in its entirety, ensuring leaderboards remain stable and historical data is accurate. If the user rejoins, their stats are immediately available.
*   **Constants:** Key values like `STARTING_ELO` and K-factors are defined as global constants in the code for easy tuning and consistency.


Excellent questions. These additions address two critical aspects of running a living, breathing competition: administrative flexibility and providing more avenues for player-to-player interaction. You are right to identify these as potential gaps.

Let's integrate these systems into the master blueprint with the same level of extreme detail.

---

### **ADDENDUM A: Administrative & Betting Systems**

This addendum expands on **Part 5: Administration & Logistics** and adds a new dimension to **Part 3: The Meta-Game Systems**.

### **5.4. Administrative Ticket Management**

To handle out-of-game rewards, correct errors, or apply manual penalties, the Game Master requires direct control over player ticket balances.

#### **5.4.1. The Admin Ticket Command Suite**

A dedicated suite of commands, locked to the Game Master's UID, provides this functionality. The commands are designed for clarity, accountability, and safety.

*   **Command Structure:** `!admin-tickets [subcommand] [@user] [amount] [reason]`
    *   `!admin-tickets add @user <amount> [reason]`: Adds a specified number of tickets to a user's balance.
    *   `!admin-tickets set @user <amount> [reason]`: Sets a user's ticket balance to an absolute value.
    *   `!admin-tickets remove @user <amount> [reason]`: Removes a specified number of tickets from a user's balance.

#### **5.4.2. Backend Logic & Accountability**

Every use of these commands is a formal, logged transaction.

1.  **Authorization:** The bot first verifies that the command author's Discord UID matches the `GAME_MASTER_UID` constant.
2.  **Input Validation:** The bot ensures the `<amount>` is a positive integer and that the target user exists.
3.  **Atomic Transaction:** The bot initiates a database transaction.
4.  **Player Update:** It modifies the `player.tickets` field in the `Player` model according to the subcommand.
5.  **Ledger Entry:** A new entry is created in the `TicketLedger` table. Crucially, the `reason` field is populated with a combination of the admin's provided reason and a prefix indicating it was a manual override.
    *   **Example `reason` log for `!admin-tickets add @Bob 100 "IRL Event Winner"`:** `ADMIN GRANT: IRL Event Winner`
    *   **Example `reason` log for `!admin-tickets set @Charlie 500 "Manual balance correction"`:** `ADMIN SET: Manual balance correction`
6.  **Confirmation:** The bot sends an ephemeral (visible only to the admin) confirmation message: "✅ Success. @Bob's ticket balance has been increased by 100. New balance: 600. The transaction has been logged."

This system provides the necessary flexibility while ensuring every administrative action is transparent and traceable through the `TicketLedger`.

---

### **3.4. The Pari-mutuel Betting System ("The Alex Moment")**

To allow players to wager on the outcome of matches, the bot will implement a pari-mutuel betting system. This system is fair, self-balancing, and eliminates the need for the "house" to set odds. All bets go into a pool, a small house cut (the "vigorish" or "vig") is taken, and the remaining prize pool is distributed among the winners.

#### **3.4.1. The Betting Workflow: From Challenge to Payout**

1.  **The Betting Window Opens:**
    *   When a standard, bet-eligible match (primarily 1v1) is created, the bot's confirmation message will include a call to action.
    *   **Bot Message:** "@Alice has challenged @Bob. Match ID: #1340. Good luck! **Bets are now open for this match!** Use `/bet 1340 ...` to place your wager."
    *   An interactive button `[Place a Bet]` is attached, which pre-fills the command for the user.

2.  **Placing a Bet:**
    *   **Command:** `/bet [match_id] [amount] [target_player]`
    *   **User Action:** A player types `/bet 1340 50 @Alice`.
    *   **Backend Logic:**
        a.  The bot validates that betting is still open for Match #1340.
        b.  It checks if the bettor has at least 50 tickets.
        c.  It escrows the tickets: The player's `tickets` balance is reduced by 50.
        d.  A new record is created in a `Bets` table, logging the `match_id`, the bettor's `player_id`, the `amount`, and the `chosen_winner_id` (@Alice).
        e.  The bot publicly confirms the bet, perhaps in a dedicated thread for that match, to build hype: "📈 **New Bet!** @Charlie has wagered 50 tickets on @Alice to win. The total pool is now 250 tickets."

3.  **The Betting Window Closes:**
    *   **Trigger:** The moment any participant in the match uses the `/match-report` command.
    *   **Action:** The bot immediately updates the `is_betting_open` flag for that match to `False`.
    *   **Bot Announcement:** In the match thread/channel: "🔒 **Betting is now closed for Match #1340.** The result has been submitted. Good luck to all bettors!"
    *   Any subsequent `/bet` commands for this `match_id` will be rejected.

4.  **Resolution & Payout:**
    *   **Trigger:** After the match result is fully confirmed by all parties.
    *   **Backend Payout Calculation:**
        a.  **Identify Winner:** The bot identifies the winning player of the match (e.g., @Bob).
        b.  **Calculate Total Pool:** Sum all bet amounts for this match from the `Bets` table. `Total Pool = 500 tickets`.
        c.  **Take the Vig:** A small percentage is taken for the "house" to remove tickets from the economy. Let's define `VIG_PERCENTAGE = 10%`.
            *   `Vig Amount = Total Pool * VIG_PERCENTAGE = 500 * 0.10 = 50 tickets`.
        d.  **Calculate Prize Pool:** `Prize Pool = Total Pool - Vig Amount = 500 - 50 = 450 tickets`.
        e.  **Calculate Winning Pool:** Sum all bets placed on the actual winner (@Bob). `Winning Pool = 150 tickets`.
        f.  **Distribute Winnings:** Iterate through every bettor who chose @Bob.
            *   **Payout Formula:** `Payout = (Their Bet / Winning Pool) * Prize Pool`
            *   A bettor who wagered 75 tickets on Bob would receive: `(75 / 150) * 450 = 0.5 * 450 = 225 tickets`.
        g.  **Transaction Logging:** For each winning bettor, their `tickets` balance is increased by their `Payout`, and a new entry is made in their `TicketLedger` (e.g., `REASON: Won bet on Match #1340`).
    *   **Public Announcement:** The bot makes a final, public announcement celebrating the outcome. "🎉 **Match #1340 Concluded!** @Bob is victorious! The 450 ticket prize pool has been distributed to the winning bettors. A huge congrats to @David who turned 75 tickets into 225!"

#### **3.4.2. Database & Architectural Requirements**

To support this system, the following database changes are required:

*   **`Match` Model Additions:**
    *   `is_betting_open` (Boolean, default `True` on creation).
    *   `betting_close_timestamp` (DateTime, set when `/report` is used).

*   **New `Bets` Table:**
    *   `bet_id` (Primary Key)
    *   `match_id` (Foreign Key to `Match`)
    *   `bettor_player_id` (Foreign Key to `Player`)
    *   `chosen_winner_player_id` (Foreign Key to `Player`)
    *   `amount` (Integer)
    *   `timestamp` (DateTime)

This detailed, pari-mutuel system creates a fair, engaging, and hype-generating side-game that perfectly complements the core competitive structure of the Culling Games.

Of course. These are excellent, concrete decisions that give the project a solid spine. Let's dive into the detailed mechanics of how each of these systems will work, from the user's perspective and the bot's backend logic.

---

### 1. The Match Reporting & Leverage System

This is the most frequent and critical user interaction. It needs to be seamless, intelligent, and dramatic.

#### **A. The Smart `/match-report [match_id]` Command**

The core principle is that the user provides the `match_id`, and the bot does all the heavy lifting to figure out what to ask next.

**User Workflow:**

1.  A match is created (e.g., via `/ffa`, `/challenge`, etc.). The bot responds with "Match #1337 has been created. Use `/match-report 1337` to submit the results."
2.  After the game, a participant types `/match-report 1337`.

**Bot's Backend Logic & Response:**

1.  **Lookup:** The bot queries its database for the `Match` with `id=1337`.
2.  **Contextualize:** From the `Match` record, it finds the associated `Event` and reads its `scoring_type` (e.g., 'FFA', '1v1', 'Leaderboard').
3.  **Adapt Interface:** The bot now presents a different interface based on the type:
    *   **If `scoring_type` is 'FFA':** The bot opens the familiar placement modal, dynamically generating a text input field for each of the registered participants.
    *   **If `scoring_type` is '1v1':** The bot responds with a message: "Who won the match between Player A and Player B?" attached with two buttons: `[ Player A Won ]` `[ Player B Won ]`.
    *   **If `scoring_type` is 'Team':** The bot responds with a message: "Which team won the match?" attached with two buttons representing the teams: `[ Team 1 Won ]` `[ Team 2 Won ]`.
    *   **If `scoring_type` is 'Leaderboard':** The bot responds with a message: "Please enter your score/time for this leaderboard event." and opens a simple modal with one input field.

This process makes reporting feel intuitive and intelligent, as the bot only ever asks for the specific information it needs for that game type.

#### **B. The Leverage System: State Management & Workflow**

This system requires the bot to track a player's "active leverage state."

**Database Change:** Your `Player` model will need a new field: `active_leverage_token` (e.g., can store text like `2x_standard`, `1.5x_forced`, or be `NULL` if none is active).

**The Workflow:**

1.  **Purchase:** A player buys a leverage item from the `/shop`. The bot adds the item to a theoretical player inventory (or a simple list of owned items).
2.  **Activation (The Toggle):**
    *   The player uses a new command: `/toggle-leverage`.
    *   The bot shows them a dropdown of their owned, inactive leverage items.
    *   The player selects "2x Leverage (Standard)." The bot sets their `player.active_leverage_token` to `2x_standard` and confirms: "✅ **2x Leverage is now ARMED.** It will be consumed on the next match you initiate."
    *   If they use `/toggle-leverage` again, they can choose to deactivate it, setting the token back to `NULL`.
3.  **Initiating a Match (The Consumption):**
    *   The player with the armed token **initiates a new match** (e.g., `/challenge @Bob`).
    *   The bot checks the initiator's `active_leverage_token`. It finds `2x_standard`.
    *   **Standard Leverage (The Open Threat):** The bot's match creation message is altered:
        > "⚠️ **LEVERAGE APPLIED!** @Alice has challenged @Bob to a **2x Elo Match!** Match ID: #1338. Good luck, players."
    *   **Forced Leverage (The Hidden Threat):** If the token was `1.5x_forced`, the bot's message would be normal, with no indication of leverage.
        > "@Alice has challenged @Bob. Match ID: #1339. Good luck, players."
4.  **Reporting & The Reveal:**
    *   The match is reported and confirmed as normal.
    *   **For Standard Leverage:** The final confirmation embed shows the multiplied Elo changes. "Final Elo: Alice: `+24`, Bob: `-24`."
    *   **For Forced Leverage (The Drama):** The confirmation embed shows the *base* Elo changes ("Alice: `+12`, Bob: `-12`"). Immediately after, the bot sends a **separate, dramatic message:**
        > "💥 **FORCED LEVERAGE REVEALED!** @Alice used a 1.5x Forced Leverage token. The final Elo changes have been adjusted."
5.  **Cleanup:** In both cases, once the match is finalized, the bot's logic applies the correct multiplier and immediately sets the player's `active_leverage_token` back to `NULL`. The token is consumed.

---

### 2. The Admin "Safety Net": Reverting a Match

This is a critical function for maintaining the integrity of the game. It must be a precise, multi-step database transaction.

**Command:** `!admin-revert-match [match_id]` (using `!` prefix for admin commands is a good convention).

**Bot's Backend Logic (An Atomic Transaction):**

When the command is run, the bot will execute the following steps in an "all or nothing" transaction. If any step fails, the entire process is rolled back.

1.  **Find the Records:** Locate the `Match` with the given ID and all of its associated `MatchParticipant` records.
2.  **Reverse Player Stats:** For each `MatchParticipant`:
    *   Read the `elo_change` and `ticket_change` values stored from the original transaction.
    *   Find the corresponding `Player`.
    *   Update the `Player`'s main stats: `player.elo -= elo_change`, `player.tickets -= ticket_change`.
    *   Decrement `player.matches_played` by 1.
    *   Correct the W/L/D record (e.g., if it was a win, decrement `wins` by 1).
3.  **Reverse Streaks:** Re-calculate the player's streak based on the now-second-to-last match.
4.  **Delete History:** Delete the `EloHistory`, `TicketLedger`, and any other log entries associated with this specific `match_id`.
5.  **Delete Match Data:** Delete the `MatchParticipant` records and finally, the parent `Match` record itself.
6.  **Confirm to Admin:** The bot sends a private message to the admin: "✅ **Success.** Match #1337 has been completely reverted. All player stats, Elo, and tickets from that match have been restored to their previous state. The players can now re-report the match."

---

### 3. Player Data: The "Ghost Player" Policy

Your decision to keep players who leave is excellent for data integrity and community.

**The Implementation:**

*   This doesn't require an `is_active` flag if you want them to always show up. The bot simply never deletes a `Player` record from the database when a user leaves the Discord server.
*   The `on_member_remove` event in the bot, which is triggered when a user leaves, will do nothing regarding the game's database.

**The Consequences (How it Works in Practice):**

1.  **Stable Leaderboards:** If Player Bob is #3 on the leaderboard and leaves the server, he remains at #3. Other players must still earn enough Elo to surpass his score. This prevents people from "gaming" the rankings by encouraging rivals to leave.
2.  **Valid Match History:** If Player Alice's profile shows she beat Bob, that record remains accurate and valid, even if Bob is no longer in the server. The history of the season is preserved.
3.  **Seamless Return:** If Bob rejoins the server a month later as a joke, the bot will recognize his Discord UID and all his stats—Elo, tickets, match history—will be exactly as he left them, ready to go.
4.  **Minor UX Consideration:** When displaying profiles or leaderboards, the bot can check if the user's ID is still present in the server's member list. If not, it could add a small "(Left Server)" tag next to their name for clarity, but this is an optional enhancement. The core data remains untouched.

That's a fantastic question. Designing the user interface for displaying this much data is just as important as the backend logic. A cluttered or confusing profile page will kill user engagement.

The best approach is a **layered, interactive menu system** using Discord's Buttons and Select Menus. You start with a high-level summary and allow the user to "drill down" for more details. This keeps the initial view clean while making all the information accessible.

Here is a comprehensive design for the `/profile` command.

---

### **The Profile Command: A Multi-Layered "Culling Games Passport"**

When a user types `/profile` (or `/profile @user`), the bot will respond with an initial, high-level embed. This is the main "Passport" page. Attached to this message will be a set of interactive components (Buttons and a Select Menu) for navigation.

#### **Layer 1: The Main Profile Embed (The "Passport")**

This is the first thing a user sees. It's designed to be a quick, scannable summary of their overall standing.

**Title:** `Culling Games Passport: [Player Name]`
**Thumbnail:** The user's Discord avatar.
**Color:** A cool, neutral color (or it could be dynamic, like gold for the #1 ranked player).

**Fields:**

1.  **Final Score & Rank** (Inline)
    *   **Title:** 🏆 Final Score
    *   **Value:** `2150`
2.  **Overall Rank** (Inline)
    *   **Title:** 🌍 Server Rank
    *   **Value:** `#1 / 50`
3.  **Ticket Balance** (Inline)
    *   **Title:** 🎟️ Tickets
    *   **Value:** `350`
4.  **Overall Scoring Elo**
    *   **Title:** 📈 Overall Scoring Elo
    *   **Value:** `1950`
5.  **Overall Raw Elo**
    *   **Title:** 📊 Overall Raw Elo
    *   **Value:** `1950`
6.  **Season Record (W-L-D)**
    *   **Title:** ⚔️ Match Record
    *   **Value:** `W: 42 - L: 20 - D: 3` (`67.7% Winrate`)
7.  **At a Glance: Top 3 Clusters**
    *   **Title:** 👑 Top Clusters
    *   **Value:**
        *   `1. Fighting Games (2100)`
        *   `2. Minecraft (2050)`
        *   `3. Chess (1980)`
8.  **At a Glance: Bottom 3 Clusters**
    *   **Title:** 💀 Areas for Improvement
    *   **Value:**
        *   `18. Running (1500)`
        *   `19. Trivia (1500)`
        *   `20. Rhythm Games (1500)`

---

#### **The Interactive Components (Attached to the Passport)**

Below the main embed, the user will see a set of controls to navigate to more detailed views.

**Row 1: Main Navigation Buttons**

`[Clusters Overview]` `[Match History]` `[Ticket Ledger]` `[View on Leaderboard]`

**Row 2: Drill-Down Select Menu**

`[ ▼ Select a Cluster to view its Events... ]`

---

### **Navigating the Profile: The Drill-Down Experience**

When a user clicks a button or uses the select menu, the bot will edit the original message to show the new information.

#### **Clicking `[Clusters Overview]` -> Layer 2**

The embed updates to a paginated list of all 20 clusters.

**Title:** `Cluster Overview: [Player Name]`
**Description:** Showing clusters 1-10 of 20.
**Fields:**
*   `[Cluster 1 Name]`: `Scoring: 2100 | Raw: 2100`
*   `[Cluster 2 Name]`: `Scoring: 2050 | Raw: 2050`
*   ...and so on for 10 clusters.
**Footer:** `Page 1/2`
**Components:** The buttons would now be `[← Previous]` `[Next →]` and a `[Back to Main Profile]` button. The Cluster Select Menu remains.

#### **Using the `[ ▼ Select Menu ]` -> Layer 3**

Let's say the user selects "Minecraft" from the dropdown. The embed updates to show the details for *just that cluster*.

**Title:** `Cluster Details: Minecraft`
**Fields:**
*   `Bedwars`: `Scoring: 2000 | Raw: 2000`
*   `Classic Duels`: `Scoring: 1900 | Raw: 1900`
*   `Skywars`: `Scoring: 1750 | Raw: 1750`
*   `Blitz Duels`: `Scoring: 1600 | Raw: 1600`
*   `Sumo Duels`: `Scoring: 1550 | Raw: 980` 💀 *(An emoji highlights the sub-1000 raw score)*
**Components:** A single `[Back to Main Profile]` button.

#### **Clicking `[Match History]` -> A Paginated Log**

The embed updates to show the user's 5 most recent matches.

**Title:** `Recent Match History`
**Description:**
*   `[#1342] MC Bedwars - 3rd/8 (-5 Elo) - 1 day ago`
*   `[#1337] Chess Bullet - Win vs. Bob (+15 Elo) - 2 days ago`
*   `[#1330] Tetris VS - Loss vs. Alice (-12 Elo) - 2 days ago`
*   ...and so on.
**Footer:** `Page 1/15`
**Components:** `[← Previous]` `[Next →]` and `[Back to Main Profile]` buttons.

#### **Clicking `[Ticket Ledger]` -> A Paginated Log**

Similar to match history, this shows recent ticket transactions.

**Title:** `Recent Ticket Transactions`
**Description:**
*   `Today: +5 (Participation: MC Bedwars)`
*   `Yesterday: -100 (Purchase: Bounty on Alice)`
*   `2 days ago: +50 (Reward: Hot Streak)`
*   ...and so on.
**Footer:** `Page 1/4`
**Components:** `[← Previous]` `[Next →]` and `[Back to Main Profile]` buttons.

### **Other potential additions**

1.  **Highest Achieved Elo:** A "Peak Raw Elo" stat (for any single event) to serve as a personal best.
2.  **Current Streak:** `W3` (Winning streak of 3) or `L2` (Losing streak of 2).

This layered, interactive design presents information cleanly, respects Discord's UI limitations, and empowers users to explore their own stats in a way that is both comprehensive and intuitive.


Excellent point. This is a crucial psychological element for a long-term competition. You want to punish mistakes, but not so severely that players feel there's no hope for recovery. Creating a "floor" for scoring purposes while still tracking the true Elo is the perfect solution. It maintains data integrity while promoting player morale.

Let's integrate this concept, find a better name, and design the fully-featured leaderboard.

---

### **Introducing the "Scoring Elo" - The Dual-Track System**

We will implement a dual-track Elo system. Every player will have two parallel Elo values at every level of the hierarchy:

1.  **Raw Elo:** This is the true, unfiltered skill rating. It can go as low as a player's performance takes them. This number is essential for accurate matchmaking and historical data, representing a player's *actual* skill.
2.  **Scoring Elo:** This is the value used for all official leaderboard calculations and the final score. It is identical to Raw Elo, *unless* the Raw Elo drops below the starting baseline (e.g., 1000). In that case, the Scoring Elo is "floored" at the baseline.

**The Rule:** `Scoring Elo = max(Raw Elo, 1000)`

This name is better than "Corrected Elo" because it clearly defines its purpose: it's the Elo that is used *for scoring* in the Culling Games. It's not a "correction" of a mistake, but an intentional part of the game's design. A more thematic name could even be **"Culling Score"** or **"Standing Elo."** For clarity in the plan, we'll use **"Scoring Elo."**

---

### **How the Dual-Track System Propagates**

This `max(Raw, 1000)` logic is applied at the very bottom, at the **Event Elo** level. This ensures the "floor" is respected all the way up the pyramid.

*   **Step 1: Event Level**
    *   You have a `Raw Event Elo` (e.g., 950 in Chess).
    *   You also have a `Scoring Event Elo` (`max(950, 1000) = 1000`).

*   **Step 2: Cluster Level**
    *   The **"Prestige Weighting"** formula is run *twice*:
        *   Once with all `Raw Event Elos` to produce the `Raw Cluster Elo`.
        *   Once with all `Scoring Event Elos` to produce the `Scoring Cluster Elo`.

*   **Step 3: Overall Level**
    *   The **"Weighted Generalist"** formula is also run *twice*:
        *   Once with all `Raw Cluster Elos` to produce the `Overall Raw Elo`.
        *   Once with all `Scoring Cluster Elos` to produce the `Overall Scoring Elo`.

This creates perfect parallel data streams, giving us everything we need for the final leaderboard.

---

### **The Final Score Calculation (v4)**

The final score formula is now updated to use the new `Overall Scoring Elo`.

`Final Score = Overall Scoring Elo + Shard of the Crown Bonus + Ticket Shop Bonuses`

This achieves your goal: a player's disastrous performance in one or two events won't unfairly tank their `Final Score`, encouraging them to keep playing.

---

### **The Ultimate Leaderboard: A Sortable Data Hub**

The main leaderboard will be the central hub of the competition. It will display all key metrics and, crucially, will be **sortable by any column**. A user could click a header (or use a command parameter like `!leaderboard --sort=raw_elo`) to re-rank the view.

Here's what the default view, sorted by `Final Score`, would look like:

| Rank | Player | Final Score ▼ | Overall Scoring Elo | Overall Raw Elo | Shard Bonus | Shop Bonus |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | Alice | **2150** | 1950 | 1950 | 0 | +200 |
| **2** | Bob | **2075** | 2025 | 2025 | +50 | +0 |
| **3** | David | **1850** | 1850 | 1850 | 0 | +0 |
| **4** | Charlie | **1823** | 1823 | **1785** | 0 | +0 |

**How to Interpret this Leaderboard:**

*   **Default View (Sorted by Final Score):** Alice is winning the Culling Games, thanks to her clever use of the Ticket Shop.
*   **Sorting by `Overall Scoring Elo`:** Clicking this header would put Bob at #1, showing he is the top-performing player in terms of the official scoring metrics.
*   **Sorting by `Overall Raw Elo`:** This would also show Bob at #1. However, it reveals a key insight about Charlie: his `Raw Elo` (1785) is lower than his `Scoring Elo` (1823). This tells everyone that Charlie has at least one event where his skill has dropped below the 1000 Elo baseline, but the system is protecting his final score.
*   **Sorting by `Shard Bonus`:** This would show who has been most successful at taking down the server owner.
*   **Sorting by `Shop Bonus`:** This would reveal who is the biggest "whale" and is influencing their score most through the ticket economy.

This design provides maximum transparency, protects player morale, and turns the leaderboard itself into a strategic tool for analyzing opponents. It's the perfect final piece for the core vision.


Of course. This is a crucial piece of the puzzle. Devising a formula that feels right and scales properly is key to making the entire system work. Your examples show a clear design intent: a steep drop-off in importance for the top few events, followed by a "long tail" of smaller, equal contributions.

A simple mathematical curve won't easily produce that specific plateau effect. Therefore, the best approach is a hybrid system that uses a defined set of multipliers—a method we can call **"Prestige Weighting."**

This system is simple to understand, perfectly tunable, and achieves the exact weighting distribution you're looking for.

---

### **The "Prestige Weighting" Formula for Cluster Elo**

Here is the proposed system for calculating the weighted Elo score for each Cluster.

#### **The Concept**

Instead of a complex continuous formula, we'll assign a "Prestige Multiplier" to each event based on a player's rank within that cluster. The top-ranked events get a high multiplier, which drops off sharply before settling on a baseline value for all subsequent events.

#### **The Prestige Multipliers**

*   **Rank 1 Event:** `4.0x` Prestige
*   **Rank 2 Event:** `2.5x` Prestige
*   **Rank 3 Event:** `1.5x` Prestige
*   **Rank 4+ Events:** `1.0x` Prestige (The Baseline)

These values are specifically designed to produce the weighting you described.

#### **The Calculation Process**

Here’s the step-by-step process for calculating a player's Cluster Elo:

1.  **Sort:** For a given player, take all their Event Elo scores within a cluster and sort them from highest to lowest.
2.  **Assign Multipliers:** Assign the appropriate Prestige Multiplier to each sorted Elo score based on its rank (1st, 2nd, 3rd, 4th, etc.).
3.  **Calculate Raw Prestige:** Multiply each Event Elo score by its Prestige Multiplier to get its "Raw Prestige Value."
4.  **Sum and Normalize:**
    *   Sum all the **Raw Prestige Values** together to get the `Total Raw Prestige`.
    *   Sum all the **Prestige Multipliers** used to get the `Total Multiplier`.
5.  **Final Cluster Elo:** Divide the `Total Raw Prestige` by the `Total Multiplier`.

`Cluster Elo = (Σ (Event_Elo * Multiplier)) / (Σ Multipliers)`

This method ensures that the final score is a true weighted average, scaled correctly by the prestige of each event.

---

### **Putting It Into Practice: Examples**

Let's see how this formula creates the exact distributions you wanted.

#### **Example 1: A Cluster with 2 Events (Minecraft: Blitz & Sumo)**
A player has `1800 Elo` in Blitz (Rank 1) and `1600 Elo` in Sumo (Rank 2).

1.  **Multipliers:** Blitz gets `4.0x`, Sumo gets `2.5x`.
2.  **Raw Prestige:**
    *   Blitz: `1800 * 4.0 = 7200`
    *   Sumo: `1600 * 2.5 = 4000`
3.  **Summation:**
    *   Total Raw Prestige: `7200 + 4000 = 11200`
    *   Total Multiplier: `4.0 + 2.5 = 6.5`
4.  **Final Cluster Elo:** `11200 / 6.5 = **1723**`

**Weighting Check:** The weights are `4.0 / 6.5 = **61.5%**` and `2.5 / 6.5 = **38.5%**`. This is extremely close to your desired `60/40` split, capturing the spirit perfectly.

---

#### **Example 2: A Cluster with 5 Events (Minecraft: Full Suite)**
A player has the following scores:
*   Bedwars: `2000` (Rank 1)
*   Classic Duels: `1900` (Rank 2)
*   Skywars: `1750` (Rank 3)
*   Blitz Duels: `1600` (Rank 4)
*   Sumo Duels: `1550` (Rank 5)

1.  **Multipliers:** `4.0x`, `2.5x`, `1.5x`, `1.0x`, `1.0x`
2.  **Total Multiplier:** `4.0 + 2.5 + 1.5 + 1.0 + 1.0 = 10.0`
3.  **Weighting Check:**
    *   Rank 1: `4.0 / 10.0 = **40%**`
    *   Rank 2: `2.5 / 10.0 = **25%**`
    *   Rank 3: `1.5 / 10.0 = **15%**`
    *   Rank 4: `1.0 / 10.0 = **10%**`
    *   Rank 5: `1.0 / 10.0 = **10%**`

This distribution **exactly matches** your `40/25/15/10/10` example.

---

#### **Example 3: A Cluster with 7 Events (IO Games)**

This shows how the system scales perfectly with the "long tail."

*   **Multipliers:** `4.0x, 2.5x, 1.5x, 1.0x, 1.0x, 1.0x, 1.0x`
*   **Total Multiplier:** `4.0 + 2.5 + 1.5 + 4.0 = 12.0`
*   **Weighting:**
    *   Rank 1: `4.0 / 12.0 = **33.3%**`
    *   Rank 2: `2.5 / 12.0 = **20.8%**`
    *   Rank 3: `1.5 / 12.0 = **12.5%**`
    *   Ranks 4-7: `1.0 / 12.0 = **8.3%**` each

This **"Prestige Weighting"** system is robust, scalable, and perfectly implements your vision for rewarding mastery while still valuing participation in secondary events within a cluster. We'll build this into the core logic.






Of course. This is a fascinating and complex part of the system that requires a very different approach from standard head-to-head Elo. A detailed breakdown is essential.

Here is an extremely detailed, step-by-step explanation of how the Leaderboard Event scoring system will work, from the underlying philosophy to the final calculation.

---

### **ADDENDUM B: The Leaderboard Event System**

CHANGE FROM THIS OVERVIEW: WEEKLY RESET WILL BE DONE MANUALLY, NOT AUTOMATICALLY

This addendum provides a complete specification for events with the `scoring_type` of 'Leaderboard'. These events are asynchronous, performance-based competitions (e.g., Tetris high score, 40L Sprint time, 1-mile run time) where players compete against a metric rather than each other directly.

### **1. The Core Philosophy**

The fundamental challenge is to translate an absolute score (e.g., "500,000 points" or "38.5 seconds") into a relative, competitive Elo rating. The system must:

*   **Reward Excellence:** A truly outstanding, record-breaking score must grant a significantly higher Elo than an average one.
*   **Encourage Consistent Participation:** Players should be incentivized to participate in weekly competitions, not just "set and forget" a single good score.
*   **Maintain Competitiveness:** The system must adapt over time. As the server community gets better at a game, the definition of a "good" score should evolve.
*   **Be Fair and Transparent:** The method for converting a score to an Elo rating must be logical, formulaic, and understandable.

To achieve this, the Leaderboard Event Elo is a composite metric derived from two distinct components: a player's **All-Time Performance** and their **Weekly Active Performance**.

### **2. The Core Mechanic: Score-to-Elo Conversion via Statistical Normalization**

We cannot directly compare scores. Instead, we must determine how good a score is *relative to everyone else's scores*. The best way to do this is by using a statistical Z-score, which measures how many standard deviations a data point is from the mean (the average).

#### **2.1. The Score Direction Flag**

First, the bot must understand what a "good" score means for each event. This requires a new property in the `Event` database model:

*   **`score_direction`:** An attribute that can be either `HIGH` or `LOW`.
    *   `HIGH`: Higher scores are better (e.g., Tetris points, NitroType WPM).
    *   `LOW`: Lower scores are better (e.g., 40L Sprint time, 1-mile run time).

This flag is crucial for the Z-score calculation to work correctly.

#### **2.2. The Z-Score Formula**

The Z-score tells us how exceptional a score is.

`Z = (Player's Score - Population Mean) / Population Standard Deviation`

*   If `score_direction` is `LOW`, the formula is inverted:
    `Z = (Population Mean - Player's Score) / Population Standard Deviation`

This ensures that a great time (low number) results in a positive Z-score, just like a great point total (high number).

#### **2.3. The Elo Conversion Formula**

Once we have the Z-score, we can convert it to an Elo-equivalent value.

`Elo = BASE_ELO + (Z * ELO_PER_SIGMA)`

*   **`BASE_ELO`**: The server's baseline Elo (e.g., `1000`). This is the Elo assigned to a perfectly average performance (Z-score of 0).
*   **`ELO_PER_SIGMA`**: A constant that defines how many Elo points one standard deviation is worth. This is a key tuning parameter that determines the "steepness" of the Elo curve. A good starting value is **`200`**.
    *   This means a score one standard deviation above average (`Z=1.0`) results in `1000 + (1 * 200) = 1200` Elo.
    *   A score two standard deviations below average (`Z=-2.0`) results in `1000 + (-2 * 200) = 600` Elo.

### **3. Component A: The All-Time Leaderboard (Personal Bests)**

This component represents a player's peak performance and forms the stable, long-term part of their rating.

#### **3.1. Database Requirement**

A new table is needed to track personal bests for every player in every leaderboard event.

*   **`PlayerEventPersonalBest` Table:**
    *   `player_id`
    *   `event_id`
    *   `best_score` (e.g., a float or integer)
    *   `timestamp_achieved`

#### **3.2. User Workflow & Calculation Trigger**

1.  **Submission:** A player uses the command `/submit-score [event_name] [score]`.
2.  **Validation:** The bot checks if this new score is better than the player's existing `best_score` in the `PlayerEventPersonalBest` table (respecting the `score_direction` flag).
3.  **Update:** If the new score is a personal best (PB), the bot updates the table with the new `best_score` and `timestamp_achieved`.
4.  **Recalculate All-Time Elo:** This is the crucial step. **Every time any player sets a new personal best**, the bot must recalculate the "All-Time Elo" for *every player* in that event.
    *   **Process:**
        a.  The bot fetches *all* `best_score` values from the `PlayerEventPersonalBest` table for the specific event.
        b.  It calculates the **Mean** and **Standard Deviation** for this entire population of PBs.
        c.  It then iterates through every player who has a PB and runs the **Score-to-Elo Conversion** formula on their score, using the newly calculated mean and standard deviation.
        d.  The resulting Elo value is stored in a `all_time_leaderboard_elo` field within the `PlayerEventStats` table.

This ensures that the value of your PB is constantly re-evaluated against the improving skill of the entire server.

### **4. Component B: The Weekly Resets (Active Performance)**

This component rewards consistent participation and recent performance.

#### **4.1. The Weekly Cycle & Database**

*   **Cycle:** The weekly cycle runs from a fixed time to a fixed time (e.g., Monday at 00:00 UTC to Sunday at 23:59 UTC).
*   **Database Tables:**
    *   **`WeeklyScores` (Temporary Table):**
        *   `player_id`, `event_id`, `score`, `timestamp`
        *   This table is **wiped clean** at the start of every new week.
    *   **`PlayerWeeklyLeaderboardElo` (Permanent Log):**
        *   `player_id`, `event_id`, `week_number`, `weekly_elo_score`
        *   This table stores the historical results of each weekly competition.

#### **4.2. The Automated Weekly Job**

At the end of each week (e.g., Sunday at 23:59 UTC), a scheduled job runs automatically for every leaderboard event.

1.  **Gather Data:** The bot collects all submissions for the week from the `WeeklyScores` table for a specific event.
2.  **Calculate Weekly Stats:** It calculates the **Mean** and **Standard Deviation** for *only that week's submissions*.
3.  **Calculate Weekly Elo:** It iterates through every player who participated that week and runs the **Score-to-Elo Conversion** on their weekly best score.
4.  **Log Results:** The resulting `weekly_elo_score` is saved to the `PlayerWeeklyLeaderboardElo` table for each participant, along with the current `week_number`.
5.  **Announce Winners:** The bot can post a summary message in a channel: "🏆 **Tetris Weekly Results (Week 12):** 1st: @Alice (1550 Elo), 2nd: @Bob (1300 Elo), 3rd: @Charlie (1100 Elo)."
6.  **Reset:** The `WeeklyScores` table is cleared, ready for the next week's submissions.

### **5. The Final Leaderboard Event Elo Calculation**

Finally, we combine the two components to get the official `Event Elo` that feeds into the Cluster Elo calculation. This is calculated dynamically whenever a player's profile or the main leaderboard is viewed.

`Event Elo = (All_Time_Elo * 0.5) + (Average_Weekly_Elo * 0.5)`

*   **`All_Time_Elo`:** The player's `all_time_leaderboard_elo` fetched directly from their `PlayerEventStats`.
*   **`Average_Weekly_Elo`:** This is calculated as follows:
    1.  The bot checks the current `season_week_number` (e.g., the season is in its 12th week).
    2.  It sums all of the player's `weekly_elo_score` values for that event from the `PlayerWeeklyLeaderboardElo` table.
    3.  It divides that sum by the `season_week_number`.
    *   **Formula:** `Average_Weekly_Elo = (Σ weekly_elo_scores) / (Total weeks elapsed in season)`
    *   **Crucial Rule:** If a player did not participate in a given week, their score for that week is implicitly `0`, which correctly punishes inactivity by dragging down their average.

#### **Example Scenario:**

*   It's Week 4 of the season.
*   Alice's `All_Time_Elo` for Tetris is **1600**.
*   Her weekly scores were: Week 1 (`1550`), Week 2 (`1450`), Week 3 (missed), Week 4 (`1500`).
*   **Sum of weekly scores:** `1550 + 1450 + 0 + 1500 = 4500`.
*   **Average Weekly Elo:** `4500 / 4 = 1125`.
*   **Alice's Final Tetris Event Elo:** `(1600 * 0.5) + (1125 * 0.5) = 800 + 562.5 = **1362.5**`.

This detailed system creates a rich, dynamic, and competitive environment for non-traditional events, fully integrating them into the Culling Games framework.