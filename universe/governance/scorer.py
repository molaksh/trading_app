"""
Phase G Scorer: Deterministic 5-dimension scoring engine for universe governance.

Scores each candidate symbol 0-100 across:
1. Performance (0.45) — Trade ledger win rate, avg return, Sharpe proxy
2. Regime (0.25)      — Current regime signal mapped to score
3. Liquidity (0.15)   — 20-day avg daily volume normalized vs universe median
4. Volatility (0.10)  — Sweet-spot curve (too low or too high = lower score)
5. Sentiment (0.05)   — Phase F verdict confidence + narrative consistency
"""

import logging
import math
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from universe.governance.config import SCORE_WEIGHTS

logger = logging.getLogger(__name__)


@dataclass
class ScoredCandidate:
    symbol: str
    total_score: float
    dimension_scores: Dict[str, float]
    weighted_scores: Dict[str, float]
    raw_metrics: Dict[str, Any]
    regime_label: str
    timestamp_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UniverseScorer:
    """Deterministic scoring engine for universe candidate selection."""

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or SCORE_WEIGHTS

    def score_symbol(
        self,
        symbol: str,
        ohlcv_df,
        trade_history: list,
        regime_label: str,
        verdict: Optional[Dict[str, Any]] = None,
        universe_median_volume: Optional[float] = None,
    ) -> ScoredCandidate:
        """Score a single symbol across all 5 dimensions."""
        raw_metrics: Dict[str, Any] = {}
        dimension_scores: Dict[str, float] = {}

        # 1. Performance score
        perf_score, perf_metrics = self._score_performance(trade_history)
        dimension_scores["performance"] = perf_score
        raw_metrics.update(perf_metrics)

        # 2. Regime score
        regime_score = self._score_regime(regime_label)
        dimension_scores["regime"] = regime_score
        raw_metrics["regime_label"] = regime_label

        # 3. Liquidity score
        liq_score, liq_metrics = self._score_liquidity(ohlcv_df, universe_median_volume)
        dimension_scores["liquidity"] = liq_score
        raw_metrics.update(liq_metrics)

        # 4. Volatility score
        vol_score, vol_metrics = self._score_volatility(ohlcv_df)
        dimension_scores["volatility"] = vol_score
        raw_metrics.update(vol_metrics)

        # 5. Sentiment score
        sent_score, sent_metrics = self._score_sentiment(verdict)
        dimension_scores["sentiment"] = sent_score
        raw_metrics.update(sent_metrics)

        # Weighted total
        weighted_scores = {
            dim: dimension_scores[dim] * self.weights[dim]
            for dim in self.weights
        }
        total_score = sum(weighted_scores.values())

        return ScoredCandidate(
            symbol=symbol,
            total_score=round(total_score, 2),
            dimension_scores={k: round(v, 2) for k, v in dimension_scores.items()},
            weighted_scores={k: round(v, 2) for k, v in weighted_scores.items()},
            raw_metrics=raw_metrics,
            regime_label=regime_label,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )

    def score_universe(
        self,
        candidates: List[str],
        ohlcv_data: Dict[str, Any],
        trade_history_by_symbol: Dict[str, list],
        regime_label: str,
        verdict: Optional[Dict[str, Any]] = None,
    ) -> List[ScoredCandidate]:
        """Score all candidates and return sorted by total_score descending."""
        # Compute universe median volume for liquidity normalization
        volumes = []
        for symbol in candidates:
            df = ohlcv_data.get(symbol)
            if df is not None and len(df) >= 20:
                try:
                    vol_col = self._get_volume_column(df)
                    if vol_col:
                        avg_vol = float(df[vol_col].tail(20).mean())
                        if avg_vol > 0:
                            volumes.append(avg_vol)
                except Exception:
                    pass
        universe_median_volume = statistics.median(volumes) if volumes else None

        scored = []
        for symbol in candidates:
            try:
                df = ohlcv_data.get(symbol)
                if df is None or len(df) < 5:
                    logger.warning("SCORER_SKIP | symbol=%s | reason=insufficient_data", symbol)
                    continue

                trades = trade_history_by_symbol.get(symbol, [])

                candidate = self.score_symbol(
                    symbol=symbol,
                    ohlcv_df=df,
                    trade_history=trades,
                    regime_label=regime_label,
                    verdict=verdict,
                    universe_median_volume=universe_median_volume,
                )
                scored.append(candidate)
            except Exception as e:
                logger.error("SCORER_ERROR | symbol=%s | error=%s", symbol, e, exc_info=True)

        scored.sort(key=lambda c: c.total_score, reverse=True)
        return scored

    # ========================================================================
    # Dimension Scoring Functions
    # ========================================================================

    def _score_performance(self, trade_history: list) -> tuple:
        """Score based on trade ledger: win rate, avg return, Sharpe proxy."""
        metrics: Dict[str, Any] = {
            "trade_count": 0,
            "win_rate": 0.0,
            "avg_return_pct": 0.0,
            "sharpe_proxy": 0.0,
        }

        if not trade_history:
            # No trade history: neutral score
            return 50.0, metrics

        # Use last 30 trades max
        recent = trade_history[-30:]
        metrics["trade_count"] = len(recent)

        returns = []
        wins = 0
        for trade in recent:
            pnl_pct = getattr(trade, "net_pnl_pct", None)
            if pnl_pct is None:
                pnl_pct = trade.get("net_pnl_pct", 0.0) if isinstance(trade, dict) else 0.0
            returns.append(float(pnl_pct))
            if float(pnl_pct) > 0:
                wins += 1

        win_rate = wins / len(recent) if recent else 0.0
        avg_return = sum(returns) / len(returns) if returns else 0.0

        # Sharpe proxy: mean / std (annualized approximation not needed for ranking)
        if len(returns) > 1:
            std = statistics.stdev(returns)
            sharpe_proxy = avg_return / std if std > 0 else 0.0
        else:
            sharpe_proxy = 0.0

        metrics["win_rate"] = round(win_rate, 4)
        metrics["avg_return_pct"] = round(avg_return, 6)
        metrics["sharpe_proxy"] = round(sharpe_proxy, 4)

        # Map to 0-100 score
        # Win rate contributes 60%, Sharpe proxy 40%
        win_score = min(100.0, max(0.0, win_rate * 100.0))
        sharpe_score = min(100.0, max(0.0, 50.0 + sharpe_proxy * 25.0))

        score = win_score * 0.6 + sharpe_score * 0.4
        return round(min(100.0, max(0.0, score)), 2), metrics

    def _score_regime(self, regime_label: str) -> float:
        """Map regime label to score."""
        regime_map = {
            "risk_on": 100.0,
            "neutral": 70.0,
            "risk_off": 40.0,
            "panic": 10.0,
        }
        return regime_map.get(regime_label, 50.0)

    def _score_liquidity(self, ohlcv_df, universe_median_volume: Optional[float]) -> tuple:
        """Score based on 20-day average daily volume vs universe median."""
        metrics: Dict[str, Any] = {
            "avg_daily_volume": 0.0,
            "universe_median_volume": universe_median_volume,
        }

        if ohlcv_df is None or len(ohlcv_df) < 5:
            return 50.0, metrics

        vol_col = self._get_volume_column(ohlcv_df)
        if not vol_col:
            return 50.0, metrics

        lookback = min(20, len(ohlcv_df))
        avg_vol = float(ohlcv_df[vol_col].tail(lookback).mean())
        metrics["avg_daily_volume"] = round(avg_vol, 2)

        if not universe_median_volume or universe_median_volume <= 0:
            return 50.0, metrics

        # Ratio to median: 1.0 = median, 2.0 = 2x median, etc.
        ratio = avg_vol / universe_median_volume

        # Score: logarithmic scale, capped at 100
        if ratio <= 0:
            score = 0.0
        else:
            score = min(100.0, 50.0 + 25.0 * math.log2(max(ratio, 0.01)))

        return round(max(0.0, score), 2), metrics

    def _score_volatility(self, ohlcv_df) -> tuple:
        """Score volatility with sweet-spot curve: too low or too high = lower score."""
        metrics: Dict[str, Any] = {
            "realized_vol_20d": 0.0,
        }

        if ohlcv_df is None or len(ohlcv_df) < 10:
            return 50.0, metrics

        close_col = self._get_close_column(ohlcv_df)
        if not close_col:
            return 50.0, metrics

        closes = ohlcv_df[close_col].tail(21).values
        if len(closes) < 2:
            return 50.0, metrics

        # Daily log returns
        returns = []
        for i in range(1, len(closes)):
            if closes[i] > 0 and closes[i - 1] > 0:
                returns.append(math.log(closes[i] / closes[i - 1]))

        if len(returns) < 5:
            return 50.0, metrics

        std_daily = statistics.stdev(returns)
        realized_vol = std_daily * math.sqrt(365) * 100  # annualized %

        metrics["realized_vol_20d"] = round(realized_vol, 2)

        # Sweet spot curve: peak score at ~40-60% annualized vol
        # Too low (<15%): boring, not enough opportunity
        # Too high (>120%): dangerous, too risky
        if realized_vol < 5:
            score = 20.0
        elif realized_vol < 15:
            score = 20.0 + (realized_vol - 5) * 4.0  # 20 -> 60
        elif realized_vol < 40:
            score = 60.0 + (realized_vol - 15) * 1.6  # 60 -> 100
        elif realized_vol <= 70:
            score = 100.0  # Sweet spot
        elif realized_vol <= 120:
            score = 100.0 - (realized_vol - 70) * 1.0  # 100 -> 50
        else:
            score = max(10.0, 50.0 - (realized_vol - 120) * 0.5)

        return round(min(100.0, max(0.0, score)), 2), metrics

    def _score_sentiment(self, verdict: Optional[Dict[str, Any]]) -> tuple:
        """Score based on Phase F verdict confidence + narrative consistency."""
        metrics: Dict[str, Any] = {
            "verdict_type": None,
            "regime_confidence": None,
            "narrative_consistency": None,
        }

        if not verdict or "verdict" not in verdict:
            return 50.0, metrics  # Neutral when no verdict available

        v = verdict["verdict"]
        verdict_type = v.get("verdict", "")
        confidence = v.get("regime_confidence", 0.5)
        consistency = v.get("narrative_consistency", "MIXED")

        metrics["verdict_type"] = verdict_type
        metrics["regime_confidence"] = confidence
        metrics["narrative_consistency"] = consistency

        # Base score from verdict type
        verdict_score_map = {
            "REGIME_VALIDATED": 80.0,
            "POSSIBLE_STRUCTURAL_SHIFT_OBSERVE": 60.0,
            "REGIME_QUESTIONABLE": 40.0,
            "HIGH_NOISE_NO_ACTION": 30.0,
        }
        base = verdict_score_map.get(verdict_type, 50.0)

        # Adjust by confidence (0-1 scale)
        confidence_adj = (float(confidence) - 0.5) * 20.0  # +/-10 adjustment

        # Adjust by narrative consistency
        consistency_adj = {"HIGH": 10.0, "MIXED": 0.0, "LOW": -10.0}.get(consistency, 0.0)

        score = base + confidence_adj + consistency_adj
        return round(min(100.0, max(0.0, score)), 2), metrics

    # ========================================================================
    # Helpers
    # ========================================================================

    def _get_volume_column(self, df) -> Optional[str]:
        """Find the volume column in the dataframe."""
        for col in ["Volume", "volume", "vol"]:
            if col in df.columns:
                return col
        return None

    def _get_close_column(self, df) -> Optional[str]:
        """Find the close column in the dataframe."""
        for col in ["Close", "close"]:
            if col in df.columns:
                return col
        return None
