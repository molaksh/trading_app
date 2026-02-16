"""
Phase H Layer 2: Per-Asset Regime Engine.

Scores each accepted universe symbol on 4 dimensions:
  1. Trend 4h        (0.35) — SMA slope direction/strength
  2. Vol contraction  (0.25) — lower vol = higher score
  3. Relative strength vs BTC (0.20)
  4. Momentum         (0.20) — ROC / price vs SMA

Classification: >= 0.75 VERY_STRONG, >= 0.60 STRONG, >= 0.45 NEUTRAL, < 0.45 WEAK
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

from phase_h_crypto_regime.config import (
    ASSET_VERY_STRONG,
    ASSET_STRONG,
    ASSET_NEUTRAL,
)

logger = logging.getLogger(__name__)


@dataclass
class AssetRegimeResult:
    """Result for a single asset's regime score."""
    symbol: str
    asset_score: float          # 0.0 - 1.0
    asset_regime: str           # VERY_STRONG, STRONG, NEUTRAL, WEAK
    components: Dict[str, float] = field(default_factory=dict)


class AssetRegimeEngine:
    """
    Per-asset scoring for universe symbols.

    Score = 0.35 * trend_4h + 0.25 * vol_contraction +
            0.20 * relative_strength_vs_btc + 0.20 * momentum
    """

    WEIGHTS = {
        "trend_4h": 0.35,
        "vol_contraction": 0.25,
        "relative_strength_vs_btc": 0.20,
        "momentum": 0.20,
    }

    def score_asset(
        self,
        symbol: str,
        bars_4h: pd.DataFrame,
        btc_bars_4h: pd.DataFrame,
    ) -> AssetRegimeResult:
        """
        Score a single asset.

        Args:
            symbol: Canonical symbol
            bars_4h: 4h OHLCV for this asset
            btc_bars_4h: 4h OHLCV for BTC (reference)

        Returns:
            AssetRegimeResult
        """
        components = {}

        components["trend_4h"] = self._trend_score(bars_4h)
        components["vol_contraction"] = self._vol_contraction_score(bars_4h)
        components["relative_strength_vs_btc"] = self._relative_strength(bars_4h, btc_bars_4h)
        components["momentum"] = self._momentum_score(bars_4h)

        asset_score = sum(
            self.WEIGHTS[k] * components[k] for k in self.WEIGHTS
        )
        asset_score = max(0.0, min(1.0, asset_score))
        asset_regime = self._classify(asset_score)

        return AssetRegimeResult(
            symbol=symbol,
            asset_score=round(asset_score, 4),
            asset_regime=asset_regime,
            components={k: round(v, 4) for k, v in components.items()},
        )

    def score_universe(
        self,
        universe_bars_4h: Dict[str, pd.DataFrame],
        btc_bars_4h: pd.DataFrame,
    ) -> Dict[str, AssetRegimeResult]:
        """Score all symbols in the universe."""
        results = {}
        for symbol, bars in universe_bars_4h.items():
            if bars is None or bars.empty:
                continue
            try:
                results[symbol] = self.score_asset(symbol, bars, btc_bars_4h)
            except Exception as e:
                logger.warning("Failed to score asset %s: %s", symbol, e)
        return results

    def _trend_score(self, bars_4h: pd.DataFrame) -> float:
        """SMA slope normalized to 0-1. Positive slope = higher score."""
        if bars_4h is None or bars_4h.empty or len(bars_4h) < 50:
            return 0.50

        try:
            sma20 = bars_4h["Close"].rolling(window=20, min_periods=20).mean()
            sma50 = bars_4h["Close"].rolling(window=50, min_periods=50).mean()

            slope_20 = sma20.pct_change(periods=5).iloc[-1] * 100
            slope_50 = sma50.pct_change(periods=10).iloc[-1] * 100

            if pd.isna(slope_20) or pd.isna(slope_50):
                return 0.50

            combined = 0.6 * slope_20 + 0.4 * slope_50
            # Normalize: -5% to +5% -> 0 to 1
            normalized = (combined + 5.0) / 10.0
            return max(0.0, min(1.0, normalized))
        except Exception:
            return 0.50

    def _vol_contraction_score(self, bars_4h: pd.DataFrame) -> float:
        """Lower vol percentile = higher score (vol contraction is bullish)."""
        if bars_4h is None or bars_4h.empty or len(bars_4h) < 50:
            return 0.50

        try:
            log_ret = np.log(bars_4h["Close"] / bars_4h["Close"].shift(1))
            vol_20 = log_ret.rolling(window=20, min_periods=20).std()
            vol_series = vol_20.dropna()

            if len(vol_series) < 30:
                return 0.50

            current_vol = vol_series.iloc[-1]
            percentile = (vol_series < current_vol).sum() / len(vol_series)
            # Invert: low vol = high score
            return max(0.0, min(1.0, 1.0 - float(percentile)))
        except Exception:
            return 0.50

    def _relative_strength(
        self,
        bars_4h: pd.DataFrame,
        btc_bars_4h: pd.DataFrame,
    ) -> float:
        """Return relative to BTC over 20 periods, normalized to 0-1."""
        if (bars_4h is None or bars_4h.empty or len(bars_4h) < 20
                or btc_bars_4h is None or btc_bars_4h.empty or len(btc_bars_4h) < 20):
            return 0.50

        try:
            asset_ret = (bars_4h["Close"].iloc[-1] / bars_4h["Close"].iloc[-20]) - 1.0
            btc_ret = (btc_bars_4h["Close"].iloc[-1] / btc_bars_4h["Close"].iloc[-20]) - 1.0

            # Relative return difference
            diff = asset_ret - btc_ret
            # Normalize: -10% to +10% -> 0 to 1
            normalized = (diff + 0.10) / 0.20
            return max(0.0, min(1.0, normalized))
        except Exception:
            return 0.50

    def _momentum_score(self, bars_4h: pd.DataFrame) -> float:
        """Rate of change + price vs SMA, normalized to 0-1."""
        if bars_4h is None or bars_4h.empty or len(bars_4h) < 50:
            return 0.50

        try:
            close = bars_4h["Close"]
            # ROC over 20 periods
            roc = (close.iloc[-1] / close.iloc[-20]) - 1.0

            # Price vs SMA50
            sma50 = close.rolling(window=50, min_periods=50).mean().iloc[-1]
            if pd.isna(sma50) or sma50 <= 0:
                return 0.50
            price_vs_sma = (close.iloc[-1] - sma50) / sma50

            combined = 0.5 * roc + 0.5 * price_vs_sma
            # Normalize: -15% to +15% -> 0 to 1
            normalized = (combined + 0.15) / 0.30
            return max(0.0, min(1.0, normalized))
        except Exception:
            return 0.50

    @staticmethod
    def _classify(score: float) -> str:
        """Classify asset score into regime."""
        if score >= ASSET_VERY_STRONG:
            return "VERY_STRONG"
        elif score >= ASSET_STRONG:
            return "STRONG"
        elif score >= ASSET_NEUTRAL:
            return "NEUTRAL"
        else:
            return "WEAK"
