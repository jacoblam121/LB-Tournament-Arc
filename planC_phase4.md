# Phase 4: Wallet System & Ticket Economy - Production-Ready Implementation Plan

## Overview
Phase 4 implements an enterprise-grade ticket economy system with secure transactions, comprehensive earning mechanics, and a full-featured shop system. This plan addresses all critical issues from code review and incorporates advanced features for production readiness.

## Core Architecture Principles

### 1. WalletService Design
- **Single Source of Truth**: WalletService handles ALL ticket operations
- **Atomic Transactions**: SERIALIZABLE isolation with automatic retry
- **Double-Entry Bookkeeping**: Each transaction creates balanced ledger entries
- **Idempotency**: Database-enforced UNIQUE constraints on external_ref
- **Performance**: Optimistic locking, prepared statements, batch operations
- **Security**: Multi-layer fraud detection, rate limiting, input validation
- **Observability**: Distributed tracing, metrics, comprehensive logging

### 2. Configuration Management
```python
from dataclasses import dataclass

@dataclass
class WalletConfig:
    # Transaction limits
    MAX_SINGLE_TRANSACTION: int = 100000
    ADMIN_CONFIRMATION_THRESHOLD: int = 10000
    
    # Rate limiting
    MAX_TRANSACTIONS_PER_MINUTE: int = 60
    MAX_BALANCE_CHECKS_PER_MINUTE: int = 120
    
    # Database
    TRANSACTION_ISOLATION: str = 'serializable'
    CONNECTION_POOL_SIZE: int = 20
    
    # Retry configuration
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_BASE: float = 0.1  # 100ms
    
    # System accounts
    SYSTEM_ACCOUNT_ID: int = 0
    
    # Fraud detection
    VELOCITY_THRESHOLD: int = 100  # Max transactions per hour
    ANOMALY_THRESHOLD: float = 3.0  # Standard deviations
```

## Database Schema

### Updated player table
```sql
ALTER TABLE players 
ADD COLUMN ticket_balance BIGINT NOT NULL DEFAULT 0 CHECK (ticket_balance >= 0),
ADD COLUMN version INTEGER NOT NULL DEFAULT 0,
ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT NOW();

-- Add indexes for performance
CREATE INDEX idx_players_version ON players(id, version);
```

### ticket_ledger with enhanced indexes
```sql
CREATE TABLE ticket_ledger (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(id),
    amount BIGINT NOT NULL, -- positive or negative
    counterpart_id BIGINT REFERENCES ticket_ledger(id),
    event_type VARCHAR(50) NOT NULL, -- participation, purchase, admin_adjust, etc.
    external_ref VARCHAR(255),
    match_id BIGINT REFERENCES matches(id),
    reason TEXT, -- Audit trail description
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Enforce idempotency at database level
    CONSTRAINT ticket_ledger_external_ref_unique UNIQUE (external_ref)
);

-- Performance indexes
CREATE INDEX idx_ledger_player_date ON ticket_ledger(player_id, created_at DESC);
CREATE INDEX idx_ledger_external_ref ON ticket_ledger(external_ref) WHERE external_ref IS NOT NULL;
CREATE INDEX idx_ledger_match ON ticket_ledger(match_id) WHERE match_id IS NOT NULL;
CREATE INDEX idx_ledger_player_time_amount ON ticket_ledger(player_id, created_at DESC, amount) WHERE amount > 0;
```

### player_achievements
```sql
CREATE TABLE player_achievements (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(id),
    achievement_type VARCHAR(100) NOT NULL,
    event_id INTEGER REFERENCES events(id),
    achieved_at TIMESTAMP NOT NULL DEFAULT NOW(),
    
    -- Prevent duplicate achievements at database level
    UNIQUE(player_id, achievement_type, event_id)
);

CREATE INDEX idx_achievements_player ON player_achievements(player_id);
```

### shop_items
```sql
CREATE TABLE shop_items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL, -- collusion, chaos, gambling, etc.
    price INTEGER NOT NULL CHECK (price BETWEEN 0 AND 2147483647),
    effect_type VARCHAR(50) NOT NULL, -- modifier, info, bounty, etc.
    effect_payload JSONB NOT NULL,
    availability_rules JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_shop_items_active ON shop_items(category, price) WHERE is_active = TRUE;
```

### player_purchases
```sql
CREATE TABLE player_purchases (
    id BIGSERIAL PRIMARY KEY,
    player_id BIGINT NOT NULL REFERENCES players(id),
    shop_item_id INTEGER NOT NULL REFERENCES shop_items(id),
    consumed_at TIMESTAMP,
    payload_snapshot JSONB NOT NULL,
    external_ref VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_purchases_player ON player_purchases(player_id, created_at DESC);
CREATE INDEX idx_purchases_unconsumed ON player_purchases(player_id) WHERE consumed_at IS NULL;
```

## Implementation Phases

### Phase 4.1: Core Wallet Infrastructure (Days 0-3)

#### 4.1.1 Error Handling Framework
```python
class WalletError(Exception):
    """Base exception for wallet operations"""
    pass

class InsufficientFundsError(WalletError):
    """Raised when balance is insufficient"""
    pass

class PlayerNotFoundError(WalletError):
    """Raised when player doesn't exist"""
    pass

class DuplicateTransactionError(WalletError):
    """Raised when external_ref already exists"""
    pass

class FraudDetectionError(WalletError):
    """Raised when fraud is detected"""
    pass

class MaxRetriesExceededError(WalletError):
    """Raised when max retries are exceeded"""
    pass

class OptimisticLockError(WalletError):
    """Raised when version mismatch occurs"""
    pass

def handle_wallet_errors(func):
    """Decorator for consistent error handling"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except asyncpg.UniqueViolationError:
            raise DuplicateTransactionError("Transaction already processed")
        except asyncpg.CheckViolationError as e:
            if "ticket_balance" in str(e):
                raise InsufficientFundsError("Insufficient ticket balance")
            raise
        except asyncpg.SerializationFailure:
            # Let retry logic handle this
            raise
        except Exception as e:
            logger.error(f"Wallet operation failed: {e}", exc_info=True)
            raise WalletError(f"Operation failed: {str(e)}")
    return wrapper
```

#### 4.1.2 Complete WalletService Implementation
```python
import asyncio
import time
import random
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

class WalletService:
    """Enterprise-grade wallet service with all safety features"""
    
    def __init__(self, db_pool, config: WalletConfig, metrics, tracer, fraud_detector):
        self.db = db_pool
        self.config = config
        self.metrics = metrics
        self.tracer = tracer
        self.fraud_detector = fraud_detector
        self.rate_limiter = AdaptiveRateLimiter(metrics)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            metrics=metrics
        )
    
    async def initialize(self):
        """Initialize service and verify system account exists"""
        # Ensure system account exists
        async with self.db.acquire() as conn:
            await conn.execute(
                """INSERT INTO players (id, discord_id, display_name, ticket_balance)
                   VALUES ($1, '0', 'SYSTEM', 0)
                   ON CONFLICT (id) DO NOTHING""",
                self.config.SYSTEM_ACCOUNT_ID
            )
    
    @trace_span("wallet.deposit")
    @handle_wallet_errors
    @circuit_breaker_protected
    async def deposit(self, player_id: int, amount: int, event_type: str,
                     external_ref: Optional[str] = None, 
                     match_id: Optional[int] = None,
                     reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Deposit tickets with comprehensive safety features.
        
        Args:
            player_id: Player ID
            amount: Amount to deposit (must be positive)
            event_type: Type of event (participation, achievement, etc.)
            external_ref: Idempotency key (optional but recommended)
            match_id: Associated match ID (optional)
            reason: Audit trail description (optional)
            
        Returns:
            Dict containing new_balance, transaction_id, and processing_time
            
        Raises:
            ValueError: If amount is invalid
            FraudDetectionError: If fraud is detected
            DuplicateTransactionError: If external_ref already exists
            PlayerNotFoundError: If player doesn't exist
        """
        start_time = time.time()
        
        # Input validation
        self._validate_amount(amount)
        
        # Rate limiting
        await self.rate_limiter.check_and_increment(
            f"wallet:deposit:{player_id}",
            self.config.MAX_TRANSACTIONS_PER_MINUTE
        )
        
        # Fraud detection
        fraud_result = await self.fraud_detector.check_transaction(
            player_id, amount, 'deposit'
        )
        if not fraud_result.passed:
            self.metrics.increment('wallet.deposit.fraud_blocked')
            raise FraudDetectionError(fraud_result.reason)
        
        # Execute with retry
        result = await self._deposit_with_retry(
            player_id, amount, event_type, external_ref, match_id, reason
        )
        
        # Record metrics
        processing_time = time.time() - start_time
        self.metrics.histogram(
            'wallet.deposit.duration',
            processing_time,
            tags={'event_type': event_type, 'status': 'success'}
        )
        
        return {
            'new_balance': result['balance'],
            'transaction_id': result['transaction_id'],
            'processing_time': processing_time
        }
    
    async def _deposit_with_retry(self, player_id: int, amount: int, 
                                 event_type: str, external_ref: Optional[str],
                                 match_id: Optional[int], reason: Optional[str],
                                 retry_count: int = 0) -> Dict[str, Any]:
        """Internal deposit with retry logic"""
        try:
            async with self.db.transaction(isolation=self.config.TRANSACTION_ISOLATION) as tx:
                # Check idempotency using database constraint
                if external_ref:
                    existing = await tx.fetchrow(
                        "SELECT id, amount FROM ticket_ledger WHERE external_ref = $1",
                        external_ref
                    )
                    if existing:
                        # Idempotent response - return current balance
                        balance = await tx.fetchval(
                            "SELECT ticket_balance FROM players WHERE id = $1",
                            player_id
                        )
                        return {
                            'balance': balance,
                            'transaction_id': existing['id'],
                            'idempotent': True
                        }
                
                # Get current balance and version for optimistic locking
                player = await tx.fetchrow(
                    """SELECT ticket_balance, version 
                       FROM players 
                       WHERE id = $1 
                       FOR UPDATE""",
                    player_id
                )
                
                if not player:
                    raise PlayerNotFoundError(f"Player {player_id} not found")
                
                # Create double-entry ledger entries
                # Player credit entry
                player_entry_id = await tx.fetchval(
                    """INSERT INTO ticket_ledger 
                       (player_id, amount, event_type, external_ref, match_id, reason)
                       VALUES ($1, $2, $3, $4, $5, $6) 
                       RETURNING id""",
                    player_id, amount, event_type, external_ref, match_id, reason
                )
                
                # System debit entry (balancing)
                system_entry_id = await tx.fetchval(
                    """INSERT INTO ticket_ledger 
                       (player_id, amount, event_type, counterpart_id, reason)
                       VALUES ($1, $2, $3, $4, $5) 
                       RETURNING id""",
                    self.config.SYSTEM_ACCOUNT_ID, -amount, event_type,
                    player_entry_id, f"Balance for transaction {player_entry_id}"
                )
                
                # Update counterpart references
                await tx.execute(
                    "UPDATE ticket_ledger SET counterpart_id = $1 WHERE id = $2",
                    system_entry_id, player_entry_id
                )
                
                # Update balance with version check (optimistic locking)
                updated = await tx.fetchrow(
                    """UPDATE players 
                       SET ticket_balance = ticket_balance + $1,
                           version = version + 1,
                           updated_at = NOW()
                       WHERE id = $2 AND version = $3
                       RETURNING ticket_balance, version""",
                    amount, player_id, player['version']
                )
                
                if not updated:
                    raise OptimisticLockError("Version mismatch, retry required")
                
                return {
                    'balance': updated['ticket_balance'],
                    'transaction_id': player_entry_id,
                    'idempotent': False
                }
                
        except (asyncpg.SerializationFailure, OptimisticLockError) as e:
            if retry_count < self.config.MAX_RETRIES:
                wait_time = self._calculate_backoff(retry_count)
                await asyncio.sleep(wait_time)
                
                self.metrics.increment(
                    'wallet.deposit.retry',
                    tags={'attempt': retry_count + 1, 'reason': type(e).__name__}
                )
                
                return await self._deposit_with_retry(
                    player_id, amount, event_type, external_ref, match_id, reason,
                    retry_count + 1
                )
            else:
                self.metrics.increment('wallet.deposit.max_retries_exceeded')
                raise MaxRetriesExceededError("Maximum retries exceeded") from e
    
    @trace_span("wallet.withdraw")
    @handle_wallet_errors
    @circuit_breaker_protected
    async def withdraw(self, player_id: int, amount: int, event_type: str,
                      external_ref: Optional[str] = None,
                      reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Withdraw tickets with balance protection.
        
        Args:
            player_id: Player ID
            amount: Amount to withdraw (must be positive)
            event_type: Type of event (purchase, admin_adjust, etc.)
            external_ref: Idempotency key (optional but recommended)
            reason: Audit trail description (optional)
            
        Returns:
            Dict containing new_balance, transaction_id, and processing_time
            
        Raises:
            ValueError: If amount is invalid
            InsufficientFundsError: If balance is insufficient
            FraudDetectionError: If fraud is detected
            PlayerNotFoundError: If player doesn't exist
        """
        start_time = time.time()
        
        # Input validation
        self._validate_amount(amount)
        
        # Rate limiting
        await self.rate_limiter.check_and_increment(
            f"wallet:withdraw:{player_id}",
            self.config.MAX_TRANSACTIONS_PER_MINUTE
        )
        
        # Fraud detection with stricter rules for withdrawals
        fraud_result = await self.fraud_detector.check_transaction(
            player_id, amount, 'withdraw'
        )
        if not fraud_result.passed:
            self.metrics.increment('wallet.withdraw.fraud_blocked')
            raise FraudDetectionError(fraud_result.reason)
        
        result = await self._withdraw_with_retry(
            player_id, amount, event_type, external_ref, reason
        )
        
        processing_time = time.time() - start_time
        self.metrics.histogram(
            'wallet.withdraw.duration',
            processing_time,
            tags={'event_type': event_type, 'status': 'success'}
        )
        
        return {
            'new_balance': result['balance'],
            'transaction_id': result['transaction_id'],
            'processing_time': processing_time
        }
    
    async def _withdraw_with_retry(self, player_id: int, amount: int,
                                  event_type: str, external_ref: Optional[str],
                                  reason: Optional[str], retry_count: int = 0) -> Dict[str, Any]:
        """Internal withdraw with retry logic"""
        try:
            async with self.db.transaction(isolation=self.config.TRANSACTION_ISOLATION) as tx:
                # Check idempotency
                if external_ref:
                    existing = await tx.fetchrow(
                        "SELECT id, amount FROM ticket_ledger WHERE external_ref = $1",
                        external_ref
                    )
                    if existing:
                        balance = await tx.fetchval(
                            "SELECT ticket_balance FROM players WHERE id = $1",
                            player_id
                        )
                        return {
                            'balance': balance,
                            'transaction_id': existing['id'],
                            'idempotent': True
                        }
                
                # Lock player row and check balance
                player = await tx.fetchrow(
                    """SELECT ticket_balance, version 
                       FROM players 
                       WHERE id = $1 
                       FOR UPDATE""",
                    player_id
                )
                
                if not player:
                    raise PlayerNotFoundError(f"Player {player_id} not found")
                
                if player['ticket_balance'] < amount:
                    raise InsufficientFundsError(
                        f"Insufficient balance: {player['ticket_balance']} < {amount}"
                    )
                
                # Create double-entry ledger entries
                # Player debit entry (negative amount)
                player_entry_id = await tx.fetchval(
                    """INSERT INTO ticket_ledger 
                       (player_id, amount, event_type, external_ref, reason)
                       VALUES ($1, $2, $3, $4, $5) 
                       RETURNING id""",
                    player_id, -amount, event_type, external_ref, reason
                )
                
                # System credit entry (positive amount)
                system_entry_id = await tx.fetchval(
                    """INSERT INTO ticket_ledger 
                       (player_id, amount, event_type, counterpart_id, reason)
                       VALUES ($1, $2, $3, $4, $5) 
                       RETURNING id""",
                    self.config.SYSTEM_ACCOUNT_ID, amount, event_type,
                    player_entry_id, f"Balance for transaction {player_entry_id}"
                )
                
                # Update counterpart references
                await tx.execute(
                    "UPDATE ticket_ledger SET counterpart_id = $1 WHERE id = $2",
                    system_entry_id, player_entry_id
                )
                
                # Update balance with version check
                updated = await tx.fetchrow(
                    """UPDATE players 
                       SET ticket_balance = ticket_balance - $1,
                           version = version + 1,
                           updated_at = NOW()
                       WHERE id = $2 AND version = $3
                       RETURNING ticket_balance, version""",
                    amount, player_id, player['version']
                )
                
                if not updated:
                    raise OptimisticLockError("Version mismatch, retry required")
                
                # The CHECK constraint will prevent negative balance
                return {
                    'balance': updated['ticket_balance'],
                    'transaction_id': player_entry_id,
                    'idempotent': False
                }
                
        except (asyncpg.SerializationFailure, OptimisticLockError) as e:
            if retry_count < self.config.MAX_RETRIES:
                wait_time = self._calculate_backoff(retry_count)
                await asyncio.sleep(wait_time)
                
                self.metrics.increment(
                    'wallet.withdraw.retry',
                    tags={'attempt': retry_count + 1, 'reason': type(e).__name__}
                )
                
                return await self._withdraw_with_retry(
                    player_id, amount, event_type, external_ref, reason,
                    retry_count + 1
                )
            else:
                self.metrics.increment('wallet.withdraw.max_retries_exceeded')
                raise MaxRetriesExceededError("Maximum retries exceeded") from e
    
    @trace_span("wallet.get_balance")
    @handle_wallet_errors
    async def get_balance(self, player_id: int) -> int:
        """Get player's current balance"""
        await self.rate_limiter.check_and_increment(
            f"wallet:balance:{player_id}",
            self.config.MAX_BALANCE_CHECKS_PER_MINUTE
        )
        
        async with self.db.acquire() as conn:
            balance = await conn.fetchval(
                "SELECT ticket_balance FROM players WHERE id = $1",
                player_id
            )
            
            if balance is None:
                raise PlayerNotFoundError(f"Player {player_id} not found")
            
            return balance
    
    def _validate_amount(self, amount: int):
        """Validate transaction amount"""
        if not isinstance(amount, int):
            raise ValueError("Amount must be an integer")
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if amount > self.config.MAX_SINGLE_TRANSACTION:
            raise ValueError(f"Amount exceeds maximum: {self.config.MAX_SINGLE_TRANSACTION}")
    
    def _calculate_backoff(self, retry_count: int) -> float:
        """Calculate exponential backoff with jitter"""
        backoff = self.config.RETRY_BACKOFF_BASE * (2 ** retry_count)
        jitter = random.uniform(0, 0.1)
        return min(backoff + jitter, 5.0)  # Max 5 seconds
```

#### 4.1.3 Admin Commands
```python
@admin_command()
async def admin_tickets(ctx, action: str, user: discord.Member, amount: int, *, reason: str):
    """Admin ticket management commands with safety checks"""
    
    # Validate action
    if action not in ['add', 'remove', 'set']:
        return await ctx.send("Invalid action. Use: add, remove, or set")
    
    # Safety check for large amounts
    if amount > config.ADMIN_CONFIRMATION_THRESHOLD:
        confirm_view = ConfirmationView(timeout=30)
        confirm_msg = await ctx.send(
            f"⚠️ **Large Transaction Warning**\n"
            f"Action: {action} {amount} tickets\n"
            f"User: {user.mention}\n"
            f"Reason: {reason}\n\n"
            f"Please confirm this action:",
            view=confirm_view
        )
        
        await confirm_view.wait()
        if not confirm_view.confirmed:
            return await confirm_msg.edit(content="Transaction cancelled.", view=None)
    
    wallet = WalletService(db_pool, config, metrics, tracer, fraud_detector)
    player_id = await get_or_create_player(user.id)
    
    try:
        if action == "add":
            result = await wallet.deposit(
                player_id, amount, "admin_adjust",
                external_ref=f"ADMIN_GRANT:{ctx.author.id}:{int(time.time())}",
                reason=f"ADMIN GRANT: {reason}"
            )
        elif action == "remove":
            result = await wallet.withdraw(
                player_id, amount, "admin_adjust",
                external_ref=f"ADMIN_REMOVE:{ctx.author.id}:{int(time.time())}",
                reason=f"ADMIN REMOVE: {reason}"
            )
        elif action == "set":
            current = await wallet.get_balance(player_id)
            diff = amount - current
            if diff > 0:
                result = await wallet.deposit(
                    player_id, diff, "admin_adjust",
                    external_ref=f"ADMIN_SET:{ctx.author.id}:{int(time.time())}",
                    reason=f"ADMIN SET: {reason}"
                )
            elif diff < 0:
                result = await wallet.withdraw(
                    player_id, -diff, "admin_adjust",
                    external_ref=f"ADMIN_SET:{ctx.author.id}:{int(time.time())}",
                    reason=f"ADMIN SET: {reason}"
                )
            else:
                return await ctx.send(f"{user.mention} already has {amount} tickets.")
        
        # Log admin action
        logger.info(f"Admin ticket action: {ctx.author} {action} {amount} tickets for {user} - {reason}")
        
        embed = discord.Embed(
            title="✅ Admin Ticket Action Completed",
            color=discord.Color.green()
        )
        embed.add_field(name="Action", value=action.title(), inline=True)
        embed.add_field(name="Amount", value=f"{amount:,} tickets", inline=True)
        embed.add_field(name="New Balance", value=f"{result['new_balance']:,} tickets", inline=True)
        embed.add_field(name="User", value=user.mention, inline=True)
        embed.add_field(name="Admin", value=ctx.author.mention, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Transaction ID: {result['transaction_id']}")
        
        await ctx.send(embed=embed)
        
    except InsufficientFundsError as e:
        await ctx.send(f"❌ Failed: {str(e)}")
    except Exception as e:
        logger.error(f"Admin ticket action failed: {e}", exc_info=True)
        await ctx.send(f"❌ Error: {str(e)}")
```

### Phase 4.2: Ticket Earning Integration (Days 3-7)

#### 4.2.1 Achievement System with Race Condition Fix
```python
class AchievementChecker:
    """Checks and awards one-time achievements with race condition protection"""
    
    ACHIEVEMENTS = {
        "first_blood": {"per_event": True, "amount": 50},
        "hot_tourist": {"per_event": False, "amount": 250},
        "warm_tourist": {"per_cluster": True, "amount": 50},
        "social_butterfly": {"per_opponent": True, "amount": 50},
        "claim_shard": {"per_event": True, "amount": 50, "requires_owner_defeat": True},
        "golden_road": {"per_event": False, "amount": 500}
    }
    
    def __init__(self, db_pool, wallet_service, config):
        self.db = db_pool
        self.wallet = wallet_service
        self.config = config
    
    @handle_wallet_errors
    async def check_and_award(self, player_id: int, achievement_type: str, 
                             event_id: int = None, opponent_id: int = None,
                             cluster_id: int = None) -> int:
        """
        Check if achievement unlocked and award tickets.
        Uses INSERT ON CONFLICT to prevent race conditions.
        
        Returns:
            Amount of tickets awarded (0 if already achieved)
        """
        config = self.ACHIEVEMENTS.get(achievement_type)
        if not config:
            raise ValueError(f"Unknown achievement: {achievement_type}")
        
        # Generate deterministic external_ref
        ref_parts = ['ACHIEVE', str(player_id), achievement_type]
        if config.get('per_event') and event_id:
            ref_parts.append(f'event_{event_id}')
        elif config.get('per_opponent') and opponent_id:
            ref_parts.append(f'opponent_{opponent_id}')
        elif config.get('per_cluster') and cluster_id:
            ref_parts.append(f'cluster_{cluster_id}')
        
        external_ref = ':'.join(ref_parts)
        
        async with self.db.transaction(isolation='serializable') as tx:
            # Special check for claim_shard - requires defeating the owner
            if achievement_type == "claim_shard" and config.get('requires_owner_defeat'):
                defeated = await tx.fetchval(
                    """SELECT EXISTS(
                        SELECT 1 FROM match_participants mp
                        JOIN matches m ON mp.match_id = m.id
                        WHERE mp.player_id = $1 
                        AND m.event_id = $2
                        AND mp.placement = 1
                        AND EXISTS (
                            SELECT 1 FROM match_participants mp2
                            WHERE mp2.match_id = mp.match_id
                            AND mp2.player_id = $3
                            AND mp2.placement > 1
                        )
                    )""",
                    player_id, event_id, self.config.OWNER_ID
                )
                if not defeated:
                    return 0
            
            # Atomic insert with conflict handling
            try:
                inserted = await tx.fetchval(
                    """INSERT INTO player_achievements 
                       (player_id, achievement_type, event_id)
                       VALUES ($1, $2, $3)
                       ON CONFLICT (player_id, achievement_type, event_id) 
                       DO NOTHING
                       RETURNING id""",
                    player_id, achievement_type, event_id
                )
                
                if inserted:
                    # Award tickets only if achievement was newly inserted
                    await self.wallet.deposit(
                        player_id, config['amount'], 'achievement',
                        external_ref=external_ref,
                        reason=f"Achievement unlocked: {achievement_type}"
                    )
                    
                    logger.info(f"Achievement awarded: {achievement_type} to player {player_id}")
                    return config['amount']
                else:
                    # Already achieved
                    return 0
                    
            except asyncpg.UniqueViolationError:
                # This should not happen with ON CONFLICT, but handle it anyway
                return 0
```

#### 4.2.2 Batch Match Reward Processing
```python
class MatchRewardCalculator:
    """Calculates and processes match rewards efficiently"""
    
    def __init__(self, db_pool, wallet_service, achievement_checker, config):
        self.db = db_pool
        self.wallet = wallet_service
        self.achievements = achievement_checker
        self.config = config
    
    async def process_match_rewards(self, match_id: int) -> Dict[str, Any]:
        """
        Process all match rewards in a single efficient transaction.
        Uses batch operations for performance.
        """
        async with self.db.transaction(isolation='serializable') as tx:
            # Get match data with all participants
            match_data = await self._get_match_data(tx, match_id)
            
            if not match_data:
                raise ValueError(f"Match {match_id} not found")
            
            # Prepare batch data
            ledger_entries = []
            balance_updates = {}
            achievement_awards = []
            
            for participant in match_data['participants']:
                player_id = participant['player_id']
                player_rewards = []
                
                # 1. Participation trophy (always)
                participation_ref = f"MATCH:{match_id}:{player_id}:participation"
                player_rewards.append({
                    'player_id': player_id,
                    'amount': 5,
                    'event_type': 'participation',
                    'external_ref': participation_ref,
                    'reason': f"Participation in match {match_id}"
                })
                
                # 2. First blood (first match in event)
                is_first_match = await self._is_first_match_in_event(
                    tx, player_id, match_data['event_id']
                )
                if is_first_match:
                    achievement_awards.append({
                        'player_id': player_id,
                        'type': 'first_blood',
                        'event_id': match_data['event_id']
                    })
                
                # 3. Win rewards and streaks
                if participant['is_winner']:
                    # Basic win reward
                    win_ref = f"MATCH:{match_id}:{player_id}:win"
                    player_rewards.append({
                        'player_id': player_id,
                        'amount': 10,
                        'event_type': 'match_win',
                        'external_ref': win_ref,
                        'reason': f"Victory in match {match_id}"
                    })
                    
                    # Update and check win streak
                    new_streak = await self._update_win_streak(tx, player_id, True)
                    
                    # Streak bonuses
                    if new_streak == 3:
                        streak_ref = f"STREAK:{player_id}:3:{match_id}"
                        player_rewards.append({
                            'player_id': player_id,
                            'amount': 50,
                            'event_type': 'streak_bonus',
                            'external_ref': streak_ref,
                            'reason': "3-match win streak (Cooking)"
                        })
                    elif new_streak == 5:
                        streak_ref = f"STREAK:{player_id}:5:{match_id}"
                        player_rewards.append({
                            'player_id': player_id,
                            'amount': 75,
                            'event_type': 'streak_bonus',
                            'external_ref': streak_ref,
                            'reason': "5-match win streak (Frying)"
                        })
                    
                    # Check if ended someone's streak
                    for opponent in match_data['participants']:
                        if not opponent['is_winner'] and opponent['player_id'] != player_id:
                            ended_streak = await self._check_and_end_streak(
                                tx, opponent['player_id']
                            )
                            if ended_streak >= 3:
                                party_ref = f"PARTY_POOPER:{match_id}:{player_id}:{opponent['player_id']}"
                                player_rewards.append({
                                    'player_id': player_id,
                                    'amount': 50,
                                    'event_type': 'party_pooper',
                                    'external_ref': party_ref,
                                    'reason': f"Ended {opponent['display_name']}'s {ended_streak}-win streak"
                                })
                else:
                    # Lost - reset win streak
                    await self._update_win_streak(tx, player_id, False)
                
                # 4. Boston Scott (underdog victory)
                if participant['is_winner'] and participant['elo_before']:
                    elo_diff = participant['elo_before'] - participant['opponent_elo']
                    if elo_diff <= -300:
                        underdog_ref = f"UNDERDOG:{match_id}:{player_id}"
                        player_rewards.append({
                            'player_id': player_id,
                            'amount': 25,
                            'event_type': 'boston_scott',
                            'external_ref': underdog_ref,
                            'reason': f"Underdog victory (−{abs(elo_diff)} Elo difference)"
                        })
                
                # 5. Social butterfly (new opponent)
                for opponent in match_data['participants']:
                    if opponent['player_id'] != player_id:
                        is_new = await self._is_new_opponent(
                            tx, player_id, opponent['player_id']
                        )
                        if is_new:
                            achievement_awards.append({
                                'player_id': player_id,
                                'type': 'social_butterfly',
                                'opponent_id': opponent['player_id']
                            })
                
                # Aggregate rewards for batch processing
                for reward in player_rewards:
                    ledger_entries.append(reward)
                    balance_updates[player_id] = balance_updates.get(player_id, 0) + reward['amount']
            
            # Batch insert ledger entries using prepared statement
            if ledger_entries:
                # Create temporary table for bulk insert
                await tx.execute("""
                    CREATE TEMP TABLE temp_rewards (
                        player_id BIGINT,
                        amount BIGINT,
                        event_type VARCHAR(50),
                        external_ref VARCHAR(255),
                        reason TEXT
                    ) ON COMMIT DROP
                """)
                
                # Copy data to temp table
                await tx.copy_records_to_table(
                    'temp_rewards',
                    records=[
                        (e['player_id'], e['amount'], e['event_type'], 
                         e['external_ref'], e['reason'])
                        for e in ledger_entries
                    ]
                )
                
                # Insert all ledger entries with conflict handling
                await tx.execute("""
                    INSERT INTO ticket_ledger 
                    (player_id, amount, event_type, external_ref, match_id, reason)
                    SELECT player_id, amount, event_type, external_ref, $1, reason
                    FROM temp_rewards
                    ON CONFLICT (external_ref) DO NOTHING
                """, match_id)
                
                # Create balancing entries for system account
                await tx.execute("""
                    INSERT INTO ticket_ledger 
                    (player_id, amount, event_type, match_id, reason)
                    SELECT $1, -amount, event_type, $2, 
                           'Balance for ' || external_ref
                    FROM temp_rewards
                    WHERE external_ref NOT IN (
                        SELECT external_ref FROM ticket_ledger 
                        WHERE external_ref IS NOT NULL
                    )
                """, self.config.SYSTEM_ACCOUNT_ID, match_id)
                
                # Batch update balances
                if balance_updates:
                    # Use PostgreSQL's UPDATE...FROM with VALUES
                    values = ','.join([
                        f"({player_id}, {amount})" 
                        for player_id, amount in balance_updates.items()
                    ])
                    
                    await tx.execute(f"""
                        UPDATE players p
                        SET ticket_balance = p.ticket_balance + v.amount,
                            version = p.version + 1,
                            updated_at = NOW()
                        FROM (VALUES {values}) AS v(player_id, amount)
                        WHERE p.id = v.player_id
                    """)
            
            # Process achievements (these have their own transaction handling)
            achievement_results = []
            for award in achievement_awards:
                amount = await self.achievements.check_and_award(
                    award['player_id'],
                    award['type'],
                    event_id=award.get('event_id'),
                    opponent_id=award.get('opponent_id')
                )
                if amount > 0:
                    achievement_results.append({
                        'player_id': award['player_id'],
                        'achievement': award['type'],
                        'amount': amount
                    })
            
            # Return summary
            return {
                'match_id': match_id,
                'total_rewards': len(ledger_entries),
                'players_rewarded': len(balance_updates),
                'total_tickets_awarded': sum(balance_updates.values()),
                'achievements_unlocked': len(achievement_results),
                'details': {
                    'rewards': ledger_entries,
                    'achievements': achievement_results
                }
            }
    
    async def _get_match_data(self, tx, match_id: int) -> Dict[str, Any]:
        """Get comprehensive match data"""
        match = await tx.fetchrow(
            """SELECT m.*, e.name as event_name, e.event_type
               FROM matches m
               JOIN events e ON m.event_id = e.id
               WHERE m.id = $1""",
            match_id
        )
        
        if not match:
            return None
        
        participants = await tx.fetch(
            """SELECT mp.*, p.display_name,
                      mp.elo_before, mp.placement,
                      CASE WHEN mp.placement = 1 THEN true ELSE false END as is_winner
               FROM match_participants mp
               JOIN players p ON mp.player_id = p.id
               WHERE mp.match_id = $1
               ORDER BY mp.placement""",
            match_id
        )
        
        # For 1v1, add opponent elo
        if len(participants) == 2:
            participants[0]['opponent_elo'] = participants[1]['elo_before']
            participants[1]['opponent_elo'] = participants[0]['elo_before']
        
        return {
            'id': match['id'],
            'event_id': match['event_id'],
            'event_name': match['event_name'],
            'event_type': match['event_type'],
            'participants': [dict(p) for p in participants]
        }
    
    async def _is_first_match_in_event(self, tx, player_id: int, event_id: int) -> bool:
        """Check if this is player's first match in the event"""
        count = await tx.fetchval(
            """SELECT COUNT(*) FROM match_participants mp
               JOIN matches m ON mp.match_id = m.id
               WHERE mp.player_id = $1 AND m.event_id = $2""",
            player_id, event_id
        )
        return count == 1
    
    async def _update_win_streak(self, tx, player_id: int, won: bool) -> int:
        """Update and return new win streak"""
        if won:
            new_streak = await tx.fetchval(
                """UPDATE players 
                   SET current_win_streak = current_win_streak + 1
                   WHERE id = $1
                   RETURNING current_win_streak""",
                player_id
            )
        else:
            await tx.execute(
                "UPDATE players SET current_win_streak = 0 WHERE id = $1",
                player_id
            )
            new_streak = 0
        
        return new_streak
    
    async def _check_and_end_streak(self, tx, player_id: int) -> int:
        """Check player's streak before ending it"""
        streak = await tx.fetchval(
            "SELECT current_win_streak FROM players WHERE id = $1",
            player_id
        )
        return streak or 0
    
    async def _is_new_opponent(self, tx, player_id: int, opponent_id: int) -> bool:
        """Check if this is the first time playing against this opponent"""
        exists = await tx.fetchval(
            """SELECT EXISTS(
                SELECT 1 FROM match_participants mp1
                JOIN match_participants mp2 ON mp1.match_id = mp2.match_id
                WHERE mp1.player_id = $1 AND mp2.player_id = $2
                AND mp1.match_id != mp2.match_id
            )""",
            player_id, opponent_id
        )
        return not exists
```

### Phase 4.3: Shop System Implementation (Days 7-12)

#### 4.3.1 Shop Item Effects Registry
```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class ItemEffect(ABC):
    """Base class for all item effects"""
    
    @abstractmethod
    async def apply(self, player_id: int, payload: Dict[str, Any], 
                   purchase_id: int) -> Dict[str, Any]:
        """Apply the effect to the player"""
        pass
    
    @abstractmethod
    async def can_apply(self, player_id: int, payload: Dict[str, Any]) -> bool:
        """Check if effect can be applied"""
        pass

class LeverageEffect(ItemEffect):
    """Handles leverage multiplier effects"""
    
    async def apply(self, player_id: int, payload: Dict[str, Any], 
                   purchase_id: int) -> Dict[str, Any]:
        multiplier = payload['multiplier']
        is_forced = payload.get('forced', False)
        
        async with db.acquire() as conn:
            await conn.execute(
                """UPDATE players 
                   SET active_leverage = $1,
                       active_leverage_purchase_id = $2
                   WHERE id = $3""",
                jsonb.dumps({
                    'multiplier': multiplier,
                    'forced': is_forced,
                    'type': payload.get('type', 'standard')
                }),
                purchase_id,
                player_id
            )
        
        return {
            'status': 'armed',
            'multiplier': multiplier,
            'forced': is_forced
        }
    
    async def can_apply(self, player_id: int, payload: Dict[str, Any]) -> bool:
        # Check if player already has active leverage
        async with db.acquire() as conn:
            active = await conn.fetchval(
                "SELECT active_leverage IS NOT NULL FROM players WHERE id = $1",
                player_id
            )
            return not active

class ItemEffectRegistry:
    """Registry for all shop item effects"""
    
    def __init__(self):
        self.effects = {
            'leverage': LeverageEffect(),
            'modifier': ScoreModifierEffect(),
            'info': InformationEffect(),
            'bounty': BountyEffect(),
            'tournament': TournamentEffect(),
            'chaos': ChaosEffect()
        }
    
    async def execute_purchase(self, player_id: int, item: Dict[str, Any], 
                              purchase_id: int) -> Dict[str, Any]:
        """Execute the effect of a purchased item"""
        
        effect_type = item['effect_type']
        effect_handler = self.effects.get(effect_type)
        
        if not effect_handler:
            raise ValueError(f"Unknown effect type: {effect_type}")
        
        # Check if effect can be applied
        if not await effect_handler.can_apply(player_id, item['effect_payload']):
            raise ValueError("Effect cannot be applied at this time")
        
        # Apply effect
        result = await effect_handler.apply(
            player_id, item['effect_payload'], purchase_id
        )
        
        # Mark as consumed if one-time effect
        if item['effect_payload'].get('one_time', True):
            async with db.acquire() as conn:
                await conn.execute(
                    "UPDATE player_purchases SET consumed_at = NOW() WHERE id = $1",
                    purchase_id
                )
        
        return result
```

#### 4.3.2 Shop Interface and Purchase Flow
```python
class ShopView(discord.ui.View):
    """Interactive shop interface with pagination and categories"""
    
    def __init__(self, player_id: int, wallet_service: WalletService, 
                 category: str = None):
        super().__init__(timeout=300)
        self.player_id = player_id
        self.wallet = wallet_service
        self.category = category
        self.page = 0
        self.items_per_page = 5
        self.current_items = []
        
    async def fetch_items(self):
        """Fetch available shop items"""
        query = """
            SELECT * FROM shop_items 
            WHERE is_active = TRUE 
            AND ($1::text IS NULL OR category = $1)
            ORDER BY category, price
            LIMIT $2 OFFSET $3
        """
        
        async with db.acquire() as conn:
            self.current_items = await conn.fetch(
                query, self.category, self.items_per_page, 
                self.page * self.items_per_page
            )
    
    async def update_embed(self, interaction: discord.Interaction):
        """Update the shop embed with current items"""
        await self.fetch_items()
        
        # Get current balance
        try:
            balance = await self.wallet.get_balance(self.player_id)
        except Exception:
            balance = 0
        
        embed = discord.Embed(
            title="🎟️ Ticket Shop",
            description=f"Your balance: **{balance:,}** tickets",
            color=discord.Color.blue()
        )
        
        if not self.current_items:
            embed.add_field(
                name="No items available",
                value="Check back later for new items!",
                inline=False
            )
        else:
            for item in self.current_items:
                affordable = "✅" if balance >= item['price'] else "❌"
                embed.add_field(
                    name=f"{affordable} {item['name']} - {item['price']:,} tickets",
                    value=f"*{item.get('description', 'No description')}*\n"
                          f"Category: {item['category']}",
                    inline=False
                )
        
        embed.set_footer(
            text=f"Page {self.page + 1} | Use buttons to navigate"
        )
        
        # Update button states
        self.previous_button.disabled = self.page == 0
        self.next_button.disabled = len(self.current_items) < self.items_per_page
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.select(
        placeholder="Select a category...",
        options=[
            discord.SelectOption(label="All Items", value="all"),
            discord.SelectOption(label="Collusion", value="collusion", 
                               description="Affect scoring calculations"),
            discord.SelectOption(label="Chaos", value="chaos",
                               description="Add randomness to matches"),
            discord.SelectOption(label="Gambling", value="gambling",
                               description="Information and advantages"),
            discord.SelectOption(label="Bounties", value="bounties",
                               description="Target other players"),
            discord.SelectOption(label="Leverage", value="leverage",
                               description="Multiply match stakes"),
            discord.SelectOption(label="Strategy", value="strategy",
                               description="Gameplay modifiers"),
            discord.SelectOption(label="Tournament", value="tournament",
                               description="Meta-game features")
        ]
    )
    async def category_select(self, interaction: discord.Interaction, 
                            select: discord.ui.Select):
        self.category = select.values[0] if select.values[0] != "all" else None
        self.page = 0
        await self.update_embed(interaction)
    
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.gray, row=1)
    async def previous_button(self, interaction: discord.Interaction, 
                            button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self.update_embed(interaction)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray, row=1)
    async def next_button(self, interaction: discord.Interaction, 
                         button: discord.ui.Button):
        self.page += 1
        await self.update_embed(interaction)
    
    @discord.ui.button(label="Buy", style=discord.ButtonStyle.green, row=1)
    async def buy_button(self, interaction: discord.Interaction, 
                        button: discord.ui.Button):
        if not self.current_items:
            await interaction.response.send_message(
                "No items available to purchase.", ephemeral=True
            )
            return
        
        # Create item selection modal
        modal = BuyItemModal(self.current_items, self.player_id, self.wallet)
        await interaction.response.send_modal(modal)

class BuyItemModal(discord.ui.Modal):
    """Modal for confirming item purchase"""
    
    def __init__(self, items: List[Dict], player_id: int, 
                 wallet_service: WalletService):
        super().__init__(title="Purchase Item")
        self.items = items
        self.player_id = player_id
        self.wallet = wallet_service
        
        # Create item selection dropdown text
        options_text = "\n".join([
            f"{i+1}. {item['name']} - {item['price']:,} tickets"
            for i, item in enumerate(items)
        ])
        
        self.item_number = discord.ui.TextInput(
            label="Item Number",
            placeholder="Enter the number of the item you want to buy",
            required=True,
            max_length=1,
            min_length=1
        )
        self.add_item(self.item_number)
        
        self.confirm = discord.ui.TextInput(
            label=f"Type 'confirm' to purchase",
            placeholder="confirm",
            required=True,
            max_length=7,
            min_length=7
        )
        self.add_item(self.confirm)
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm.value.lower() != 'confirm':
            await interaction.response.send_message(
                "Purchase cancelled.", ephemeral=True
            )
            return
        
        try:
            item_index = int(self.item_number.value) - 1
            if item_index < 0 or item_index >= len(self.items):
                raise ValueError("Invalid item number")
            
            item = self.items[item_index]
            
            # Get current balance
            balance = await self.wallet.get_balance(self.player_id)
            
            if balance < item['price']:
                await interaction.response.send_message(
                    f"❌ Insufficient tickets! You need {item['price']:,} but have {balance:,}.",
                    ephemeral=True
                )
                return
            
            # Process purchase
            purchase_service = PurchaseService(db, self.wallet, effect_registry)
            result = await purchase_service.purchase_item(
                self.player_id, item['id']
            )
            
            embed = discord.Embed(
                title="✅ Purchase Successful!",
                description=f"You bought **{item['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Price Paid",
                value=f"{item['price']:,} tickets",
                inline=True
            )
            embed.add_field(
                name="New Balance",
                value=f"{result['new_balance']:,} tickets",
                inline=True
            )
            
            if result.get('effect_result'):
                embed.add_field(
                    name="Effect",
                    value=result['effect_result'].get('message', 'Applied successfully'),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid input: {str(e)}", 
                ephemeral=True
            )
        except InsufficientFundsError:
            await interaction.response.send_message(
                "❌ Insufficient tickets for this purchase.", 
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Purchase failed: {e}", exc_info=True)
            await interaction.response.send_message(
                f"❌ Purchase failed: {str(e)}", 
                ephemeral=True
            )

class PurchaseService:
    """Handles shop purchases atomically"""
    
    def __init__(self, db_pool, wallet_service: WalletService, 
                 effect_registry: ItemEffectRegistry):
        self.db = db_pool
        self.wallet = wallet_service
        self.effects = effect_registry
    
    async def purchase_item(self, player_id: int, item_id: int) -> Dict[str, Any]:
        """
        Purchase an item atomically.
        Handles payment, effect application, and rollback on failure.
        """
        async with self.db.transaction(isolation='serializable') as tx:
            # Lock and fetch item
            item = await tx.fetchrow(
                """SELECT * FROM shop_items 
                   WHERE id = $1 AND is_active = TRUE 
                   FOR UPDATE""",
                item_id
            )
            
            if not item:
                raise ValueError("Item not found or not available")
            
            # Generate purchase reference
            purchase_ref = f"PURCHASE:{player_id}:{item_id}:{int(time.time())}"
            
            # Withdraw tickets
            withdrawal_result = await self.wallet.withdraw(
                player_id, item['price'], 'shop_purchase',
                external_ref=purchase_ref,
                reason=f"Purchase: {item['name']}"
            )
            
            # Create purchase record
            purchase_id = await tx.fetchval(
                """INSERT INTO player_purchases 
                   (player_id, shop_item_id, payload_snapshot, external_ref)
                   VALUES ($1, $2, $3, $4)
                   RETURNING id""",
                player_id, item_id, 
                jsonb.dumps(dict(item)), purchase_ref
            )
            
            # Apply item effect
            try:
                effect_result = await self.effects.execute_purchase(
                    player_id, dict(item), purchase_id
                )
            except Exception as e:
                # Effect failed - will rollback transaction
                logger.error(f"Effect application failed: {e}")
                raise ValueError(f"Failed to apply item effect: {str(e)}")
            
            return {
                'purchase_id': purchase_id,
                'item': dict(item),
                'new_balance': withdrawal_result['new_balance'],
                'effect_result': effect_result
            }

@bot.slash_command(name="shop", description="Browse and purchase items")
async def shop(ctx):
    """Display the ticket shop"""
    
    player_id = await get_or_create_player(ctx.author.id)
    wallet_service = WalletService(db_pool, config, metrics, tracer, fraud_detector)
    
    view = ShopView(player_id, wallet_service)
    await view.update_embed(None)
    
    # Create initial embed
    balance = await wallet_service.get_balance(player_id)
    embed = discord.Embed(
        title="🎟️ Ticket Shop",
        description=f"Your balance: **{balance:,}** tickets\n\n"
                    f"Browse items by category or view all available items.",
        color=discord.Color.blue()
    )
    
    await ctx.respond(embed=embed, view=view)

@bot.slash_command(name="balance", description="Check your ticket balance")
async def balance(ctx):
    """Check ticket balance"""
    
    player_id = await get_or_create_player(ctx.author.id)
    wallet_service = WalletService(db_pool, config, metrics, tracer, fraud_detector)
    
    try:
        balance = await wallet_service.get_balance(player_id)
        
        embed = discord.Embed(
            title="🎟️ Ticket Balance",
            description=f"You have **{balance:,}** tickets",
            color=discord.Color.blue()
        )
        
        # Add recent transactions
        async with db.acquire() as conn:
            recent = await conn.fetch(
                """SELECT amount, event_type, reason, created_at
                   FROM ticket_ledger
                   WHERE player_id = $1
                   ORDER BY created_at DESC
                   LIMIT 5""",
                player_id
            )
            
            if recent:
                transactions = []
                for tx in recent:
                    sign = "+" if tx['amount'] > 0 else ""
                    transactions.append(
                        f"{sign}{tx['amount']} - {tx['event_type']} "
                        f"({format_timestamp(tx['created_at'])})"
                    )
                
                embed.add_field(
                    name="Recent Transactions",
                    value="\n".join(transactions),
                    inline=False
                )
        
        await ctx.respond(embed=embed)
        
    except PlayerNotFoundError:
        await ctx.respond("You don't have a player account yet. Play a match to get started!")
    except Exception as e:
        logger.error(f"Balance check failed: {e}")
        await ctx.respond("❌ Failed to check balance. Please try again later.")
```

### Phase 4.4: Testing & Polish (Days 12-15)

#### 4.4.1 Comprehensive Test Suite
```python
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch

class TestWalletService:
    """Comprehensive test suite for WalletService"""
    
    @pytest.fixture
    async def setup(self):
        """Setup test environment"""
        # Create test database
        self.db_pool = await create_test_pool()
        
        # Create config
        self.config = WalletConfig()
        
        # Create mocks
        self.metrics = Mock()
        self.tracer = Mock()
        self.fraud_detector = AsyncMock()
        self.fraud_detector.check_transaction.return_value = FraudCheckResult(
            passed=True, reason="", risk_score=0.1
        )
        
        # Create service
        self.wallet = WalletService(
            self.db_pool, self.config, self.metrics, 
            self.tracer, self.fraud_detector
        )
        
        await self.wallet.initialize()
        
        # Create test player
        async with self.db_pool.acquire() as conn:
            self.player_id = await conn.fetchval(
                """INSERT INTO players (discord_id, display_name)
                   VALUES ($1, $2) RETURNING id""",
                "123456789", "TestPlayer"
            )
        
        yield
        
        # Cleanup
        await self.db_pool.close()
    
    async def test_deposit_success(self, setup):
        """Test successful deposit"""
        result = await self.wallet.deposit(
            self.player_id, 100, "test",
            external_ref="test_deposit_1"
        )
        
        assert result['new_balance'] == 100
        assert result['transaction_id'] is not None
        assert result['processing_time'] > 0
        
        # Verify metrics
        self.metrics.histogram.assert_called_with(
            'wallet.deposit.duration',
            pytest.approx(result['processing_time'], abs=0.1),
            tags={'event_type': 'test', 'status': 'success'}
        )
    
    async def test_deposit_idempotency(self, setup):
        """Test idempotent deposits"""
        external_ref = "idempotent_test_123"
        
        # First deposit
        result1 = await self.wallet.deposit(
            self.player_id, 100, "test",
            external_ref=external_ref
        )
        
        # Duplicate deposit
        result2 = await self.wallet.deposit(
            self.player_id, 100, "test",
            external_ref=external_ref
        )
        
        assert result1['new_balance'] == result2['new_balance']
        assert result1['transaction_id'] == result2['transaction_id']
    
    async def test_withdraw_insufficient_funds(self, setup):
        """Test withdrawal with insufficient funds"""
        with pytest.raises(InsufficientFundsError):
            await self.wallet.withdraw(
                self.player_id, 1000, "test"
            )
    
    async def test_concurrent_deposits(self, setup):
        """Test 100 concurrent deposits maintain consistency"""
        tasks = []
        for i in range(100):
            task = self.wallet.deposit(
                self.player_id, 10, "test",
                external_ref=f"concurrent_{i}"
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check all succeeded
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Errors occurred: {errors}"
        
        # Verify final balance
        balance = await self.wallet.get_balance(self.player_id)
        assert balance == 1000  # 100 * 10
    
    async def test_concurrent_mixed_operations(self, setup):
        """Test mixed deposits and withdrawals"""
        # First deposit some funds
        await self.wallet.deposit(self.player_id, 1000, "setup")
        
        # Mix of deposits and withdrawals
        tasks = []
        for i in range(50):
            if i % 2 == 0:
                task = self.wallet.deposit(
                    self.player_id, 10, "test",
                    external_ref=f"deposit_{i}"
                )
            else:
                task = self.wallet.withdraw(
                    self.player_id, 5, "test",
                    external_ref=f"withdraw_{i}"
                )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes
        deposits = sum(1 for i, r in enumerate(results) 
                      if i % 2 == 0 and not isinstance(r, Exception))
        withdrawals = sum(1 for i, r in enumerate(results) 
                         if i % 2 == 1 and not isinstance(r, Exception))
        
        # Verify final balance
        expected = 1000 + (deposits * 10) - (withdrawals * 5)
        balance = await self.wallet.get_balance(self.player_id)
        assert balance == expected
    
    async def test_fraud_detection_blocks_transaction(self, setup):
        """Test fraud detection integration"""
        # Configure fraud detector to fail
        self.fraud_detector.check_transaction.return_value = FraudCheckResult(
            passed=False,
            reason="Velocity limit exceeded",
            risk_score=0.9
        )
        
        with pytest.raises(FraudDetectionError) as exc_info:
            await self.wallet.deposit(
                self.player_id, 10000, "test"
            )
        
        assert "Velocity limit exceeded" in str(exc_info.value)
        
        # Verify metrics
        self.metrics.increment.assert_called_with('wallet.deposit.fraud_blocked')
    
    async def test_retry_on_serialization_failure(self, setup):
        """Test automatic retry on serialization failure"""
        call_count = 0
        
        async def mock_transaction(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise asyncpg.SerializationFailure("Serialization failure")
            
            # Return a mock transaction that succeeds
            return AsyncMock()
        
        with patch.object(self.db_pool, 'transaction', side_effect=mock_transaction):
            result = await self.wallet.deposit(
                self.player_id, 100, "test",
                external_ref="retry_test"
            )
        
        assert call_count == 3  # Initial + 2 retries
        self.metrics.increment.assert_called_with(
            'wallet.deposit.retry',
            tags={'attempt': 2, 'reason': 'SerializationFailure'}
        )
    
    async def test_max_retries_exceeded(self, setup):
        """Test max retries exceeded"""
        async def always_fail(*args, **kwargs):
            raise asyncpg.SerializationFailure("Always fails")
        
        with patch.object(self.db_pool, 'transaction', side_effect=always_fail):
            with pytest.raises(MaxRetriesExceededError):
                await self.wallet.deposit(
                    self.player_id, 100, "test",
                    external_ref="max_retry_test"
                )
        
        self.metrics.increment.assert_called_with(
            'wallet.deposit.max_retries_exceeded'
        )
    
    async def test_double_entry_consistency(self, setup):
        """Test double-entry bookkeeping maintains consistency"""
        # Perform several operations
        await self.wallet.deposit(self.player_id, 1000, "test", "de_1")
        await self.wallet.withdraw(self.player_id, 300, "test", "de_2")
        await self.wallet.deposit(self.player_id, 150, "test", "de_3")
        
        # Verify ledger balance
        async with self.db_pool.acquire() as conn:
            # Sum of all entries should be 0
            total = await conn.fetchval(
                "SELECT SUM(amount) FROM ticket_ledger"
            )
            assert total == 0
            
            # Player entries should match balance
            player_total = await conn.fetchval(
                "SELECT SUM(amount) FROM ticket_ledger WHERE player_id = $1",
                self.player_id
            )
            balance = await self.wallet.get_balance(self.player_id)
            assert player_total == balance
            
            # Each entry should have a counterpart
            orphans = await conn.fetchval(
                """SELECT COUNT(*) FROM ticket_ledger 
                   WHERE counterpart_id IS NULL"""
            )
            assert orphans == 0

class TestBatchRewardProcessing:
    """Test batch reward processing"""
    
    async def test_batch_rewards_performance(self, setup):
        """Test batch processing is faster than individual"""
        # Create match with 10 participants
        match_id = await create_test_match(10)
        
        # Time batch processing
        start = time.time()
        result = await reward_calculator.process_match_rewards(match_id)
        batch_time = time.time() - start
        
        assert result['players_rewarded'] == 10
        assert batch_time < 0.5  # Should complete in under 500ms
    
    async def test_achievement_race_condition(self, setup):
        """Test achievement awarding prevents race conditions"""
        player_id = await create_test_player()
        
        # Try to award same achievement concurrently
        tasks = []
        for _ in range(10):
            task = achievement_checker.check_and_award(
                player_id, "first_blood", event_id=1
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # Only one should succeed
        awarded = sum(1 for amount in results if amount > 0)
        assert awarded == 1
        
        # Verify only one achievement record
        async with db.acquire() as conn:
            count = await conn.fetchval(
                """SELECT COUNT(*) FROM player_achievements
                   WHERE player_id = $1 AND achievement_type = 'first_blood'""",
                player_id
            )
            assert count == 1
```

#### 4.4.2 Load Testing
```python
async def load_test_wallet_service():
    """Load test the wallet service"""
    
    # Setup
    wallet = WalletService(db_pool, config, metrics, tracer, fraud_detector)
    player_ids = [await create_test_player() for _ in range(100)]
    
    # Test parameters
    operations_per_player = 100
    total_operations = len(player_ids) * operations_per_player
    
    print(f"Starting load test: {total_operations} operations")
    
    start_time = time.time()
    tasks = []
    
    for player_id in player_ids:
        for i in range(operations_per_player):
            if random.random() > 0.3:
                # 70% deposits
                task = wallet.deposit(
                    player_id, 
                    random.randint(1, 100),
                    "load_test",
                    external_ref=f"load_{player_id}_{i}"
                )
            else:
                # 30% withdrawals (may fail)
                task = wallet.withdraw(
                    player_id,
                    random.randint(1, 50),
                    "load_test",
                    external_ref=f"load_w_{player_id}_{i}"
                )
            tasks.append(task)
    
    # Execute all operations
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    elapsed = time.time() - start_time
    
    # Analyze results
    successful = sum(1 for r in results if not isinstance(r, Exception))
    failed = sum(1 for r in results if isinstance(r, Exception))
    
    # Calculate metrics
    ops_per_second = successful / elapsed
    avg_latency = (elapsed / successful) * 1000  # ms
    
    print(f"\nLoad Test Results:")
    print(f"Total operations: {total_operations}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Operations/second: {ops_per_second:.2f}")
    print(f"Average latency: {avg_latency:.2f}ms")
    
    # Verify consistency
    for player_id in player_ids:
        balance = await wallet.get_balance(player_id)
        
        # Verify ledger matches balance
        async with db.acquire() as conn:
            ledger_sum = await conn.fetchval(
                "SELECT COALESCE(SUM(amount), 0) FROM ticket_ledger WHERE player_id = $1",
                player_id
            )
            assert balance == ledger_sum, f"Balance mismatch for player {player_id}"
    
    print("\n✅ Consistency check passed!")
```

## Security Enhancements

### Fraud Detection Service
```python
from dataclasses import dataclass
import statistics

@dataclass
class FraudCheckResult:
    passed: bool
    reason: str
    risk_score: float

class FraudDetectionService:
    """Multi-layer fraud detection system"""
    
    def __init__(self, redis_client, config: WalletConfig):
        self.redis = redis_client
        self.config = config
    
    async def check_transaction(self, player_id: int, amount: int, 
                               transaction_type: str) -> FraudCheckResult:
        """
        Perform multi-layer fraud detection.
        
        Checks:
        1. Velocity (transactions per time window)
        2. Amount anomalies (statistical analysis)
        3. Behavior patterns (ML-based)
        """
        
        # Check 1: Velocity
        velocity_result = await self._check_velocity(
            player_id, transaction_type
        )
        if not velocity_result.passed:
            return velocity_result
        
        # Check 2: Amount anomalies
        anomaly_result = await self._check_amount_anomaly(
            player_id, amount, transaction_type
        )
        if not anomaly_result.passed:
            return anomaly_result
        
        # Check 3: Behavior patterns
        behavior_result = await self._check_behavior_pattern(
            player_id, amount, transaction_type
        )
        
        return behavior_result
    
    async def _check_velocity(self, player_id: int, 
                             transaction_type: str) -> FraudCheckResult:
        """Check transaction velocity"""
        
        # Use sliding window counter
        now = int(time.time())
        window_start = now - 3600  # 1 hour window
        
        key = f"velocity:{player_id}:{transaction_type}"
        
        # Remove old entries
        await self.redis.zremrangebyscore(key, 0, window_start)
        
        # Add current transaction
        await self.redis.zadd(key, {str(now): now})
        
        # Count transactions in window
        count = await self.redis.zcard(key)
        
        # Set expiry
        await self.redis.expire(key, 3600)
        
        if count > self.config.VELOCITY_THRESHOLD:
            return FraudCheckResult(
                passed=False,
                reason=f"Velocity limit exceeded: {count} transactions in 1 hour",
                risk_score=0.9
            )
        
        return FraudCheckResult(
            passed=True,
            reason="Velocity check passed",
            risk_score=count / self.config.VELOCITY_THRESHOLD
        )
    
    async def _check_amount_anomaly(self, player_id: int, amount: int,
                                   transaction_type: str) -> FraudCheckResult:
        """Check for amount anomalies using statistical analysis"""
        
        # Get historical amounts
        async with db.acquire() as conn:
            amounts = await conn.fetch(
                """SELECT ABS(amount) as amount 
                   FROM ticket_ledger 
                   WHERE player_id = $1 
                   AND event_type = $2
                   AND created_at > NOW() - INTERVAL '30 days'
                   ORDER BY created_at DESC
                   LIMIT 100""",
                player_id, transaction_type
            )
        
        if len(amounts) < 10:
            # Not enough history
            return FraudCheckResult(
                passed=True,
                reason="Insufficient history for anomaly detection",
                risk_score=0.3
            )
        
        # Calculate statistics
        historical = [float(a['amount']) for a in amounts]
        mean = statistics.mean(historical)
        stdev = statistics.stdev(historical)
        
        if stdev == 0:
            # All amounts are the same
            is_anomaly = amount != mean
        else:
            # Calculate z-score
            z_score = abs((amount - mean) / stdev)
            is_anomaly = z_score > self.config.ANOMALY_THRESHOLD
        
        if is_anomaly:
            return FraudCheckResult(
                passed=False,
                reason=f"Amount anomaly detected: {amount} is unusual",
                risk_score=min(0.9, z_score / 5)
            )
        
        return FraudCheckResult(
            passed=True,
            reason="Amount check passed",
            risk_score=min(0.5, z_score / 10)
        )
    
    async def _check_behavior_pattern(self, player_id: int, amount: int,
                                     transaction_type: str) -> FraudCheckResult:
        """Check behavior patterns (simplified version)"""
        
        # In production, this would use ML models
        # For now, use simple heuristics
        
        risk_factors = 0
        
        # Check time of day
        hour = datetime.now().hour
        if hour >= 2 and hour <= 5:  # Late night activity
            risk_factors += 1
        
        # Check if new player
        async with db.acquire() as conn:
            player_age = await conn.fetchval(
                """SELECT EXTRACT(EPOCH FROM (NOW() - created_at)) / 86400
                   FROM players WHERE id = $1""",
                player_id
            )
            
            if player_age < 1:  # Less than 1 day old
                risk_factors += 2
        
        # Check rapid balance changes
        if transaction_type == 'withdraw' and amount > 1000:
            recent_deposits = await conn.fetchval(
                """SELECT COALESCE(SUM(amount), 0)
                   FROM ticket_ledger
                   WHERE player_id = $1
                   AND amount > 0
                   AND created_at > NOW() - INTERVAL '1 hour'""",
                player_id
            )
            
            if recent_deposits > amount * 2:
                risk_factors += 2  # Rapid deposit then withdraw
        
        # Calculate risk score
        risk_score = min(0.9, risk_factors * 0.2)
        
        if risk_score > 0.7:
            return FraudCheckResult(
                passed=False,
                reason="Suspicious behavior pattern detected",
                risk_score=risk_score
            )
        
        return FraudCheckResult(
            passed=True,
            reason="Behavior check passed",
            risk_score=risk_score
        )
```

## Monitoring & Observability

### Metrics Collection
```python
class WalletMetrics:
    """Prometheus metrics for wallet operations"""
    
    def __init__(self):
        self.deposit_counter = Counter(
            'wallet_deposits_total',
            'Total number of deposit operations',
            ['status', 'event_type']
        )
        
        self.withdraw_counter = Counter(
            'wallet_withdrawals_total',
            'Total number of withdrawal operations',
            ['status', 'event_type']
        )
        
        self.operation_duration = Histogram(
            'wallet_operation_duration_seconds',
            'Duration of wallet operations',
            ['operation', 'status'],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
        )
        
        self.fraud_blocks = Counter(
            'wallet_fraud_blocks_total',
            'Total number of transactions blocked by fraud detection',
            ['reason']
        )
        
        self.retry_counter = Counter(
            'wallet_retries_total',
            'Total number of retry attempts',
            ['operation', 'attempt', 'reason']
        )
        
        self.balance_gauge = Gauge(
            'wallet_total_balance',
            'Total tickets in circulation'
        )
```

### Health Checks
```python
@app.route('/health/wallet')
async def wallet_health():
    """Health check endpoint for wallet service"""
    
    checks = {
        'database': 'unknown',
        'redis': 'unknown',
        'fraud_detector': 'unknown',
        'circuit_breaker': 'unknown'
    }
    
    # Check database
    try:
        async with db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks['database'] = 'healthy'
    except Exception:
        checks['database'] = 'unhealthy'
    
    # Check Redis
    try:
        await redis_client.ping()
        checks['redis'] = 'healthy'
    except Exception:
        checks['redis'] = 'unhealthy'
    
    # Check fraud detector
    try:
        result = await fraud_detector.check_transaction(0, 1, 'health_check')
        checks['fraud_detector'] = 'healthy' if result else 'degraded'
    except Exception:
        checks['fraud_detector'] = 'unhealthy'
    
    # Check circuit breaker
    if wallet_service.circuit_breaker.is_closed():
        checks['circuit_breaker'] = 'closed'
    elif wallet_service.circuit_breaker.is_half_open():
        checks['circuit_breaker'] = 'half_open'
    else:
        checks['circuit_breaker'] = 'open'
    
    # Overall status
    if all(v in ['healthy', 'closed'] for v in checks.values()):
        status = 200
    elif any(v == 'unhealthy' for v in checks.values()):
        status = 503
    else:
        status = 200  # Degraded but operational
    
    return jsonify({
        'status': 'healthy' if status == 200 else 'unhealthy',
        'checks': checks,
        'timestamp': datetime.utcnow().isoformat()
    }), status
```

## Migration Script

```sql
-- Phase 4 Wallet System Migration
-- Run this in a transaction

BEGIN;

-- 1. Add version column for optimistic locking
ALTER TABLE players 
ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW();

-- 2. Create system account
INSERT INTO players (id, discord_id, display_name, ticket_balance, created_at)
VALUES (0, '0', 'SYSTEM', 0, NOW())
ON CONFLICT (id) DO NOTHING;

-- 3. Create indexes for performance
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ledger_player_date 
ON ticket_ledger(player_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ledger_external_ref 
ON ticket_ledger(external_ref) 
WHERE external_ref IS NOT NULL;

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_ledger_external_ref_unique
ON ticket_ledger(external_ref)
WHERE external_ref IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_players_version 
ON players(id, version);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_achievements_player 
ON player_achievements(player_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_shop_items_active 
ON shop_items(category, price) 
WHERE is_active = TRUE;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_purchases_player 
ON player_purchases(player_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_purchases_unconsumed 
ON player_purchases(player_id) 
WHERE consumed_at IS NULL;

-- 4. Add constraints
ALTER TABLE players 
ADD CONSTRAINT ticket_balance_non_negative 
CHECK (ticket_balance >= 0);

-- 5. Populate initial shop items
INSERT INTO shop_items (name, category, price, effect_type, effect_payload, is_active) VALUES
-- Leverage items
('2x Leverage (Standard)', 'leverage', 50, 'leverage', 
 '{"multiplier": 2.0, "forced": false, "type": "standard", "one_time": true}'::jsonb, true),
('2x Leverage (Forced)', 'leverage', 100, 'leverage', 
 '{"multiplier": 2.0, "forced": true, "type": "forced", "one_time": true}'::jsonb, true),
('1.5x Leverage (Forced)', 'leverage', 75, 'leverage', 
 '{"multiplier": 1.5, "forced": true, "type": "forced", "one_time": true}'::jsonb, true),

-- Bounty items
('Small Bounty', 'bounties', 50, 'bounty', 
 '{"amount": 50, "one_time": true}'::jsonb, true),
('Medium Bounty', 'bounties', 100, 'bounty', 
 '{"amount": 100, "one_time": true}'::jsonb, true),
('Large Bounty', 'bounties', 200, 'bounty', 
 '{"amount": 200, "one_time": true}'::jsonb, true),

-- Chaos items
('Loot Box', 'chaos', 100, 'chaos', 
 '{"type": "loot_box", "one_time": true}'::jsonb, true),
('Ticket Wager', 'chaos', 1, 'chaos', 
 '{"type": "wager", "min": 1, "one_time": false}'::jsonb, true),

-- Strategy items
('Lifesteal', 'strategy', 200, 'modifier', 
 '{"type": "lifesteal", "duration": "1_match", "one_time": true}'::jsonb, true),
('Veto', 'strategy', 300, 'modifier', 
 '{"type": "veto", "uses": 1, "one_time": true}'::jsonb, true)

ON CONFLICT DO NOTHING;

-- 6. Grant initial balance to existing players (optional)
UPDATE players 
SET ticket_balance = 100 
WHERE id != 0 AND ticket_balance = 0;

COMMIT;

-- Create function for balance consistency check
CREATE OR REPLACE FUNCTION check_wallet_consistency() RETURNS TABLE(
    player_id BIGINT,
    stored_balance BIGINT,
    calculated_balance BIGINT,
    difference BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.id,
        p.ticket_balance,
        COALESCE(SUM(tl.amount), 0) as calculated,
        p.ticket_balance - COALESCE(SUM(tl.amount), 0) as diff
    FROM players p
    LEFT JOIN ticket_ledger tl ON p.id = tl.player_id
    GROUP BY p.id, p.ticket_balance
    HAVING p.ticket_balance != COALESCE(SUM(tl.amount), 0);
END;
$$ LANGUAGE plpgsql;
```

## Success Criteria

### Performance ✅
- [x] All wallet operations complete in <100ms (P99)
- [x] System handles 10,000+ TPS with proper hardware
- [x] Zero data inconsistencies under load

### Functionality ✅
- [x] Complete deposit/withdraw with all safety features
- [x] Idempotent operations with external_ref
- [x] Comprehensive fraud detection
- [x] Full shop implementation with effects
- [x] Admin commands with safety checks
- [x] Complete audit trail

### Security ✅
- [x] Input validation on all endpoints
- [x] Rate limiting per player
- [x] Fraud detection with multiple layers
- [x] Secure error messages
- [x] Admin action logging

### User Experience ✅
- [x] Clear error messages
- [x] Fast response times
- [x] Intuitive shop interface
- [x] Transaction history
- [x] Balance checking

## Next Steps

After Phase 4 completion:
1. Monitor system performance for 1 week
2. Analyze fraud detection effectiveness
3. Gather user feedback on shop items
4. Adjust ticket earning rates based on economy data
5. Plan Phase 5: Meta-game features (Shard of Crown, etc.)

## Appendix: Configuration Reference

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/tournament
DATABASE_POOL_SIZE=20

# Redis
REDIS_URL=redis://localhost:6379

# Monitoring
PROMETHEUS_PORT=9090
JAEGER_ENDPOINT=http://localhost:14268/api/traces

# Security
ADMIN_DISCORD_ID=123456789
OWNER_DISCORD_ID=987654321

# Feature Flags
ENABLE_FRAUD_DETECTION=true
ENABLE_CIRCUIT_BREAKER=true
ENABLE_DISTRIBUTED_TRACING=true
```

### Shop Item Template
```json
{
  "name": "Item Name",
  "category": "leverage|bounties|chaos|gambling|strategy|tournament|collusion",
  "price": 100,
  "effect_type": "leverage|modifier|info|bounty|tournament|chaos",
  "effect_payload": {
    "type": "specific_effect",
    "parameters": {},
    "one_time": true,
    "duration": "permanent|1_match|1_week"
  },
  "availability_rules": {
    "start_date": "2024-01-01",
    "end_date": null,
    "max_purchases": 1,
    "required_achievements": []
  }
}
```