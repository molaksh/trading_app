"""
Crypto pipeline execution (signals only) with two-timeframe candle model.

PIPELINE ORDER (MANDATORY):
Data → Feature Builder → Regime Engine → Strategy Selector → Signals → Risk → Execution → Broker → Reconciliation → Cycle Summary

NOTE: This module produces signals and emits pipeline logs. Execution and broker
steps remain in the existing trading executor.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from config.crypto.loader import load_crypto_config
from config.settings import MAX_TRADES_PER_DAY
from runtime.trade_permission import get_trade_permission
from runtime.ai_advisor import get_ai_runner
from runtime.observability import get_observability
from crypto.features import build_execution_features, build_regime_features
from crypto.pipeline.logging import log_pipeline_stage
from crypto.regime import CryptoRegimeEngine, RegimeThresholds, MarketRegime
from crypto.strategies import CryptoStrategySelector
from crypto.strategies.strategies_collection import CRYPTO_STRATEGIES
from crypto.scope_guard import validate_crypto_universe_symbols
from data.crypto_price_loader import load_crypto_price_data_two_timeframes

logger = logging.getLogger(__name__)

def run_crypto_pipeline(
    runtime,
    run_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Run the crypto signal-generation pipeline (no execution).

    Returns:
        DataFrame of signals to execute (symbol, confidence, close, strategy, intent, reason)
    """
    scope = runtime.scope
    crypto_config = load_crypto_config(scope)
    allowlist = crypto_config.get("UNIVERSE_ALLOWLIST") or crypto_config.get("CRYPTO_UNIVERSE")
    symbols = validate_crypto_universe_symbols(allowlist or ["BTC", "ETH", "SOL"])

    if run_id is None:
        run_id = str(uuid.uuid4())

    # CRITICAL FIX: Reset daily trades counter at start of each pipeline run
    # This ensures the counter resets each day and prevents capacity deadlock
    current_date = pd.Timestamp.now()
    portfolio = runtime.risk_manager.portfolio
    old_counter = portfolio.daily_trades_opened
    portfolio.update_equity_at_date(current_date)
    new_counter = portfolio.daily_trades_opened

    logger.info(
        f"DAILY_COUNTER_RESET | date={current_date.date()} | "
        f"old_value={old_counter} | new_value={new_counter} | "
        f"start_date={portfolio.daily_start_date}"
    )

    # Defensive check: if counter is stuck, reset it
    if new_counter > MAX_TRADES_PER_DAY:
        logger.warning(
            f"DAILY_COUNTER_STUCK | counter={new_counter} exceeds MAX={MAX_TRADES_PER_DAY}, "
            f"forcing reset to 0"
        )
        portfolio.daily_trades_opened = 0
        new_counter = 0

    # Config: lookbacks and intervals
    execution_interval = str(crypto_config.get("EXECUTION_CANDLE_INTERVAL", "5m"))
    regime_interval = str(crypto_config.get("REGIME_CANDLE_INTERVAL", "4h"))
    execution_lookback = int(crypto_config.get("EXECUTION_LOOKBACK_BARS", 500))
    regime_lookback = int(crypto_config.get("REGIME_LOOKBACK_BARS", 200))

    if execution_interval != "5m" or regime_interval != "4h":
        raise ValueError(
            f"CRYPTO_PIPELINE_INVALID_INTERVALS: execution={execution_interval} regime={regime_interval}"
        )

    # Stage 1: DATA
    bars_5m: Dict[str, pd.DataFrame] = {}
    bars_4h: Dict[str, pd.DataFrame] = {}
    permission = get_trade_permission()

    for symbol in symbols:
        exec_bars, regime_bars = load_crypto_price_data_two_timeframes(
            symbol=symbol,
            execution_lookback_bars=execution_lookback,
            regime_lookback_bars=regime_lookback,
            execution_interval=execution_interval,
            regime_interval=regime_interval,
        )
        if exec_bars is not None:
            _validate_timeframe(exec_bars, 5, symbol, execution_interval)
        if regime_bars is not None:
            _validate_timeframe(regime_bars, 240, symbol, regime_interval)
        bars_5m[symbol] = exec_bars
        bars_4h[symbol] = regime_bars

    # Block trading on partial/inconsistent market data (live mode)
    missing_exec = [s for s in symbols if bars_5m.get(s) is None or bars_5m[s].empty]
    missing_regime = [s for s in symbols if bars_4h.get(s) is None or bars_4h[s].empty]
    if missing_exec or missing_regime:
        reason = f"missing_exec={missing_exec} missing_regime={missing_regime}"
        if scope.env.lower() == "live":
            permission.set_block("MARKET_DATA_BLOCKED", reason)
        logger.warning(f"MARKET_DATA_BLOCKED | {reason}")
        return pd.DataFrame()
    else:
        if scope.env.lower() == "live":
            permission.clear_block("MARKET_DATA_BLOCKED", "market data complete")

    log_pipeline_stage(
        stage="DATA_LOADED",
        scope=str(scope),
        run_id=run_id,
        symbols=symbols,
        extra={
            "execution_interval": execution_interval,
            "regime_interval": regime_interval,
            "execution_counts": {s: (len(bars_5m[s]) if bars_5m[s] is not None else 0) for s in symbols},
            "regime_counts": {s: (len(bars_4h[s]) if bars_4h[s] is not None else 0) for s in symbols},
        },
    )

    # Stage 2: FEATURES
    execution_features: Dict[str, Dict] = {}
    for symbol in symbols:
        if bars_5m[symbol] is None or bars_5m[symbol].empty:
            continue
        ctx = build_execution_features(symbol, bars_5m[symbol])
        execution_features[symbol] = asdict(ctx)

    # Regime features use anchor symbol (BTC preferred)
    anchor_symbol = "BTC" if "BTC" in symbols else symbols[0]
    if bars_4h.get(anchor_symbol) is None or bars_4h[anchor_symbol].empty:
        reason = f"Regime candles missing for anchor symbol {anchor_symbol}"
        if scope.env.lower() == "live":
            permission.set_block("MARKET_DATA_BLOCKED", reason)
        logger.warning(f"MARKET_DATA_BLOCKED | {reason}")
        return pd.DataFrame()
    regime_ctx = build_regime_features(anchor_symbol, bars_4h[anchor_symbol], correlation_symbols=bars_4h)

    log_pipeline_stage(
        stage="FEATURES_BUILT",
        scope=str(scope),
        run_id=run_id,
        symbols=symbols,
        extra={
            "execution_feature_symbols": list(execution_features.keys()),
            "regime_feature_symbol": anchor_symbol,
        },
    )

    from universe.governance.config import PHASE_G_ENABLED as _phase_g_on
    if _phase_g_on:
        # Phase G: universe is already selected by governance; use as-is
        ordered_symbols = list(symbols)
    else:
        ordered_symbols = get_ai_runner().get_ranked_symbols(symbols)
    max_scanned = int(crypto_config.get("MAX_SYMBOLS_SCANNED_PER_CYCLE", len(ordered_symbols) or 1))
    if max_scanned <= 0:
        max_scanned = len(ordered_symbols)

    primary_block = permission.get_primary_block()
    capacity_blocked = False
    daily_trades = runtime.risk_manager.portfolio.daily_trades_opened

    # Diagnostic logging for capacity check
    logger.info(
        f"CAPACITY_CHECK | daily_trades_opened={daily_trades} | MAX={MAX_TRADES_PER_DAY} | "
        f"open_positions={len([p for ps in runtime.risk_manager.portfolio.open_positions.values() for p in ps])} | "
        f"primary_block={primary_block.state if primary_block else None}"
    )

    if daily_trades >= MAX_TRADES_PER_DAY:
        capacity_blocked = True
        logger.warning(
            f"CAPACITY_BLOCKED | trades_opened={daily_trades} >= MAX={MAX_TRADES_PER_DAY}"
        )
    if primary_block is not None and primary_block.state == "RISK_LIMIT_BLOCKED":
        capacity_blocked = True
        logger.warning(f"RISK_LIMIT_BLOCKED | reason={primary_block.reason}")

    if capacity_blocked:
        scanned_symbols = []
        skipped_symbols = list(ordered_symbols)
    else:
        scanned_symbols = list(ordered_symbols[:max_scanned])
        skipped_symbols = list(ordered_symbols[max_scanned:])

    get_observability().record_scan_metrics(
        ai_ranked_universe_size=len(ordered_symbols),
        ai_scan_coverage_count=len(scanned_symbols),
        skipped_due_to_capacity=len(skipped_symbols),
    )

    if skipped_symbols:
        logger.warning(
            "SIGNAL_SKIPPED_DUE_TO_CAPACITY | count=%s capacity_blocked=%s symbols=%s",
            len(skipped_symbols),
            capacity_blocked,
            ",".join(skipped_symbols),
        )
        log_pipeline_stage(
            stage="SIGNAL_SKIPPED_DUE_TO_CAPACITY",
            scope=str(scope),
            run_id=run_id,
            symbols=skipped_symbols,
            extra={
                "skipped_count": len(skipped_symbols),
                "max_symbols_scanned_per_cycle": max_scanned,
                "capacity_blocked": capacity_blocked,
            },
        )

    # Stage 3: REGIME ENGINE
    thresholds = RegimeThresholds(
        vol_low=float(crypto_config.get("REGIME_VOL_LOW", 30.0)),
        vol_high=float(crypto_config.get("REGIME_VOL_HIGH", 60.0)),
        vol_extreme=float(crypto_config.get("REGIME_VOL_EXTREME", 100.0)),
        trend_pos=float(crypto_config.get("REGIME_TREND_POS", 0.5)),
        trend_neg=float(crypto_config.get("REGIME_TREND_NEG", -0.5)),
        trend_strong_neg=float(crypto_config.get("REGIME_TREND_STRONG_NEG", -2.0)),
        drawdown_mild=float(crypto_config.get("REGIME_DRAWDOWN_MILD", -5.0)),
        drawdown_moderate=float(crypto_config.get("REGIME_DRAWDOWN_MODERATE", -15.0)),
        drawdown_severe=float(crypto_config.get("REGIME_DRAWDOWN_SEVERE", -30.0)),
        hysteresis_count=int(crypto_config.get("REGIME_HYSTERESIS_COUNT", 2)),
    )

    if not hasattr(runtime, "crypto_regime_engine") or runtime.crypto_regime_engine is None:
        runtime.crypto_regime_engine = CryptoRegimeEngine(thresholds=thresholds)

    regime_signal = runtime.crypto_regime_engine.analyze(regime_ctx)

    # Maintain regime history in runtime state
    if not hasattr(runtime, "crypto_state") or runtime.crypto_state is None:
        runtime.crypto_state = {
            "regime_history": [],
            "bars_since_transition": 0,
            "transition_prices": {},
        }
    runtime.crypto_state["regime_history"].append(regime_signal.regime.value)
    runtime.crypto_state["regime_history"] = runtime.crypto_state["regime_history"][-50:]

    # Track PANIC → NEUTRAL transition for recovery strategy
    if regime_signal.regime_changed and regime_signal.previous_regime == MarketRegime.PANIC and regime_signal.regime == MarketRegime.NEUTRAL:
        runtime.crypto_state["bars_since_transition"] = 0
        runtime.crypto_state["transition_prices"] = {
            sym: float(execution_features.get(sym, {}).get("close", 0.0)) for sym in execution_features.keys()
        }
    else:
        runtime.crypto_state["bars_since_transition"] = runtime.crypto_state.get("bars_since_transition", 0) + 1

    log_pipeline_stage(
        stage="REGIME_EVALUATION",
        scope=str(scope),
        run_id=run_id,
        symbols=symbols,
        extra={
            "regime_current": regime_signal.regime.value,
            "regime_previous": regime_signal.previous_regime.value if regime_signal.previous_regime else None,
            "regime_changed": regime_signal.regime_changed,
            "scores": {
                "volatility": regime_signal.volatility,
                "trend": regime_signal.trend_slope,
                "drawdown": regime_signal.drawdown,
            },
            "rationale": regime_signal.rationale,
            "confirmations": regime_signal.confirmations,
        },
    )

    if regime_signal.regime_changed:
        log_pipeline_stage(
            stage="REGIME_TRANSITION",
            scope=str(scope),
            run_id=run_id,
            symbols=symbols,
            extra={
                "from": regime_signal.previous_regime.value if regime_signal.previous_regime else None,
                "to": regime_signal.regime.value,
            },
        )

    # Stage 4: STRATEGY SELECTOR
    selector = CryptoStrategySelector(
        max_concurrent=int(crypto_config.get("MAX_CONCURRENT_STRATEGIES", 2)),
        max_position_count=int(crypto_config.get("STRATEGY_MAX_POSITION_COUNT", 5)),
        max_risk_per_trade=float(crypto_config.get("STRATEGY_MAX_RISK_PER_TRADE", 0.02)),
        allocation_cap_pct=float(crypto_config.get("DEFAULT_STRATEGY_ALLOCATION", 0.5)),
    )

    eligible = selector.get_eligible_strategies(regime_signal.regime)

    # Phase D: Track regime block (hook for observability)
    try:
        eligible_names = [e.value for e in eligible]
        get_observability().on_strategies_selected(eligible_names, regime_signal.regime.value)
    except Exception as e:
        logger.warning(f"PHASE_D_OBSERVABILITY_HOOK_FAILED | error={e}")

    log_pipeline_stage(
        stage="STRATEGIES_ELIGIBLE",
        scope=str(scope),
        run_id=run_id,
        symbols=symbols,
        extra={
            "regime": regime_signal.regime.value,
            "eligible": [e.value for e in eligible],
        },
    )

    available_capital = runtime.risk_manager.portfolio.available_capital
    selected = selector.select_strategies(regime_signal.regime, available_capital)

    log_pipeline_stage(
        stage="STRATEGIES_SELECTED",
        scope=str(scope),
        run_id=run_id,
        symbols=symbols,
        extra={
            "regime": regime_signal.regime.value,
            "selected": [s.strategy_type.value for s in selected],
        },
    )

    # Stage 5: STRATEGY SIGNALS
    signals: List[Dict] = []
    for allocation in selected:
        strategy_name = allocation.strategy_type.value
        strategy = CRYPTO_STRATEGIES.get(strategy_name)
        if strategy is None:
            continue

        for symbol in scanned_symbols:
            if symbol not in execution_features:
                continue

            feature_context = dict(execution_features[symbol])
            feature_context["regime_history"] = runtime.crypto_state.get("regime_history", [])

            transition_prices = runtime.crypto_state.get("transition_prices", {})
            if transition_prices and symbol in transition_prices and transition_prices[symbol] > 0:
                feature_context["recovery_move_pct"] = (
                    (feature_context.get("close", 0) - transition_prices[symbol]) / transition_prices[symbol]
                )
            else:
                feature_context["recovery_move_pct"] = 0.0
            feature_context["bars_since_transition"] = runtime.crypto_state.get("bars_since_transition", 0)

            signal = strategy.generate_signal(
                feature_context=feature_context,
                portfolio_state={},
                budget=allocation.capital_allocation,
                regime_state=regime_signal.regime.value,
            )

            signals.append(
                {
                    "symbol": symbol,
                    "strategy": strategy_name,
                    "intent": signal.intent,
                    "confidence_raw": signal.confidence,
                    "suggested_size": signal.suggested_size,
                    "reason": signal.reason,
                    "close": feature_context.get("close", 0),
                }
            )

    log_pipeline_stage(
        stage="SIGNALS_GENERATED",
        scope=str(scope),
        run_id=run_id,
        symbols=scanned_symbols,
        extra={
            "regime": regime_signal.regime.value,
            "signal_count": len(signals),
            "scan_order": scanned_symbols,
        },
    )

    # Convert to DataFrame for executor (LONG signals only)
    rows = []
    for sig in signals:
        if sig["intent"] != "LONG":
            continue
        confidence = _map_confidence(sig["confidence_raw"])
        rows.append(
            {
                "symbol": sig["symbol"],
                "confidence": confidence,
                "close": sig["close"],
                "strategy": sig["strategy"],
                "intent": sig["intent"],
                "reason": sig["reason"],
            }
        )

    return pd.DataFrame(rows)


def _map_confidence(raw_confidence: float) -> int:
    """Map 0..1 confidence to 1..5 scale."""
    if raw_confidence <= 0:
        return 1
    scaled = int(round(raw_confidence * 4)) + 1
    return max(1, min(5, scaled))


def _validate_timeframe(df: pd.DataFrame, expected_minutes: int, symbol: str, label: str) -> None:
    """
    Validate that candle spacing matches expected timeframe.
    """
    if df is None or df.empty:
        return
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"Candle index must be DatetimeIndex for {symbol} {label}")

    diffs = df.index.to_series().diff().dropna()
    if diffs.empty:
        return
    median_delta = diffs.median()
    expected_delta = timedelta(minutes=expected_minutes)
    tolerance = timedelta(minutes=max(1, expected_minutes * 0.1))

    if abs(median_delta - expected_delta) > tolerance:
        raise ValueError(
            f"Candle timeframe mismatch for {symbol} ({label}): expected {expected_minutes}m, got {median_delta}"
        )
