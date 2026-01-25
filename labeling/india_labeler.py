"""
India-specific labels for ML training (Phase D).

Defines win/loss labels compatible with existing ML pipeline.
India-specific: 7-day horizon, 2.5% target, 1.5% max drawdown.
"""

import pandas as pd
import numpy as np
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# INDIA LABELING CONFIGURATION
# ============================================================================
DEFAULT_HORIZON_DAYS = 7           # 7 trading days (vs 5 US)
DEFAULT_TARGET_RETURN = 0.025      # +2.5% target return
DEFAULT_MAX_DRAWDOWN = -0.015      # -1.5% max drawdown


# ============================================================================
# INDIA LABELER
# ============================================================================
def label_india_signals(
    df: pd.DataFrame,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    target_return: float = DEFAULT_TARGET_RETURN,
    max_drawdown: float = DEFAULT_MAX_DRAWDOWN,
    symbol: str = "",
) -> pd.DataFrame:
    """
    Create win/loss labels for India signals.
    
    Label = 1 if:
        - Price reaches +target_return % within horizon_days
        - WITHOUT dropping max_drawdown % in between
    
    Label = 0 otherwise.
    
    Args:
        df: OHLCV DataFrame with columns [date, open, high, low, close]
        horizon_days: Forward-looking window (days)
        target_return: Win target (e.g., 0.025 = +2.5%)
        max_drawdown: Max acceptable drawdown (e.g., -0.015 = -1.5%)
        symbol: Stock symbol (for logging)
        
    Returns:
        DataFrame with added 'label' column (0 or 1)
    """
    df = df.copy()
    df["label"] = np.nan
    
    entry_price = df["close"].values
    horizon = horizon_days
    
    # For each row, look ahead
    for i in range(len(df) - horizon):
        entry = entry_price[i]
        if entry <= 0 or np.isnan(entry):
            continue
        
        # Look ahead window
        future_closes = df["close"].iloc[i:i+horizon+1].values
        future_highs = df["high"].iloc[i:i+horizon+1].values
        future_lows = df["low"].iloc[i:i+horizon+1].values
        
        # Check if target reached
        max_future = future_highs.max()
        max_return = (max_future - entry) / entry
        
        # Check max drawdown
        min_future = future_lows.min()
        min_drawdown = (min_future - entry) / entry
        
        # Label: win if target reached and drawdown not too deep
        if max_return >= target_return and min_drawdown >= max_drawdown:
            df.loc[i, "label"] = 1
        else:
            df.loc[i, "label"] = 0
    
    # Summary
    labeled_count = df["label"].notna().sum()
    win_rate = df["label"].mean() if labeled_count > 0 else 0
    
    logger.info(
        f"[INDIA] {symbol}: Labeled {labeled_count} signals, "
        f"win rate {win_rate:.1%}"
    )
    
    return df


# ============================================================================
# BULK LABELING
# ============================================================================
def label_india_universe(
    data: dict,  # {symbol: DataFrame}
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    target_return: float = DEFAULT_TARGET_RETURN,
    max_drawdown: float = DEFAULT_MAX_DRAWDOWN,
) -> dict:
    """
    Label all symbols in universe.
    
    Args:
        data: {symbol: DataFrame} with OHLCV
        horizon_days: Forward-looking window
        target_return: Win target
        max_drawdown: Max drawdown
        
    Returns:
        {symbol: DataFrame} with labels
    """
    labeled_data = {}
    
    for symbol, df in data.items():
        try:
            df_labeled = label_india_signals(
                df,
                horizon_days=horizon_days,
                target_return=target_return,
                max_drawdown=max_drawdown,
                symbol=symbol,
            )
            labeled_data[symbol] = df_labeled
        except Exception as e:
            logger.error(f"[INDIA] Error labeling {symbol}: {e}")
    
    logger.info(f"[INDIA] Labeled {len(labeled_data)} symbols")
    return labeled_data


# ============================================================================
# LABEL STATISTICS
# ============================================================================
def get_label_stats(data: dict) -> dict:
    """
    Compute label statistics across universe.
    
    Returns:
        {
            "total_labeled": int,
            "total_wins": int,
            "win_rate": float,
            "by_symbol": {symbol: {"total": int, "wins": int, "rate": float}}
        }
    """
    total_labeled = 0
    total_wins = 0
    by_symbol = {}
    
    for symbol, df in data.items():
        labeled = df["label"].notna().sum()
        wins = df["label"].sum() if labeled > 0 else 0
        rate = wins / labeled if labeled > 0 else 0
        
        by_symbol[symbol] = {
            "total": labeled,
            "wins": wins,
            "rate": rate,
        }
        
        total_labeled += labeled
        total_wins += wins
    
    overall_rate = total_wins / total_labeled if total_labeled > 0 else 0
    
    return {
        "total_labeled": total_labeled,
        "total_wins": total_wins,
        "win_rate": overall_rate,
        "by_symbol": by_symbol,
    }


# ============================================================================
# TESTING
# ============================================================================
if __name__ == "__main__":
    print("\n[TEST] India labeling...")
    
    # Create sample data
    np.random.seed(42)
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    prices = 100 * np.exp(np.random.randn(100).cumsum() * 0.02)
    
    df_sample = pd.DataFrame({
        "date": dates,
        "open": prices * 0.99,
        "high": prices * 1.02,
        "low": prices * 0.98,
        "close": prices,
        "volume": np.random.randint(1_000_000, 5_000_000, 100),
    })
    
    # Label
    df_labeled = label_india_signals(df_sample, symbol="TEST")
    
    # Stats
    stats = get_label_stats({"TEST": df_labeled})
    print(f"\nTotal labeled: {stats['total_labeled']}")
    print(f"Win rate: {stats['win_rate']:.1%}")
