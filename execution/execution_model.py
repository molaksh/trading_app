"""
Execution realism model (Phase G).

Simulates realistic execution with:
- Entry/exit price slippage
- Liquidity constraints
- Next-open entry timing
- Conservative fill assumptions

NOT USED FOR:
- Real-time execution
- Broker API integration
- Intraday trading
- Live fills

Used ONLY FOR:
- Realistic backtesting assumptions
- PnL adjustment for slippage costs
- Liquidity risk quantification
"""

import logging
from typing import Optional, Dict, Tuple

import pandas as pd
import numpy as np

from config.settings import (
    ENTRY_SLIPPAGE_BPS,
    EXIT_SLIPPAGE_BPS,
    MAX_POSITION_ADV_PCT,
    USE_NEXT_OPEN_ENTRY,
)

logger = logging.getLogger(__name__)


def apply_slippage(price: float, slippage_bps: int, direction: str = "entry") -> float:
    """
    Apply slippage to a price.
    
    Slippage is conservative: assumes we get worse prices due to market impact.
    
    Args:
        price: Reference price (typically open or close)
        slippage_bps: Slippage in basis points (100 bps = 1%)
        direction: "entry" (slippage against us on entry) or "exit"
    
    Returns:
        Price with slippage applied
    
    Example:
        apply_slippage(100.0, 5, "entry") -> 100.05 (worse entry price)
        apply_slippage(100.0, 5, "exit")  -> 99.95 (worse exit price)
    """
    slippage_pct = slippage_bps / 10000.0  # Convert bps to decimal
    
    if direction == "entry":
        # On entry: price moves against us (higher)
        return price * (1 + slippage_pct)
    elif direction == "exit":
        # On exit: price moves against us (lower)
        return price * (1 - slippage_pct)
    else:
        raise ValueError(f"direction must be 'entry' or 'exit', got {direction}")


def compute_entry_price(
    signal_date: pd.Timestamp,
    price_data: pd.DataFrame,
    use_next_open: bool = True,
) -> Optional[float]:
    """
    Compute realistic entry price.
    
    When backtesting: signals generated on day T (based on T-1 close).
    - If use_next_open=True: enter at day T+1 open (realistic, next day)
    - If use_next_open=False: enter at day T close (optimistic, same day)
    
    Args:
        signal_date: Date signal was generated
        price_data: DataFrame with OHLCV data, indexed by date
        use_next_open: If True, use next day's open; else use same day's close
    
    Returns:
        Entry price with slippage applied, or None if price unavailable
    """
    try:
        if use_next_open:
            # Get next trading day's open
            # Find signal_date in index
            if signal_date not in price_data.index:
                logger.warning(f"Signal date {signal_date} not in price data")
                return None
            
            # Get next trading day
            idx = price_data.index.get_loc(signal_date)
            if idx >= len(price_data) - 1:
                logger.warning(f"No next day data available after {signal_date}")
                return None
            
            next_open = price_data.iloc[idx + 1]["Open"]
        else:
            # Use same day's close (optimistic)
            if signal_date not in price_data.index:
                logger.warning(f"Signal date {signal_date} not in price data")
                return None
            
            next_open = price_data.loc[signal_date, "Close"]
        
        # Apply entry slippage
        entry_price = apply_slippage(next_open, ENTRY_SLIPPAGE_BPS, direction="entry")
        return entry_price
    
    except Exception as e:
        logger.warning(f"Error computing entry price: {e}")
        return None


def compute_exit_price(
    exit_date: pd.Timestamp,
    price_data: pd.DataFrame,
    use_next_open: bool = True,
) -> Optional[float]:
    """
    Compute realistic exit price.
    
    On exit day, we can sell at that day's prices.
    - If use_next_open=True: use open (market open exit)
    - If use_next_open=False: use close (end-of-day exit)
    
    Args:
        exit_date: Date to exit position
        price_data: DataFrame with OHLCV data, indexed by date
        use_next_open: If True, use open; else use close
    
    Returns:
        Exit price with slippage applied, or None if price unavailable
    """
    try:
        if exit_date not in price_data.index:
            logger.warning(f"Exit date {exit_date} not in price data")
            return None
        
        if use_next_open:
            exit_ref_price = price_data.loc[exit_date, "Open"]
        else:
            exit_ref_price = price_data.loc[exit_date, "Close"]
        
        # Apply exit slippage
        exit_price = apply_slippage(exit_ref_price, EXIT_SLIPPAGE_BPS, direction="exit")
        return exit_price
    
    except Exception as e:
        logger.warning(f"Error computing exit price: {e}")
        return None


def check_liquidity(
    position_notional: float,
    avg_daily_dollar_volume: float,
    max_adv_pct: float = MAX_POSITION_ADV_PCT,
) -> Tuple[bool, Optional[str]]:
    """
    Check if position size is within liquidity limits.
    
    Conservative check: reject if position would exceed X% of average daily volume.
    This prevents market impact and ensures the position is tradeable.
    
    Args:
        position_notional: Position value in dollars (shares * price)
        avg_daily_dollar_volume: Average daily dollar volume (close price)
        max_adv_pct: Max position as % of ADV (default 5%)
    
    Returns:
        Tuple of (passes_check, reason)
        - If passes_check=True: (True, None) - position OK
        - If passes_check=False: (False, reason_string) - position rejected
    
    Example:
        ADV = 10M dollars, max_adv_pct = 5%
        Max position allowed = 500k dollars
        
        If position_notional = 400k: OK (4% of ADV)
        If position_notional = 600k: REJECTED (6% of ADV)
    """
    if avg_daily_dollar_volume <= 0:
        return False, "Invalid ADV: must be > 0"
    
    position_adv_pct = position_notional / avg_daily_dollar_volume
    
    if position_adv_pct > max_adv_pct:
        reason = (
            f"Position too large: {position_notional:,.0f} "
            f"is {position_adv_pct:.2%} of ADV "
            f"({avg_daily_dollar_volume:,.0f}), "
            f"exceeds limit of {max_adv_pct:.2%}"
        )
        return False, reason
    
    return True, None


def compute_slippage_cost(
    entry_price_idealized: float,
    exit_price_idealized: float,
    entry_price_realistic: float,
    exit_price_realistic: float,
    position_size: float,
) -> Dict[str, float]:
    """
    Compute slippage costs between idealized and realistic fills.
    
    Args:
        entry_price_idealized: Original entry price (no slippage)
        exit_price_idealized: Original exit price (no slippage)
        entry_price_realistic: Entry price with slippage
        exit_price_realistic: Exit price with slippage
        position_size: Number of shares
    
    Returns:
        Dict with:
        - entry_slippage_cost: dollars lost on entry
        - exit_slippage_cost: dollars lost on exit
        - total_slippage_cost: sum of both
        - entry_slippage_bps: entry slippage in bps
        - exit_slippage_bps: exit slippage in bps
    """
    entry_slippage_cost = (entry_price_realistic - entry_price_idealized) * position_size
    exit_slippage_cost = (exit_price_idealized - exit_price_realistic) * position_size
    total_slippage_cost = entry_slippage_cost + exit_slippage_cost
    
    entry_slippage_bps = (entry_price_realistic / entry_price_idealized - 1) * 10000
    exit_slippage_bps = (exit_price_idealized / exit_price_realistic - 1) * 10000
    
    return {
        "entry_slippage_cost": entry_slippage_cost,
        "exit_slippage_cost": exit_slippage_cost,
        "total_slippage_cost": total_slippage_cost,
        "entry_slippage_bps": entry_slippage_bps,
        "exit_slippage_bps": exit_slippage_bps,
    }


class ExecutionModel:
    """
    Realistic execution model for backtesting.
    
    Applies execution realism without real-time or broker integration.
    """
    
    def __init__(
        self,
        entry_slippage_bps: int = ENTRY_SLIPPAGE_BPS,
        exit_slippage_bps: int = EXIT_SLIPPAGE_BPS,
        max_adv_pct: float = MAX_POSITION_ADV_PCT,
        use_next_open: bool = USE_NEXT_OPEN_ENTRY,
    ):
        """Initialize execution model with parameters."""
        self.entry_slippage_bps = entry_slippage_bps
        self.exit_slippage_bps = exit_slippage_bps
        self.max_adv_pct = max_adv_pct
        self.use_next_open = use_next_open
        
        # Statistics
        self.trades_rejected_liquidity = 0
        self.total_slippage_cost = 0.0
        self.total_slippage_trades = 0
    
    def get_entry_price(
        self,
        signal_date: pd.Timestamp,
        price_data: pd.DataFrame,
    ) -> Optional[float]:
        """Get entry price with slippage."""
        return compute_entry_price(signal_date, price_data, self.use_next_open)
    
    def get_exit_price(
        self,
        exit_date: pd.Timestamp,
        price_data: pd.DataFrame,
    ) -> Optional[float]:
        """Get exit price with slippage."""
        return compute_exit_price(exit_date, price_data, self.use_next_open)
    
    def check_liquidity_for_position(
        self,
        position_notional: float,
        avg_daily_dollar_volume: float,
    ) -> Tuple[bool, Optional[str]]:
        """Check if position meets liquidity requirements."""
        passed, reason = check_liquidity(
            position_notional,
            avg_daily_dollar_volume,
            self.max_adv_pct
        )
        
        if not passed:
            self.trades_rejected_liquidity += 1
        
        return passed, reason
    
    def get_summary(self) -> Dict[str, float]:
        """Get execution statistics."""
        return {
            "trades_rejected_liquidity": self.trades_rejected_liquidity,
            "total_slippage_cost": self.total_slippage_cost,
            "total_slippage_trades": self.total_slippage_trades,
            "avg_slippage_per_trade": (
                self.total_slippage_cost / self.total_slippage_trades
                if self.total_slippage_trades > 0 else 0.0
            ),
        }
