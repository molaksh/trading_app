"""
Label generator for ML dataset.
Given price data and an entry date, computes binary label (0 or 1) based on:
- Label = 1 if price reaches TARGET_RETURN within HORIZON_DAYS without falling below MAX_DRAWDOWN
- Label = 0 otherwise
No future data leakage: only uses data after entry date.
"""

import logging
from typing import Optional
import pandas as pd
import numpy as np
from config.settings import (
    LABEL_HORIZON_DAYS,
    LABEL_TARGET_RETURN,
    LABEL_MAX_DRAWDOWN,
)

logger = logging.getLogger(__name__)


def compute_label(
    price_series: pd.Series,
    entry_date: pd.Timestamp,
    entry_price: float
) -> Optional[int]:
    """
    Compute binary label for a single entry point.
    
    Given:
    - Entry at entry_date with entry_price
    - Forward horizon of LABEL_HORIZON_DAYS
    
    Return:
    - 1 if price reaches (entry_price * (1 + LABEL_TARGET_RETURN))
      within HORIZON_DAYS without falling below (entry_price * (1 + LABEL_MAX_DRAWDOWN))
    - 0 otherwise
    - None if insufficient forward data
    
    Parameters
    ----------
    price_series : pd.Series
        Series of prices indexed by date. Must contain entry_date and future dates.
    entry_date : pd.Timestamp
        Date of entry (must be in price_series index)
    entry_price : float
        Price at entry (typically close price on entry_date)
    
    Returns
    -------
    int or None
        Label (0 or 1) or None if entry_date not found or insufficient future data
    """
    # Validation
    if price_series is None or price_series.empty:
        logger.warning("Received empty price series")
        return None
    
    if entry_date not in price_series.index:
        logger.warning(f"Entry date {entry_date} not in price series")
        return None
    
    if entry_price <= 0:
        logger.warning(f"Invalid entry price: {entry_price}")
        return None
    
    try:
        # Get entry index
        entry_idx = price_series.index.get_loc(entry_date)
        
        # Extract forward looking window (next HORIZON_DAYS)
        end_idx = min(entry_idx + LABEL_HORIZON_DAYS, len(price_series))
        forward_prices = price_series.iloc[entry_idx + 1 : end_idx + 1]
        
        # Insufficient forward data
        if len(forward_prices) == 0:
            logger.debug(f"No forward data for {entry_date}")
            return None
        
        # Compute target levels
        target_price = entry_price * (1 + LABEL_TARGET_RETURN)
        max_loss_price = entry_price * (1 + LABEL_MAX_DRAWDOWN)
        
        # Check drawdown: if any price falls below max_loss_price, label = 0
        if (forward_prices < max_loss_price).any():
            label = 0
            logger.debug(
                f"{entry_date}: Drawdown violated (min={forward_prices.min():.2f} < {max_loss_price:.2f})"
            )
        # Check profit target: if any price reaches target_price, label = 1
        elif (forward_prices >= target_price).any():
            label = 1
            logger.debug(
                f"{entry_date}: Target reached (max={forward_prices.max():.2f} >= {target_price:.2f})"
            )
        else:
            # Neither target reached nor drawdown violated
            label = 0
            logger.debug(
                f"{entry_date}: No target, no loss (range=[{forward_prices.min():.2f}, {forward_prices.max():.2f}])"
            )
        
        return int(label)
    
    except Exception as e:
        logger.error(f"Label computation failed for {entry_date}: {type(e).__name__}: {e}")
        return None


def compute_labels_for_symbol(
    price_df: pd.DataFrame,
    valid_dates: Optional[list] = None
) -> Optional[pd.Series]:
    """
    Compute labels for multiple dates within a symbol's price history.
    
    Parameters
    ----------
    price_df : pd.DataFrame
        DataFrame with 'Close' column and date index.
        Must have at least (LABEL_HORIZON_DAYS + 1) rows.
    valid_dates : list, optional
        List of dates to compute labels for. If None, uses all dates
        except the last LABEL_HORIZON_DAYS (which lack sufficient forward data).
    
    Returns
    -------
    pd.Series or None
        Series indexed by date with label values (0 or 1),
        or None if input validation fails
    """
    if price_df is None or price_df.empty:
        logger.warning("Received empty price DataFrame")
        return None
    
    if 'Close' not in price_df.columns:
        logger.error("Price DataFrame missing 'Close' column")
        return None
    
    try:
        close_prices = price_df['Close']
        
        # Determine dates to label
        if valid_dates is None:
            # Use all dates except last LABEL_HORIZON_DAYS
            valid_dates = close_prices.index[:-LABEL_HORIZON_DAYS]
        
        if len(valid_dates) == 0:
            logger.warning(f"No valid dates for labeling (horizon={LABEL_HORIZON_DAYS})")
            return None
        
        # Compute labels
        labels = {}
        for date in valid_dates:
            label = compute_label(close_prices, date, close_prices[date])
            if label is not None:
                labels[date] = label
        
        if len(labels) == 0:
            logger.warning("No labels computed")
            return None
        
        result = pd.Series(labels, dtype='int8')
        logger.debug(f"Computed {len(result)} labels: {(result == 1).sum()} positive, {(result == 0).sum()} negative")
        
        return result
    
    except Exception as e:
        logger.error(f"Batch label computation failed: {type(e).__name__}: {e}")
        return None
