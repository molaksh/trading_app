"""
Trade Intent Guard - PDT-safe behavior layer.

Prevents accidental day trading, strategy drift, and regulatory violations
for all accounts, with special rules for margin accounts < $25k.

PHILOSOPHY:
- Behavioral PDT (swing trade intent) applies to ALL accounts
- Regulatory PDT (5-day rule) applies to MARGIN < $25k only
- Risk-reducing exits (STOP_LOSS, RISK_MANAGER) ALWAYS allowed
- All blocks return structured reasons for auditability

PHASE: Future-proofing refactor
- Hold period logic delegated to HoldPolicy (mode-specific)
- PDT logic remains in guard (regulatory, not mode-specific)
- SwingHoldPolicy: MIN_HOLD=2, MAX_HOLD=20, no same-day exits
- DayTradeHoldPolicy: MIN_HOLD=0, MAX_HOLD=1, same-day exits allowed (NOT IMPLEMENTED)
"""

import logging
from enum import Enum
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Tuple, Optional, Dict, List
from policies.base import HoldPolicy

logger = logging.getLogger(__name__)


class ExitReason(Enum):
    """Exit signal classification."""
    STOP_LOSS = "stop_loss"                 # Risk-reducing, always allowed
    RISK_MANAGER = "risk_manager"           # Risk-reducing, always allowed
    TIME_EXPIRY = "time_expiry"             # Max hold reached
    STRATEGY_SIGNAL = "strategy_signal"     # Profit target, trend break, etc.
    MANUAL_OVERRIDE = "manual_override"     # Manual, normally blocked


class BlockReason(Enum):
    """Structured reasons for exit blocking."""
    # Behavioral PDT
    SAME_DAY_DISCRETIONARY = "same_day_discretionary"  # Day N entry, day N exit (non-risk)
    MIN_HOLD_NOT_MET = "min_hold_not_met"              # < 2 days for small accounts
    
    # Regulatory PDT (margin < $25k)
    PDT_LIMIT_REACHED = "pdt_limit_reached"            # 3+ day trades in 5 days
    PDT_LIMIT_AT_RISK = "pdt_limit_at_risk"            # Would trigger PDT (2 day trades, would be 3rd)
    
    # Account type
    CASH_ACCOUNT_SAME_DAY = "cash_account_same_day"    # Cash accounts no PDT but behavioral rule
    
    # Override disabled
    MANUAL_OVERRIDE_DISABLED = "manual_override_disabled"
    
    # Other
    MAX_HOLD_EXCEEDED = "max_hold_exceeded"             # Force exit required
    ALLOWED = "allowed"                                 # No block


@dataclass
class Trade:
    """Trade record for intent guard evaluation."""
    symbol: str
    entry_date: date
    entry_price: float
    quantity: int
    confidence: int
    

@dataclass
class AccountContext:
    """Account state for PDT evaluation."""
    account_equity: float
    account_type: str  # "CASH" or "MARGIN"
    day_trade_count_5d: int  # Rolling 5-day count from broker
    

@dataclass
class ExitDecision:
    """Structured exit decision with reasoning."""
    allowed: bool
    reason: str  # BlockReason enum value
    block_reason: Optional[str] = None  # Human-readable if blocked
    day_trade_count_5d: int = 0
    account_equity: float = 0.0
    account_type: str = ""
    holding_days: int = 0


class TradeIntentGuard:
    """
    Behavioral and regulatory PDT guard for swing trading.
    
    Rules are applied in priority order:
    1. Risk-reducing exits (STOP_LOSS, RISK_MANAGER) ALWAYS allowed
    2. Hold period validation delegated to HoldPolicy
    3. Regulatory PDT soft/hard limits for margin < $25k
    
    PHASE: Future-proofing refactor
    - Hold period logic delegated to HoldPolicy (mode-specific)
    - Swing mode uses SwingHoldPolicy (2-20 days, no same-day exits)
    - Day trade mode will use DayTradeHoldPolicy (0-1 days, same-day allowed)
    - Guard focuses on regulatory PDT only
    """
    
    # Configuration (PDT-specific, not hold-period related)
    MIN_EQUITY_THRESHOLD = 25000.0          # Account size threshold for PDT rules
    PDT_SOFT_LIMIT = 2                      # Warn at 2 day trades
    PDT_HARD_LIMIT = 3                      # Block at 3 day trades (regulatory)
    PDT_WINDOW_DAYS = 5                     # Rolling window for day trade count
    ALLOW_MANUAL_OVERRIDE = False           # Disable manual overrides by default
    
    def __init__(self, hold_policy: HoldPolicy, allow_manual_override: bool = False):
        """
        Initialize guard with mode-specific hold policy.
        
        Args:
            hold_policy: HoldPolicy implementation (SwingHoldPolicy, DayTradeHoldPolicy, etc.)
            allow_manual_override: Enable manual overrides (normally disabled)
        """
        self.hold_policy = hold_policy
        self.ALLOW_MANUAL_OVERRIDE = allow_manual_override
        
        logger.info("TradeIntentGuard initialized")
        logger.info(f"  Hold Policy: {hold_policy.get_name()}")
        logger.info(f"  Min hold days: {hold_policy.min_hold_days()}")
        logger.info(f"  Max hold days: {hold_policy.max_hold_days()}")
        logger.info(f"  Same-day exits allowed: {hold_policy.allows_same_day_exit()}")
        logger.info(f"  PDT soft limit: {self.PDT_SOFT_LIMIT}")
        logger.info(f"  PDT hard limit: {self.PDT_HARD_LIMIT}")
        logger.info(f"  Manual override: {'ENABLED' if allow_manual_override else 'DISABLED'}")

    def can_exit_trade(
        self,
        trade: Trade,
        exit_date: date,
        exit_reason: ExitReason,
        account_context: AccountContext,
    ) -> ExitDecision:
        """
        Determine if a trade can be exited.
        
        LOGIC:
        1. Calculate holding days
        2. Check if max hold exceeded → FORCE EXIT (delegated to HoldPolicy)
        3. Check if risk-reducing → ALLOW (bypasses all rules)
        4. Validate hold period (delegated to HoldPolicy)
        5. Check regulatory PDT limits (margin < $25k) → BLOCK if violated
        6. Check manual override status → ALLOW/BLOCK
        
        Args:
            trade: Trade record
            exit_date: Date of exit attempt
            exit_reason: Classified exit reason
            account_context: Account state
        
        Returns:
            ExitDecision with allow/block determination and reasons
        """
        holding_days = (exit_date - trade.entry_date).days
        
        logger.info("=" * 80)
        logger.info("TRADE INTENT GUARD EVALUATION")
        logger.info("=" * 80)
        logger.info(f"Symbol: {trade.symbol}")
        logger.info(f"Entry: {trade.entry_date}, Exit: {exit_date}")
        logger.info(f"Holding days: {holding_days}")
        logger.info(f"Exit reason: {exit_reason.value}")
        logger.info(f"Account: {account_context.account_type} (${account_context.account_equity:,.2f})")
        logger.info(f"Day trades (5d): {account_context.day_trade_count_5d}")
        logger.info(f"Hold Policy: {self.hold_policy.get_name()}")
        
        # ====================================================================
        # RULE 1: Force exit if max hold exceeded (HoldPolicy)
        # ====================================================================
        if self.hold_policy.is_forced_exit_required(holding_days):
            decision = ExitDecision(
                allowed=True,
                reason=BlockReason.MAX_HOLD_EXCEEDED.value,
                block_reason=None,
                holding_days=holding_days,
                account_equity=account_context.account_equity,
                account_type=account_context.account_type,
                day_trade_count_5d=account_context.day_trade_count_5d,
            )
            logger.info(f"✅ FORCED EXIT: Max hold period exceeded ({holding_days} > {self.hold_policy.max_hold_days()})")
            return decision
        
        # ====================================================================
        # RULE 2: Risk-reducing exits ALWAYS allowed (override all rules)
        # ====================================================================
        is_risk_reducing = exit_reason in [ExitReason.STOP_LOSS, ExitReason.RISK_MANAGER]
        if is_risk_reducing:
            decision = ExitDecision(
                allowed=True,
                reason=BlockReason.ALLOWED.value,
                block_reason=None,
                holding_days=holding_days,
                account_equity=account_context.account_equity,
                account_type=account_context.account_type,
                day_trade_count_5d=account_context.day_trade_count_5d,
            )
            logger.info(f"✅ ALLOWED: Risk-reducing exit ({exit_reason.value})")
            return decision
        
        # ====================================================================
        # RULE 3: Validate hold period (delegated to HoldPolicy)
        # ====================================================================
        allowed, block_reason = self.hold_policy.validate_hold_period(holding_days, is_risk_reducing)
        if not allowed:
            decision = ExitDecision(
                allowed=False,
                reason=BlockReason.MIN_HOLD_NOT_MET.value if holding_days < self.hold_policy.min_hold_days() 
                       else BlockReason.SAME_DAY_DISCRETIONARY.value,
                block_reason=block_reason,
                holding_days=holding_days,
                account_equity=account_context.account_equity,
                account_type=account_context.account_type,
                day_trade_count_5d=account_context.day_trade_count_5d,
            )
            logger.warning(f"❌ BLOCKED: {block_reason}")
            return decision
        
        # ====================================================================
        # RULE 4: Regulatory PDT limits (MARGIN only, < $25k)
        # ====================================================================
        if (account_context.account_type == "MARGIN" and 
            account_context.account_equity < self.MIN_EQUITY_THRESHOLD):
            
            # Is this a day trade?
            if self._is_day_trade(trade, exit_date):
                
                # Hard limit: Already at or over limit?
                if account_context.day_trade_count_5d >= self.PDT_HARD_LIMIT:
                    decision = ExitDecision(
                        allowed=False,
                        reason=BlockReason.PDT_LIMIT_REACHED.value,
                        block_reason=f"PDT limit reached ({account_context.day_trade_count_5d}/{self.PDT_HARD_LIMIT})",
                        holding_days=holding_days,
                        account_equity=account_context.account_equity,
                        account_type=account_context.account_type,
                        day_trade_count_5d=account_context.day_trade_count_5d,
                    )
                    logger.warning(f"❌ BLOCKED: PDT hard limit reached ({account_context.day_trade_count_5d})")
                    return decision
                
                # Soft limit: Would this trade trigger the hard limit?
                if account_context.day_trade_count_5d == self.PDT_SOFT_LIMIT:
                    decision = ExitDecision(
                        allowed=False,
                        reason=BlockReason.PDT_LIMIT_AT_RISK.value,
                        block_reason=f"Would trigger PDT limit ({self.PDT_SOFT_LIMIT} → {self.PDT_SOFT_LIMIT + 1})",
                        holding_days=holding_days,
                        account_equity=account_context.account_equity,
                        account_type=account_context.account_type,
                        day_trade_count_5d=account_context.day_trade_count_5d,
                    )
                    logger.warning(f"❌ BLOCKED: Would trigger PDT limit")
                    return decision
        
        # ====================================================================
        # RULE 5: Manual override (normally disabled)
        # ====================================================================
        if exit_reason == ExitReason.MANUAL_OVERRIDE:
            if not self.ALLOW_MANUAL_OVERRIDE:
                decision = ExitDecision(
                    allowed=False,
                    reason=BlockReason.MANUAL_OVERRIDE_DISABLED.value,
                    block_reason="Manual overrides are disabled",
                    holding_days=holding_days,
                    account_equity=account_context.account_equity,
                    account_type=account_context.account_type,
                    day_trade_count_5d=account_context.day_trade_count_5d,
                )
                logger.warning(f"❌ BLOCKED: Manual override disabled")
                return decision
        
        # ====================================================================
        # DEFAULT: ALLOW (all checks passed)
        # ====================================================================
        decision = ExitDecision(
            allowed=True,
            reason=BlockReason.ALLOWED.value,
            block_reason=None,
            holding_days=holding_days,
            account_equity=account_context.account_equity,
            account_type=account_context.account_type,
            day_trade_count_5d=account_context.day_trade_count_5d,
        )
        logger.info(f"✅ ALLOWED: Exit approved")
        return decision

    def _is_day_trade(self, trade: Trade, exit_date: date) -> bool:
        """
        Determine if trade is a day trade (opened and closed same day).
        
        Args:
            trade: Trade record
            exit_date: Date of exit
        
        Returns:
            True if opened and closed same day
        """
        is_dt = trade.entry_date == exit_date
        logger.debug(f"Is day trade: {is_dt} (entry={trade.entry_date}, exit={exit_date})")
        return is_dt

    def log_exit_decision(self, decision: ExitDecision, trade: Trade, exit_reason: ExitReason) -> None:
        """
        Log exit decision for audit trail.
        
        Args:
            decision: ExitDecision result
            trade: Trade record
            exit_reason: Exit reason classification
        """
        logger.info("\n" + "=" * 80)
        logger.info("EXIT DECISION LOG")
        logger.info("=" * 80)
        logger.info(f"Symbol: {trade.symbol}")
        logger.info(f"Allowed: {decision.allowed}")
        logger.info(f"Reason: {decision.reason}")
        if decision.block_reason:
            logger.warning(f"Block Reason: {decision.block_reason}")
        logger.info(f"Holding Days: {decision.holding_days}")
        logger.info(f"Account Type: {decision.account_type}")
        logger.info(f"Account Equity: ${decision.account_equity:,.2f}")
        logger.info(f"Day Trade Count (5d): {decision.day_trade_count_5d}")
        logger.info(f"Exit Reason: {exit_reason.value}")
        logger.info("=" * 80 + "\n")


# =============================================================================
# CONVENIENCE FACTORY FUNCTIONS
# =============================================================================

def create_guard(hold_policy: HoldPolicy, allow_manual_override: bool = False) -> TradeIntentGuard:
    """
    Create a TradeIntentGuard with hold policy.
    
    Args:
        hold_policy: HoldPolicy implementation (SwingHoldPolicy, DayTradeHoldPolicy, etc.)
        allow_manual_override: Enable manual overrides (normally disabled)
    
    Returns:
        Configured TradeIntentGuard
    """
    return TradeIntentGuard(hold_policy=hold_policy, allow_manual_override=allow_manual_override)


def create_trade(
    symbol: str,
    entry_date: date,
    entry_price: float,
    quantity: int,
    confidence: int = 3,
) -> Trade:
    """Factory for Trade creation."""
    return Trade(
        symbol=symbol,
        entry_date=entry_date,
        entry_price=entry_price,
        quantity=quantity,
        confidence=confidence,
    )


def create_account_context(
    account_equity: float,
    account_type: str = "MARGIN",
    day_trade_count_5d: int = 0,
) -> AccountContext:
    """Factory for AccountContext creation."""
    if account_type not in ["CASH", "MARGIN"]:
        raise ValueError(f"Invalid account_type: {account_type}")
    
    return AccountContext(
        account_equity=account_equity,
        account_type=account_type,
        day_trade_count_5d=day_trade_count_5d,
    )
