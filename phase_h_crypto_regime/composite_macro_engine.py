"""
Phase H Layer 1: Composite Macro Engine.

Replaces BTC-only macro with 5-component weighted score:
  1. BTC regime score (0.40)
  2. ETH regime score (0.20)
  3. Total market trend (0.15) — weighted avg SMA slope across universe
  4. ALT vs BTC relative strength (0.15)
  5. Volatility expansion (0.10) — BTC vol percentile

Output: CompositeMacroResult with macro_score, macro_regime, macro_confidence.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
import pandas as pd

from phase_h_crypto_regime.config import (
    MACRO_WEIGHTS,
    MACRO_RISK_ON,
    MACRO_NEUTRAL_LOW,
    MACRO_RISK_OFF_LOW,
)
from crypto.features.regime_features import build_regime_features
from crypto.regime.crypto_regime_engine import CryptoRegimeEngine, RegimeThresholds, MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class CompositeMacroResult:
    """Result of composite macro analysis."""
    macro_score: float          # 0.0 - 1.0
    macro_regime: str           # RISK_ON, NEUTRAL, RISK_OFF, PANIC
    macro_confidence: float     # 0.0 - 1.0
    component_scores: Dict[str, float] = field(default_factory=dict)


class CompositeMacroEngine:
    """
    Computes composite macro score from 5 weighted components.

    Uses existing build_regime_features + fresh CryptoRegimeEngine
    (no hysteresis) for BTC/ETH regime scores.
    """

    def __init__(self):
        self.weights = MACRO_WEIGHTS

    def compute(
        self,
        btc_4h: pd.DataFrame,
        eth_4h: Optional[pd.DataFrame],
        universe_bars_4h: Dict[str, pd.DataFrame],
    ) -> CompositeMacroResult:
        """
        Compute composite macro score.

        Args:
            btc_4h: BTC 4h OHLCV bars
            eth_4h: ETH 4h OHLCV bars (optional)
            universe_bars_4h: Dict of symbol -> 4h bars for all universe symbols

        Returns:
            CompositeMacroResult
        """
        components = {}

        # Component 1: BTC regime score
        btc_score = self._regime_score(btc_4h, "BTC", universe_bars_4h)
        components["btc_regime"] = btc_score

        # Component 2: ETH regime score
        if eth_4h is not None and not eth_4h.empty:
            eth_score = self._regime_score(eth_4h, "ETH", universe_bars_4h)
        else:
            eth_score = btc_score  # fallback to BTC
        components["eth_regime"] = eth_score

        # Component 3: Total market trend (weighted avg SMA slope)
        total_trend = self._total_market_trend(universe_bars_4h)
        components["total_market_trend"] = total_trend

        # Component 4: ALT vs BTC relative strength
        alt_strength = self._alt_vs_btc_strength(btc_4h, universe_bars_4h)
        components["alt_vs_btc_strength"] = alt_strength

        # Component 5: Volatility expansion (BTC vol percentile)
        vol_expansion = self._volatility_expansion(btc_4h)
        components["volatility_expansion"] = vol_expansion

        # Weighted composite
        macro_score = sum(
            self.weights[k] * components[k] for k in self.weights
        )
        macro_score = max(0.0, min(1.0, macro_score))

        # Classify regime
        macro_regime = self._classify(macro_score)

        # Confidence: how far from nearest threshold
        confidence = self._compute_confidence(macro_score, components)

        return CompositeMacroResult(
            macro_score=round(macro_score, 4),
            macro_regime=macro_regime,
            macro_confidence=round(confidence, 4),
            component_scores={k: round(v, 4) for k, v in components.items()},
        )

    def _regime_score(
        self,
        bars_4h: pd.DataFrame,
        symbol: str,
        correlation_bars: Dict[str, pd.DataFrame],
    ) -> float:
        """Convert regime classification to 0-1 score."""
        try:
            features = build_regime_features(
                symbol=symbol,
                bars_4h=bars_4h,
                lookback_periods=min(100, len(bars_4h)),
                correlation_symbols=correlation_bars,
            )
            engine = CryptoRegimeEngine(thresholds=RegimeThresholds())
            signal = engine.analyze(features)

            regime_scores = {
                MarketRegime.RISK_ON: 0.90,
                MarketRegime.NEUTRAL: 0.65,
                MarketRegime.RISK_OFF: 0.35,
                MarketRegime.PANIC: 0.10,
            }
            return regime_scores.get(signal.regime, 0.50)
        except Exception as e:
            logger.warning("Failed to compute regime score for %s: %s", symbol, e)
            return 0.50

    def _total_market_trend(self, universe_bars_4h: Dict[str, pd.DataFrame]) -> float:
        """Weighted average SMA slope across universe, normalized to 0-1."""
        slopes = []
        for symbol, bars in universe_bars_4h.items():
            if bars is None or bars.empty or len(bars) < 50:
                continue
            try:
                sma50 = bars["Close"].rolling(window=50, min_periods=50).mean()
                slope = sma50.pct_change(periods=10).iloc[-1] * 100
                if pd.notna(slope):
                    slopes.append(slope)
            except Exception:
                continue

        if not slopes:
            return 0.50

        avg_slope = float(np.mean(slopes))
        # Normalize: -5% to +5% -> 0 to 1
        normalized = (avg_slope + 5.0) / 10.0
        return max(0.0, min(1.0, normalized))

    def _alt_vs_btc_strength(
        self,
        btc_4h: pd.DataFrame,
        universe_bars_4h: Dict[str, pd.DataFrame],
    ) -> float:
        """Relative strength: alt avg return / BTC return, normalized to 0-1."""
        if btc_4h is None or btc_4h.empty or len(btc_4h) < 20:
            return 0.50

        try:
            btc_ret = (btc_4h["Close"].iloc[-1] / btc_4h["Close"].iloc[-20]) - 1.0
        except Exception:
            return 0.50

        alt_rets = []
        for symbol, bars in universe_bars_4h.items():
            if symbol == "BTC" or bars is None or bars.empty or len(bars) < 20:
                continue
            try:
                ret = (bars["Close"].iloc[-1] / bars["Close"].iloc[-20]) - 1.0
                alt_rets.append(ret)
            except Exception:
                continue

        if not alt_rets:
            return 0.50

        avg_alt_ret = float(np.mean(alt_rets))

        # Relative strength ratio
        if abs(btc_ret) < 1e-8:
            ratio = 1.0 if avg_alt_ret >= 0 else 0.0
        else:
            ratio = avg_alt_ret / btc_ret if btc_ret > 0 else -(avg_alt_ret / btc_ret)

        # Normalize: 0.5 to 2.0 -> 0 to 1
        normalized = (ratio - 0.5) / 1.5
        return max(0.0, min(1.0, normalized))

    def _volatility_expansion(self, btc_4h: pd.DataFrame) -> float:
        """BTC vol percentile, inverted (low vol = high score = risk on)."""
        if btc_4h is None or btc_4h.empty or len(btc_4h) < 100:
            return 0.50

        try:
            log_returns = np.log(btc_4h["Close"] / btc_4h["Close"].shift(1))
            vol_20 = log_returns.rolling(window=20, min_periods=20).std()
            vol_series = vol_20.dropna()

            if len(vol_series) < 50:
                return 0.50

            current_vol = vol_series.iloc[-1]
            percentile = (vol_series < current_vol).sum() / len(vol_series)

            # Invert: low vol percentile = high score (risk on)
            return max(0.0, min(1.0, 1.0 - float(percentile)))
        except Exception as e:
            logger.warning("Failed to compute vol expansion: %s", e)
            return 0.50

    @staticmethod
    def _classify(macro_score: float) -> str:
        """Classify macro score into regime."""
        if macro_score >= MACRO_RISK_ON:
            return "RISK_ON"
        elif macro_score >= MACRO_NEUTRAL_LOW:
            return "NEUTRAL"
        elif macro_score >= MACRO_RISK_OFF_LOW:
            return "RISK_OFF"
        else:
            return "PANIC"

    @staticmethod
    def _compute_confidence(macro_score: float, components: Dict[str, float]) -> float:
        """Confidence based on distance from thresholds and component agreement."""
        thresholds = [MACRO_RISK_ON, MACRO_NEUTRAL_LOW, MACRO_RISK_OFF_LOW]
        min_dist = min(abs(macro_score - t) for t in thresholds)

        # Distance component (0-0.5)
        distance_conf = min(0.5, min_dist * 2.5)

        # Agreement component (0-0.5): how similar are all components
        vals = list(components.values())
        if vals:
            spread = max(vals) - min(vals)
            agreement_conf = max(0.0, 0.5 - spread * 0.5)
        else:
            agreement_conf = 0.25

        return max(0.1, min(1.0, distance_conf + agreement_conf))
