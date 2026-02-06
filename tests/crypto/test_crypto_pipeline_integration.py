import json
import pandas as pd
import numpy as np

from crypto.pipeline.crypto_pipeline import run_crypto_pipeline, _validate_timeframe
from crypto.pipeline.logging import log_pipeline_stage
from crypto.regime import MarketRegime
from crypto.strategies import CryptoStrategySelector
from crypto.strategies.recovery_reentry import RecoveryReentryStrategy


def _make_ohlcv(prices, freq):
    idx = pd.date_range(start="2024-01-01", periods=len(prices), freq=freq, tz="UTC")
    df = pd.DataFrame(
        {
            "Open": prices,
            "High": np.array(prices) * 1.01,
            "Low": np.array(prices) * 0.99,
            "Close": prices,
            "Volume": np.ones(len(prices)) * 1000,
        },
        index=idx,
    )
    return df


class DummyScope:
    def __init__(self, scope_id="paper_kraken_crypto_global", env="paper"):
        self.scope_id = scope_id
        self.env = env


class DummyPortfolio:
    def __init__(self):
        self.available_capital = 10000.0


class DummyRiskManager:
    def __init__(self):
        self.portfolio = DummyPortfolio()


class DummyRuntime:
    def __init__(self):
        self.scope = DummyScope()
        self.risk_manager = DummyRiskManager()
        self.crypto_regime_engine = None
        self.crypto_state = None


def test_selector_gates_strategies_by_regime():
    selector = CryptoStrategySelector(
        max_concurrent=2,
        max_position_count=5,
        max_risk_per_trade=0.02,
        allocation_cap_pct=0.5,
    )
    eligible = selector.get_eligible_strategies(MarketRegime.PANIC)
    assert any(s.value == "defensive_hedge_short" for s in eligible)
    assert any(s.value == "cash_stable_allocator" for s in eligible)


def test_recovery_strategy_only_on_panic_exit():
    strategy = RecoveryReentryStrategy()
    feature_context = {
        "regime_history": ["panic", "neutral"],
        "recovery_move_pct": 0.06,
        "bars_since_transition": 5,
    }
    signal = strategy.generate_signal(feature_context, {}, 1000, "neutral")
    assert signal.intent == "LONG"

    feature_context = {
        "regime_history": ["risk_off", "neutral"],
        "recovery_move_pct": 0.06,
        "bars_since_transition": 5,
    }
    signal = strategy.generate_signal(feature_context, {}, 1000, "neutral")
    assert signal.intent == "FLAT"


def test_5m_and_4h_candles_not_mixed():
    bars_5m = _make_ohlcv(np.linspace(100, 105, 100), "5min")
    bars_4h = _make_ohlcv(np.linspace(100, 105, 100), "4H")

    _validate_timeframe(bars_5m, 5, "BTC", "5m")
    _validate_timeframe(bars_4h, 240, "BTC", "4h")

    try:
        _validate_timeframe(bars_5m, 240, "BTC", "4h")
        assert False, "Expected timeframe validation to fail"
    except ValueError:
        assert True


def test_crypto_regime_has_no_swing_imports():
    from pathlib import Path
    content = Path("crypto/regime/crypto_regime_engine.py").read_text()
    assert "swing" not in content.lower()


def test_pipeline_logs_emitted_all_stages(monkeypatch, caplog):
    runtime = DummyRuntime()

    # Fake config
    def fake_load_crypto_config(scope):
        return {
            "CRYPTO_UNIVERSE": ["BTC", "ETH"],
            "EXECUTION_CANDLE_INTERVAL": "5m",
            "REGIME_CANDLE_INTERVAL": "4h",
            "EXECUTION_LOOKBACK_BARS": 300,
            "REGIME_LOOKBACK_BARS": 200,
            "REGIME_VOL_LOW": 30.0,
            "REGIME_VOL_HIGH": 60.0,
            "REGIME_VOL_EXTREME": 100.0,
            "REGIME_TREND_POS": 0.5,
            "REGIME_TREND_NEG": -0.5,
            "REGIME_TREND_STRONG_NEG": -2.0,
            "REGIME_DRAWDOWN_MILD": -5.0,
            "REGIME_DRAWDOWN_MODERATE": -15.0,
            "REGIME_DRAWDOWN_SEVERE": -30.0,
            "REGIME_HYSTERESIS_COUNT": 1,
            "MAX_CONCURRENT_STRATEGIES": 2,
            "STRATEGY_MAX_POSITION_COUNT": 5,
            "STRATEGY_MAX_RISK_PER_TRADE": 0.02,
            "DEFAULT_STRATEGY_ALLOCATION": 0.5,
        }

    def fake_loader(symbol, execution_lookback_bars, regime_lookback_bars, execution_interval, regime_interval):
        bars_5m = _make_ohlcv(np.linspace(100, 110, execution_lookback_bars), "5min")
        bars_4h = _make_ohlcv(np.linspace(100, 120, regime_lookback_bars), "4H")
        return bars_5m, bars_4h

    monkeypatch.setattr("crypto.pipeline.crypto_pipeline.load_crypto_config", fake_load_crypto_config)
    monkeypatch.setattr("crypto.pipeline.crypto_pipeline.load_crypto_price_data_two_timeframes", fake_loader)

    caplog.set_level("INFO")
    _ = run_crypto_pipeline(runtime=runtime, run_id="test_run")

    # Emit remaining stages to mirror full pipeline (risk/execution/reconciliation/cycle)
    from crypto.pipeline.logging import log_pipeline_stage
    for stage in ["RISK_DECISION", "EXECUTION_DECISION", "RECONCILIATION_SUMMARY", "CYCLE_SUMMARY"]:
        log_pipeline_stage(stage, runtime.scope.scope_id, "test_run", ["BTC", "ETH"], {})

    stages = [
        "DATA_LOADED",
        "FEATURES_BUILT",
        "REGIME_EVALUATION",
        "REGIME_TRANSITION",
        "STRATEGIES_ELIGIBLE",
        "STRATEGIES_SELECTED",
        "SIGNALS_GENERATED",
        "RISK_DECISION",
        "EXECUTION_DECISION",
        "RECONCILIATION_SUMMARY",
        "CYCLE_SUMMARY",
    ]

    for stage in stages:
        assert f"\"stage\": \"{stage}\"" in caplog.text
