"""
Team Formation Modal - Phase 2.2 Implementation

Modal for assigning players to teams in team-based challenges.
Follows Discord's 5-input limitation with dynamic team assignment.
"""

import discord
from typing import List, Dict, Optional
from bot.utils.logger import setup_logger

logger = setup_logger(__name__)


class TeamFormationModal(discord.ui.Modal, title="Team Formation"):
    """
    Modal for organizing players into teams for team-based challenges.
    
    Always creates exactly 2 teams (Team A and Team B) for all team matches.
    Each team assignment is a text input where players can be assigned.
    """
    
    def __init__(
        self,
        challenge_cog,
        cluster_id: int,
        event_id: int,
        participants: List[discord.Member],
        match_type: str = "team"
    ):
        """
        Initialize TeamFormationModal.
        
        Args:
            challenge_cog: Reference to ChallengeCog for callback
            cluster_id: ID of the selected cluster
            event_id: ID of the selected event
            participants: List of Discord members participating
            match_type: Type of match (should be "team")
        """
        super().__init__(timeout=300)  # 5 minute timeout
        
        self.challenge_cog = challenge_cog
        self.cluster_id = cluster_id
        self.event_id = event_id
        self.participants = participants
        self.match_type = match_type
        self.logger = logger
        
        # Validate participant count
        if len(participants) < 2:
            raise ValueError("Team matches require at least 2 participants")
        if len(participants) > 8:
            raise ValueError("Team matches support maximum 8 participants")
        
        # Team matches always have exactly 2 teams
        self.team_count = 2
        
        # Create dynamic fields based on team count
        self._create_team_fields()
    
    def _create_team_fields(self):
        """Create text input fields for each team"""
        # Create participant list for reference
        participant_list = "\n".join([
            f"{i+1}. {p.display_name}" for i, p in enumerate(self.participants)
        ])
        
        # Team labels
        team_labels = ["Team A", "Team B"]
        
        # Create fields for each team (exactly 2 teams)
        for i in range(self.team_count):
            if i == 0:
                # First field includes participant list
                placeholder = "Enter player numbers (e.g., 1 3)"
                label = f"{team_labels[i]} Members"
                default = ""
            else:
                placeholder = "Enter player numbers"
                label = f"{team_labels[i]} Members"
                default = ""
            
            text_input = discord.ui.TextInput(
                label=label,
                placeholder=placeholder,
                required=True,
                min_length=1,
                max_length=20,
                style=discord.TextStyle.short,
                custom_id=f"team_{i}",
                default=default
            )
            self.add_item(text_input)
        
        # Add participant reference field if we have room (max 5 fields total)
        if self.team_count < 5:
            ref_input = discord.ui.TextInput(
                label="Participant Reference (DO NOT EDIT)",
                placeholder="Reference only",
                required=False,
                max_length=1000,
                style=discord.TextStyle.paragraph,
                custom_id="participant_ref",
                default=participant_list
            )
            self.add_item(ref_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """
        Process team assignments and create the challenge.
        
        Validates team assignments and calls back to ChallengeCog
        to complete challenge creation.
        """
        try:
            # Parse team assignments
            team_assignments = {}
            assigned_players = set()
            
            for item in self.children:
                if isinstance(item, discord.ui.TextInput) and item.custom_id.startswith("team_"):
                    team_id = item.custom_id.split("_")[1]  # "0", "1", "2", "3"
                    
                    # Parse player numbers from input
                    player_numbers = []
                    for num_str in item.value.strip().split():
                        try:
                            num = int(num_str) - 1  # Convert to 0-indexed
                            if 0 <= num < len(self.participants):
                                player_numbers.append(num)
                            else:
                                await interaction.response.send_message(
                                    f"❌ Invalid player number: {num_str}. Must be between 1 and {len(self.participants)}.",
                                    ephemeral=True
                                )
                                return
                        except ValueError:
                            await interaction.response.send_message(
                                f"❌ Invalid input: '{num_str}'. Please enter player numbers only.",
                                ephemeral=True
                            )
                            return
                    
                    # Assign players to team
                    for player_idx in player_numbers:
                        if player_idx in assigned_players:
                            player = self.participants[player_idx]
                            await interaction.response.send_message(
                                f"❌ {player.display_name} is assigned to multiple teams!",
                                ephemeral=True
                            )
                            return
                        
                        assigned_players.add(player_idx)
                        player = self.participants[player_idx]
                        team_assignments[player.id] = f"Team_{team_id}"
            
            # Validate all players are assigned
            if len(assigned_players) != len(self.participants):
                missing = []
                for i, p in enumerate(self.participants):
                    if i not in assigned_players:
                        missing.append(f"{i+1}. {p.display_name}")
                
                await interaction.response.send_message(
                    f"❌ Not all players assigned to teams!\n\nMissing:\n{chr(10).join(missing)}",
                    ephemeral=True
                )
                return
            
            # Validate team sizes (at least 1 player per team)
            team_sizes = {}
            for team in team_assignments.values():
                team_sizes[team] = team_sizes.get(team, 0) + 1
            
            if len(team_sizes) < 2:
                await interaction.response.send_message(
                    "❌ Team matches require at least 2 teams!",
                    ephemeral=True
                )
                return
            
            # Call back to ChallengeCog to complete challenge creation
            await self.challenge_cog._complete_team_challenge_creation(
                interaction=interaction,
                cluster_id=self.cluster_id,
                event_id=self.event_id,
                participants=self.participants,
                team_assignments=team_assignments
            )
            
        except Exception as e:
            self.logger.error(f"Error in TeamFormationModal submission: {e}")
            
            # Try to respond if we haven't already
            try:
                await interaction.response.send_message(
                    "❌ An error occurred while creating the team challenge. Please try again.",
                    ephemeral=True
                )
            except discord.InteractionResponded:
                # Already responded, send followup instead
                await interaction.followup.send(
                    "❌ An error occurred while creating the team challenge. Please try again.",
                    ephemeral=True
                )
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Handle modal errors"""
        self.logger.error(f"TeamFormationModal error: {error}", exc_info=True)
        
        try:
            await interaction.response.send_message(
                "❌ An unexpected error occurred. Please try again.",
                ephemeral=True
            )
        except discord.InteractionResponded:
            pass