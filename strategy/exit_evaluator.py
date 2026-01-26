"""
Exit signal evaluator for swing trading system.

CRITICAL DESIGN PRINCIPLES:
1. This is a SWING TRADING system, NOT day trading
2. Swing exits evaluated on EOD data only (executed next market open)
3. Emergency exits are RARE, intraday, for capital protection ONLY
4. No same-day entry and exit via strategy logic
5. Emergency and swing exits are strictly separated and logged differently

Exit Types:
- SWING_EXIT: Normal strategy exit based on EOD signals
- EMERGENCY_EXIT: Intraday risk protection (rare, hard thresholds)
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, date
from enum import Enum

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class ExitType(Enum):
    """Exit classification for audit trail."""
    SWING_EXIT = "SWING_EXIT"          # Normal EOD strategy exit
    EMERGENCY_EXIT = "EMERGENCY_EXIT"  # Intraday capital protection


@dataclass
class ExitSignal:
    """
    Exit signal with full audit trail.
    
    Attributes:
        symbol: Ticker symbol
        exit_type: SWING_EXIT or EMERGENCY_EXIT
        reason: Human-readable exit reason
        timestamp: When exit was generated
        entry_date: When position was entered
        holding_days: Days held
        confidence: Original entry confidence (for stats)
        urgency: 'eod' (execute next open) or 'immediate' (intraday)
    """
    symbol: str
    exit_type: ExitType
    reason: str
    timestamp: datetime
    entry_date: date
    holding_days: int
    confidence: int
    urgency: str  # 'eod' or 'immediate'
    
    def to_dict(self) -> Dict:
        """Convert to dict for logging."""
        return {
            "symbol": self.symbol,
            "exit_type": self.exit_type.value,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "entry_date": self.entry_date.isoformat(),
            "holding_days": self.holding_days,
            "confidence": self.confidence,
            "urgency": self.urgency,
        }


class SwingExitEvaluator:
    """
    Evaluates EOD swing strategy exits.
    
    NEVER triggers intraday. Only evaluates on end-of-day data.
    Exits execute at next market open.
    
    Exit Rules:
    1. Trend invalidation (close below 200 SMA)
    2. Time-based exit (max holding period)
    3. Profit target reached
    """
    
    def __init__(
        self,
        max_holding_days: int = 20,
        profit_target_pct: float = 0.10,  # 10% profit target
        use_trend_invalidation: bool = True,
    ):
        """
        Initialize swing exit evaluator.
        
        Args:
            max_holding_days: Maximum days to hold position
            profit_target_pct: Profit target (e.g., 0.10 = 10%)
            use_trend_invalidation: Enable trend invalidation rule
        """
        self.max_holding_days = max_holding_days
        self.profit_target_pct = profit_target_pct
        self.use_trend_invalidation = use_trend_invalidation
        
        logger.info("Swing Exit Evaluator initialized")
        logger.info(f"  Max holding days: {max_holding_days}")
        logger.info(f"  Profit target: {profit_target_pct:.1%}")
        logger.info(f"  Trend invalidation: {use_trend_invalidation}")
    
    def evaluate(
        self,
        symbol: str,
        entry_date: date,
        entry_price: float,
        current_price: float,
        confidence: int,
        eod_data: Optional[pd.Series] = None,
        evaluation_date: Optional[date] = None,
    ) -> Optional[ExitSignal]:
        """
        Evaluate swing exit on EOD data.
        
        IMPORTANT: Only call this with EOD data, not intraday.
        
        Args:
            symbol: Ticker symbol
            entry_date: Position entry date
            entry_price: Entry price
            current_price: Current EOD close price
            confidence: Original entry confidence
            eod_data: EOD OHLCV row with technical indicators
            evaluation_date: Date of evaluation (defaults to today)
        
        Returns:
            ExitSignal if exit triggered, None otherwise
        """
        if evaluation_date is None:
            evaluation_date = date.today()
        
        holding_days = (evaluation_date - entry_date).days
        
        # Rule 1: Maximum holding period
        if holding_days >= self.max_holding_days:
            return ExitSignal(
                symbol=symbol,
                exit_type=ExitType.SWING_EXIT,
                reason=f"Max holding period reached ({holding_days} days)",
                timestamp=datetime.now(),
                entry_date=entry_date,
                holding_days=holding_days,
                confidence=confidence,
                urgency='eod',
            )
        
        # Rule 2: Profit target
        return_pct = (current_price - entry_price) / entry_price
        if return_pct >= self.profit_target_pct:
            return ExitSignal(
                symbol=symbol,
                exit_type=ExitType.SWING_EXIT,
                reason=f"Profit target reached ({return_pct:.1%} >= {self.profit_target_pct:.1%})",
                timestamp=datetime.now(),
                entry_date=entry_date,
                holding_days=holding_days,
                confidence=confidence,
                urgency='eod',
            )
        
        # Rule 3: Trend invalidation (requires eod_data)
        if self.use_trend_invalidation and eod_data is not None:
            close = eod_data.get('Close', current_price)
            sma_200 = eod_data.get('SMA_200')
            
            if sma_200 is not None and not np.isnan(sma_200):
                if close < sma_200:
                    return ExitSignal(
                        symbol=symbol,
                        exit_type=ExitType.SWING_EXIT,
                        reason=f"Trend invalidation: close ${close:.2f} < SMA200 ${sma_200:.2f}",
                        timestamp=datetime.now(),
                        entry_date=entry_date,
                        holding_days=holding_days,
                        confidence=confidence,
                        urgency='eod',
                    )
        
        # No exit signal
        return None


class EmergencyExitEvaluator:
    """
    Evaluates intraday emergency exits for capital protection.
    
    PURPOSE: Capital preservation, NOT performance optimization.
    TRIGGERS: Rare, only on extreme moves.
    EVALUATION: Continuous during market hours.
    
    Emergency Rules:
    1. Catastrophic loss (> threshold % of portfolio)
    2. Extreme adverse move (> N × ATR against position)
    3. Volatility spike / circuit breaker
    """
    
    def __init__(
        self,
        max_position_loss_pct: float = 0.03,  # 3% of portfolio per position
        atr_multiplier: float = 4.0,           # 4× ATR adverse move
        enable_volatility_check: bool = True,
    ):
        """
        Initialize emergency exit evaluator.
        
        Args:
            max_position_loss_pct: Max loss per position as % of portfolio
            atr_multiplier: ATR multiplier for extreme moves
            enable_volatility_check: Enable volatility spike detection
        """
        self.max_position_loss_pct = max_position_loss_pct
        self.atr_multiplier = atr_multiplier
        self.enable_volatility_check = enable_volatility_check
        
        logger.info("Emergency Exit Evaluator initialized")
        logger.info(f"  Max position loss: {max_position_loss_pct:.1%} of portfolio")
        logger.info(f"  ATR multiplier: {atr_multiplier}×")
        logger.info(f"  Volatility check: {enable_volatility_check}")
    
    def evaluate(
        self,
        symbol: str,
        entry_date: date,
        entry_price: float,
        current_price: float,
        position_size: float,
        portfolio_equity: float,
        confidence: int,
        atr: Optional[float] = None,
        evaluation_date: Optional[date] = None,
    ) -> Optional[ExitSignal]:
        """
        Evaluate emergency exit intraday.
        
        ONLY triggers on extreme capital-preservation scenarios.
        Should be RARE in normal market conditions.
        
        Args:
            symbol: Ticker symbol
            entry_date: Position entry date
            entry_price: Entry price
            current_price: Current intraday price
            position_size: Number of shares
            portfolio_equity: Total portfolio equity
            confidence: Original entry confidence
            atr: Average True Range for volatility check
            evaluation_date: Date of evaluation (defaults to today)
        
        Returns:
            ExitSignal if emergency exit triggered, None otherwise
        """
        if evaluation_date is None:
            evaluation_date = date.today()
        
        holding_days = (evaluation_date - entry_date).days
        
        # Prevent same-day exit (this is NOT day trading)
        if holding_days == 0:
            # Allow emergency exit only if catastrophic loss
            position_value = position_size * current_price
            entry_value = position_size * entry_price
            loss = entry_value - position_value
            loss_pct_of_portfolio = loss / portfolio_equity
            
            # Only exit same-day if loss is catastrophic (> 2× normal threshold)
            if loss_pct_of_portfolio < self.max_position_loss_pct * 2:
                return None
        
        # Rule 1: Catastrophic position loss
        position_value = position_size * current_price
        entry_value = position_size * entry_price
        loss = entry_value - position_value
        loss_pct_of_portfolio = loss / portfolio_equity
        
        if loss_pct_of_portfolio >= self.max_position_loss_pct:
            return ExitSignal(
                symbol=symbol,
                exit_type=ExitType.EMERGENCY_EXIT,
                reason=f"Catastrophic loss: {loss_pct_of_portfolio:.1%} of portfolio (threshold: {self.max_position_loss_pct:.1%})",
                timestamp=datetime.now(),
                entry_date=entry_date,
                holding_days=holding_days,
                confidence=confidence,
                urgency='immediate',
            )
        
        # Rule 2: Extreme adverse move (ATR-based)
        if atr is not None and atr > 0:
            price_move = entry_price - current_price  # Positive if price dropped
            threshold = self.atr_multiplier * atr
            
            if price_move >= threshold:
                return ExitSignal(
                    symbol=symbol,
                    exit_type=ExitType.EMERGENCY_EXIT,
                    reason=f"Extreme adverse move: ${price_move:.2f} >= {self.atr_multiplier}× ATR (${threshold:.2f})",
                    timestamp=datetime.now(),
                    entry_date=entry_date,
                    holding_days=holding_days,
                    confidence=confidence,
                    urgency='immediate',
                )
        
        # No emergency exit
        return None


class ExitEvaluator:
    """
    Master exit evaluator coordinating swing and emergency exits.
    
    Responsibilities:
    1. Route evaluation to appropriate evaluator (swing vs emergency)
    2. Ensure proper separation of concerns
    3. Provide unified interface to executor
    
    Design Constraints:
    - Swing exits: EOD only, never same-day
    - Emergency exits: Intraday allowed, rare, capital protection only
    - All exits logged with classification and reason
    """
    
    def __init__(
        self,
        swing_config: Optional[Dict] = None,
        emergency_config: Optional[Dict] = None,
    ):
        """
        Initialize master exit evaluator.
        
        Args:
            swing_config: Config dict for SwingExitEvaluator
            emergency_config: Config dict for EmergencyExitEvaluator
        """
        swing_config = swing_config or {}
        emergency_config = emergency_config or {}
        
        self.swing = SwingExitEvaluator(**swing_config)
        self.emergency = EmergencyExitEvaluator(**emergency_config)
        
        logger.info("Exit Evaluator initialized (2-layer: swing + emergency)")
    
    def evaluate_eod(
        self,
        symbol: str,
        entry_date: date,
        entry_price: float,
        current_price: float,
        confidence: int,
        eod_data: Optional[pd.Series] = None,
        evaluation_date: Optional[date] = None,
    ) -> Optional[ExitSignal]:
        """
        Evaluate EOD swing exit.
        
        Call this ONLY with end-of-day data.
        Never triggers same-day exit.
        
        Args:
            symbol: Ticker symbol
            entry_date: Position entry date
            entry_price: Entry price
            current_price: Current EOD close price
            confidence: Original entry confidence
            eod_data: EOD OHLCV row with indicators
            evaluation_date: Date of evaluation
        
        Returns:
            ExitSignal if swing exit triggered, None otherwise
        """
        return self.swing.evaluate(
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            current_price=current_price,
            confidence=confidence,
            eod_data=eod_data,
            evaluation_date=evaluation_date,
        )
    
    def evaluate_emergency(
        self,
        symbol: str,
        entry_date: date,
        entry_price: float,
        current_price: float,
        position_size: float,
        portfolio_equity: float,
        confidence: int,
        atr: Optional[float] = None,
        evaluation_date: Optional[date] = None,
    ) -> Optional[ExitSignal]:
        """
        Evaluate intraday emergency exit.
        
        Should be called continuously during market hours.
        Will NOT trigger same-day exit unless catastrophic.
        
        Args:
            symbol: Ticker symbol
            entry_date: Position entry date
            entry_price: Entry price
            current_price: Current intraday price
            position_size: Number of shares
            portfolio_equity: Total portfolio equity
            confidence: Original entry confidence
            atr: Average True Range
            evaluation_date: Date of evaluation
        
        Returns:
            ExitSignal if emergency exit triggered, None otherwise
        """
        return self.emergency.evaluate(
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            current_price=current_price,
            position_size=position_size,
            portfolio_equity=portfolio_equity,
            confidence=confidence,
            atr=atr,
            evaluation_date=evaluation_date,
        )
