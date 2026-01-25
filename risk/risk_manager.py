"""
Risk management engine for trade approval and position sizing.

Implements strict, transparent controls:
- Per-trade risk limits
- Per-symbol exposure limits
- Portfolio heat limits
- Daily loss limits
- Consecutive loss limits
- Confidence-based position sizing
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from config.settings import (
    RISK_PER_TRADE,
    MAX_RISK_PER_SYMBOL,
    MAX_PORTFOLIO_HEAT,
    MAX_TRADES_PER_DAY,
    MAX_CONSECUTIVE_LOSSES,
    DAILY_LOSS_LIMIT,
    CONFIDENCE_RISK_MULTIPLIER,
)
from risk.portfolio_state import PortfolioState

logger = logging.getLogger(__name__)


@dataclass
class TradeDecision:
    """Result of trade risk assessment."""
    approved: bool
    position_size: float
    risk_amount: float
    reason: str
    
    def __repr__(self) -> str:
        status = "✓ APPROVED" if self.approved else "✗ REJECTED"
        return f"{status}: {self.reason}"


class RiskManager:
    """
    Centralized risk management for trade approval.
    
    Evaluates trades against:
    - Individual trade risk limits
    - Per-symbol exposure limits
    - Portfolio heat limits
    - Daily trade frequency limits
    - Daily loss limits
    - Consecutive loss limits
    - Confidence-based position sizing
    """
    
    def __init__(self, portfolio_state: PortfolioState):
        """
        Initialize risk manager.
        
        Args:
            portfolio_state: Current portfolio state tracker
        """
        self.portfolio = portfolio_state
        self.rejections: Dict[str, int] = {}  # Track rejection reasons
        self.approvals: int = 0
        
        logger.info("Risk Manager initialized")
        logger.info(f"  Per-trade risk: {RISK_PER_TRADE:.2%}")
        logger.info(f"  Per-symbol max exposure: {MAX_RISK_PER_SYMBOL:.2%}")
        logger.info(f"  Max portfolio heat: {MAX_PORTFOLIO_HEAT:.2%}")
        logger.info(f"  Max trades per day: {MAX_TRADES_PER_DAY}")
        logger.info(f"  Max consecutive losses: {MAX_CONSECUTIVE_LOSSES}")
        logger.info(f"  Daily loss limit: {DAILY_LOSS_LIMIT:.2%}")
    
    def evaluate_trade(
        self,
        symbol: str,
        entry_price: float,
        confidence: int,
        current_prices: Dict[str, float],
    ) -> TradeDecision:
        """
        Evaluate if trade can be executed under risk constraints.
        
        Args:
            symbol: Stock ticker
            entry_price: Proposed entry price
            confidence: Confidence score (1-5)
            current_prices: Current prices for portfolio heat calc
        
        Returns:
            TradeDecision with approval status and position size
        """
        
        # Check 1: Kill switch - consecutive losses
        if self.portfolio.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
            reason = (
                f"Consecutive loss limit reached "
                f"({self.portfolio.consecutive_losses}/{MAX_CONSECUTIVE_LOSSES})"
            )
            self._record_rejection("consecutive_losses", reason)
            return TradeDecision(False, 0.0, 0.0, reason)
        
        # Check 2: Kill switch - daily loss limit
        daily_loss_pct = self.portfolio.get_daily_loss_pct()
        if daily_loss_pct <= -DAILY_LOSS_LIMIT:
            reason = (
                f"Daily loss limit exceeded "
                f"({abs(daily_loss_pct):.2%} > {DAILY_LOSS_LIMIT:.2%})"
            )
            self._record_rejection("daily_loss_limit", reason)
            return TradeDecision(False, 0.0, 0.0, reason)
        
        # Check 3: Max trades per day
        if self.portfolio.daily_trades_opened >= MAX_TRADES_PER_DAY:
            reason = (
                f"Max trades per day reached "
                f"({self.portfolio.daily_trades_opened}/{MAX_TRADES_PER_DAY})"
            )
            self._record_rejection("max_trades_per_day", reason)
            return TradeDecision(False, 0.0, 0.0, reason)
        
        # Check 4: Calculate position size with confidence multiplier
        confidence_multiplier = self._get_confidence_multiplier(confidence)
        base_risk = RISK_PER_TRADE * confidence_multiplier
        risk_amount = self.portfolio.current_equity * base_risk
        
        # Position size: risk_amount / entry_price
        position_size = risk_amount / entry_price if entry_price > 0 else 0
        
        if position_size <= 0:
            reason = f"Invalid position size calculation (price={entry_price})"
            self._record_rejection("invalid_position", reason)
            return TradeDecision(False, 0.0, 0.0, reason)
        
        # Check 5: Per-symbol exposure limit
        current_symbol_value = (
            sum(
                pos.get_current_value()
                for pos in self.portfolio.open_positions.get(symbol, [])
            ) if symbol in self.portfolio.open_positions else 0.0
        )
        proposed_symbol_value = current_symbol_value + (position_size * entry_price)
        proposed_symbol_exposure = proposed_symbol_value / self.portfolio.current_equity
        
        if proposed_symbol_exposure > MAX_RISK_PER_SYMBOL:
            reason = (
                f"Per-symbol exposure limit exceeded "
                f"({proposed_symbol_exposure:.2%} > {MAX_RISK_PER_SYMBOL:.2%})"
            )
            self._record_rejection("per_symbol_exposure", reason)
            return TradeDecision(False, 0.0, 0.0, reason)
        
        # Check 6: Portfolio heat limit
        new_portfolio_heat = self._calculate_proposed_portfolio_heat(
            risk_amount, current_prices
        )
        
        if new_portfolio_heat > MAX_PORTFOLIO_HEAT:
            reason = (
                f"Portfolio heat limit exceeded "
                f"({new_portfolio_heat:.2%} > {MAX_PORTFOLIO_HEAT:.2%})"
            )
            self._record_rejection("portfolio_heat", reason)
            return TradeDecision(False, 0.0, 0.0, reason)
        
        # All checks passed - APPROVE
        self.approvals += 1
        reason = (
            f"APPROVED (Conf={confidence}, Risk=${risk_amount:.2f}, "
            f"Size={position_size:.0f}, Heat={new_portfolio_heat:.2%})"
        )
        
        logger.debug(f"Trade approved: {symbol} @ {entry_price:.2f} | {reason}")
        
        return TradeDecision(True, position_size, risk_amount, reason)
    
    def _get_confidence_multiplier(self, confidence: int) -> float:
        """
        Get position sizing multiplier based on confidence.
        
        Args:
            confidence: Confidence score (1-5)
        
        Returns:
            Multiplier for base risk
        """
        multiplier = CONFIDENCE_RISK_MULTIPLIER.get(confidence, 1.0)
        if confidence < 1 or confidence > 5:
            logger.warning(f"Invalid confidence level: {confidence}, using 1.0")
            multiplier = 1.0
        return multiplier
    
    def _calculate_proposed_portfolio_heat(
        self,
        new_risk_amount: float,
        current_prices: Dict[str, float],
    ) -> float:
        """
        Calculate portfolio heat including proposed trade.
        
        Args:
            new_risk_amount: Risk amount of new trade
            current_prices: Current prices for unrealized P&L
        
        Returns:
            Proposed portfolio heat as % of equity
        """
        current_heat = self.portfolio.get_portfolio_heat(current_prices)
        additional_heat = new_risk_amount / self.portfolio.current_equity
        return current_heat + additional_heat
    
    def _record_rejection(self, reason_key: str, reason_msg: str) -> None:
        """
        Record rejection for reporting.
        
        Args:
            reason_key: Short key for rejection reason
            reason_msg: Full rejection message
        """
        self.rejections[reason_key] = self.rejections.get(reason_key, 0) + 1
        logger.debug(f"Trade rejected: {reason_msg}")
    
    def get_summary(self) -> Dict:
        """
        Get risk manager summary statistics.
        
        Returns:
            Dict with approval/rejection stats
        """
        total_decisions = self.approvals + sum(self.rejections.values())
        approval_rate = self.approvals / total_decisions if total_decisions > 0 else 0
        
        return {
            'approvals': self.approvals,
            'rejections': sum(self.rejections.values()),
            'total_decisions': total_decisions,
            'approval_rate': approval_rate,
            'rejection_breakdown': self.rejections.copy(),
        }
    
    def log_summary(self) -> None:
        """Log risk manager summary."""
        summary = self.get_summary()
        
        logger.info("\nRisk Manager Summary:")
        logger.info(f"  Approvals: {summary['approvals']}")
        logger.info(f"  Rejections: {summary['rejections']}")
        logger.info(f"  Approval rate: {summary['approval_rate']:.1%}")
        
        if summary['rejection_breakdown']:
            logger.info(f"  Rejection breakdown:")
            for reason, count in summary['rejection_breakdown'].items():
                logger.info(f"    {reason}: {count}")


def create_risk_manager(initial_equity: float) -> RiskManager:
    """
    Factory function to create risk manager with portfolio state.
    
    Args:
        initial_equity: Starting account equity
    
    Returns:
        Configured RiskManager instance
    """
    portfolio_state = PortfolioState(initial_equity)
    return RiskManager(portfolio_state)
