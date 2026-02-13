"""
Phase G Regime Proxy: SPY-based regime derivation for swing scope.

Reuses existing regime feature computation and threshold logic
from the crypto regime engine to derive a regime signal from SPY.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SPYRegimeProxy:
    """Derive market regime from SPY using the same logic as CryptoRegimeEngine."""

    def get_regime(self) -> Optional[str]:
        """
        Compute regime from SPY daily OHLCV.

        Returns:
            Regime label string ("risk_on", "neutral", "risk_off", "panic")
            or None if data unavailable.
        """
        try:
            from data.price_loader import load_price_data
            from crypto.features.regime_features import build_regime_features
            from crypto.regime.crypto_regime_engine import (
                CryptoRegimeEngine,
                RegimeThresholds,
            )

            # Fetch SPY daily data (20-day lookback minimum, use 100 for safety)
            df = load_price_data("SPY", lookback_days=100)
            if df is None or len(df) < 20:
                logger.warning("SPY_REGIME_PROXY | insufficient data | rows=%s",
                               len(df) if df is not None else 0)
                return None

            # Build regime features using SPY as "symbol"
            # Rename columns to match expected format if needed
            import pandas as pd
            bars = df.copy()
            # Ensure column names match what build_regime_features expects
            col_map = {}
            for col in bars.columns:
                if col.lower() == "open":
                    col_map[col] = "Open"
                elif col.lower() == "high":
                    col_map[col] = "High"
                elif col.lower() == "low":
                    col_map[col] = "Low"
                elif col.lower() == "close":
                    col_map[col] = "Close"
                elif col.lower() == "volume":
                    col_map[col] = "Volume"
            if col_map:
                bars = bars.rename(columns=col_map)

            # Ensure datetime index
            if not isinstance(bars.index, pd.DatetimeIndex):
                bars.index = pd.to_datetime(bars.index)

            features = build_regime_features(
                symbol="SPY",
                bars_4h=bars,  # Daily bars treated as period bars
                lookback_periods=min(100, len(bars)),
            )

            # Run through regime engine
            engine = CryptoRegimeEngine(thresholds=RegimeThresholds())
            signal = engine.analyze(features)

            regime_label = signal.regime.value
            logger.info(
                "SPY_REGIME_PROXY | regime=%s | volatility=%.1f | "
                "trend_slope=%.4f | drawdown=%.2f | confidence=%.2f",
                regime_label, signal.volatility, signal.trend_slope,
                signal.drawdown, signal.confidence,
            )
            return regime_label

        except Exception as e:
            logger.error("SPY_REGIME_PROXY | error=%s", e, exc_info=True)
            return None
