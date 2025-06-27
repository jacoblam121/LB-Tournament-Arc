"""
Operations Layer - Phase 2A2.5 Subphase 2

This package provides business logic operations that compose database methods
for complex workflows. Operations modules handle multi-step transactions,
validation, and business rules while maintaining clean separation of concerns.

Architecture:
- Database layer: Pure data access and CRUD operations
- Operations layer: Business logic composition and workflows
- Command layer: Discord integration and user interface

Each operations module focuses on a specific domain:
- PlayerOperations: Player lifecycle and Discord user integration
- EventOperations: Event creation and management
- MatchOperations: Match workflows and result processing (already implemented)
"""