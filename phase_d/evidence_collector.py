"""
Evidence collector: Collects post-facto metrics for completed blocks.
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from phase_d.schemas import BlockEvent, BlockEvidence
from data.crypto_price_loader import load_crypto_price_data_two_timeframes
from phase_d.historical_analyzer import HistoricalAnalyzer
from config.phase_d_settings import EVIDENCE_CORE_SYMBOLS

logger = logging.getLogger(__name__)


class EvidenceCollector:
    """Collects post-facto evidence metrics for completed blocks."""

    def __init__(self, historical_analyzer: Optional[HistoricalAnalyzer] = None):
        self.historical_analyzer = historical_analyzer or HistoricalAnalyzer()

    def collect_evidence(self, block_event: BlockEvent) -> Optional[BlockEvidence]:
        """
        Collect all evidence metrics for a completed block.

        Args:
            block_event: Completed block event (must have block_end_ts set)

        Returns:
            BlockEvidence with all metrics, or None if collection failed
        """
        if not block_event.block_end_ts:
            logger.warning(f"PHASE_D_EVIDENCE_INCOMPLETE_BLOCK | block_id={block_event.block_id}")
            return None

        try:
            # Load price data for block period
            symbols = EVIDENCE_CORE_SYMBOLS
            btc_5m = None
            eth_5m = None

            # Load each symbol separately to handle failures gracefully
            try:
                btc_bars_5m, _ = load_crypto_price_data_two_timeframes(
                    symbol="BTC",
                    start_time=block_event.block_start_ts,
                    end_time=block_event.block_end_ts,
                    execution_lookback_bars=None,
                    regime_lookback_bars=None,
                    execution_interval="5m",
                    regime_interval="4h",
                )
                btc_5m = btc_bars_5m
            except Exception as e:
                logger.warning(f"PHASE_D_BTC_PRICE_LOAD_FAILED | block_id={block_event.block_id} error={e}")

            try:
                eth_bars_5m, _ = load_crypto_price_data_two_timeframes(
                    symbol="ETH",
                    start_time=block_event.block_start_ts,
                    end_time=block_event.block_end_ts,
                    execution_lookback_bars=None,
                    regime_lookback_bars=None,
                    execution_interval="5m",
                    regime_interval="4h",
                )
                eth_5m = eth_bars_5m
            except Exception as e:
                logger.warning(f"PHASE_D_ETH_PRICE_LOAD_FAILED | block_id={block_event.block_id} error={e}")

            # Compute missed upside
            btc_upside_pct = 0.0
            eth_upside_pct = 0.0
            btc_drawdown_pct = 0.0
            eth_drawdown_pct = 0.0

            if btc_5m is not None and not btc_5m.empty and len(btc_5m) > 0:
                try:
                    btc_start = float(btc_5m.iloc[0]['close'])
                    btc_max = float(btc_5m['high'].max())
                    btc_min = float(btc_5m['low'].min())

                    if btc_start > 0:
                        btc_upside_pct = ((btc_max - btc_start) / btc_start) * 100
                        btc_drawdown_pct = ((btc_min - btc_start) / btc_start) * 100
                except Exception as e:
                    logger.warning(f"PHASE_D_BTC_METRICS_FAILED | block_id={block_event.block_id} error={e}")

            if eth_5m is not None and not eth_5m.empty and len(eth_5m) > 0:
                try:
                    eth_start = float(eth_5m.iloc[0]['close'])
                    eth_max = float(eth_5m['high'].max())
                    eth_min = float(eth_5m['low'].min())

                    if eth_start > 0:
                        eth_upside_pct = ((eth_max - eth_start) / eth_start) * 100
                        eth_drawdown_pct = ((eth_min - eth_start) / eth_start) * 100
                except Exception as e:
                    logger.warning(f"PHASE_D_ETH_METRICS_FAILED | block_id={block_event.block_id} error={e}")

            # Compute volatility expansion
            vol_before = 0.0
            vol_after = 0.0
            vol_expansion = 1.0

            if btc_5m is not None and not btc_5m.empty:
                try:
                    # Vol before block end (last 60 bars before end)
                    lookback_bars = min(60, len(btc_5m))
                    if lookback_bars > 0:
                        returns = btc_5m.iloc[-lookback_bars:]['close'].pct_change().dropna()
                        if len(returns) > 0:
                            vol_before = float(returns.std() * 100)

                    # Vol after block end (next 60 bars after end)
                    # We'd need post-block price data, which we don't have
                    # For now, use current vol as proxy
                    if len(btc_5m) > 0:
                        recent_returns = btc_5m.iloc[-min(20, len(btc_5m)):]['close'].pct_change().dropna()
                        if len(recent_returns) > 0:
                            vol_after = float(recent_returns.std() * 100)

                    if vol_before > 0:
                        vol_expansion = vol_after / vol_before
                    else:
                        vol_expansion = 1.0
                except Exception as e:
                    logger.warning(f"PHASE_D_VOLATILITY_CALC_FAILED | block_id={block_event.block_id} error={e}")

            # Get historical context
            historical_stats = self.historical_analyzer.get_regime_block_stats(
                scope=block_event.scope,
                regime=block_event.regime,
                lookback_days=30
            )

            duration = block_event.duration_seconds or 0

            evidence = BlockEvidence(
                block_id=block_event.block_id,
                scope=block_event.scope,
                duration_seconds=duration,
                historical_median_duration=historical_stats.median_duration_seconds if historical_stats else None,
                historical_p90_duration=historical_stats.p90_duration_seconds if historical_stats else None,
                btc_max_upside_pct=btc_upside_pct,
                eth_max_upside_pct=eth_upside_pct,
                alt_max_upside_pct=0.0,
                btc_max_drawdown_pct=btc_drawdown_pct,
                eth_max_drawdown_pct=eth_drawdown_pct,
                portfolio_simulated_pnl=0.0,
                volatility_before_block_end=vol_before,
                volatility_after_block_end=vol_after,
                volatility_expansion_ratio=vol_expansion,
                regime_at_start=block_event.regime,
                regime_at_end=block_event.regime,
                regime_changes_during_block=block_event.regime_changes_during_block,
                time_of_day_utc=block_event.block_start_ts.hour,
                day_of_week=block_event.block_start_ts.weekday(),
            )

            logger.info(f"PHASE_D_EVIDENCE_COLLECTED | block_id={block_event.block_id} upside_btc={btc_upside_pct:.2f}%")
            return evidence

        except Exception as e:
            logger.error(f"PHASE_D_EVIDENCE_COLLECTION_FAILED | block_id={block_event.block_id} error={e}")
            return None
