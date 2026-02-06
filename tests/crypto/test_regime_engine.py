import numpy as np
import pandas as pd

from crypto.features.regime_features import build_regime_features
from crypto.regime import CryptoRegimeEngine, RegimeThresholds, MarketRegime


def _make_ohlcv(prices, freq="4H"):
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


def test_regime_risk_on_low_vol_uptrend_4h():
    prices = np.linspace(100, 120, 200)
    df = _make_ohlcv(prices)
    ctx = build_regime_features("BTC", df)

    thresholds = RegimeThresholds(
        vol_low=50.0,
        vol_high=80.0,
        vol_extreme=120.0,
        trend_pos=0.1,
        trend_neg=-0.1,
        trend_strong_neg=-1.0,
        drawdown_mild=-5.0,
        drawdown_moderate=-15.0,
        drawdown_severe=-30.0,
        hysteresis_count=1,
    )
    engine = CryptoRegimeEngine(thresholds)
    signal = engine.analyze(ctx)
    assert signal.regime == MarketRegime.RISK_ON


def test_regime_neutral_sideways():
    prices = np.ones(200) * 100
    df = _make_ohlcv(prices)
    ctx = build_regime_features("BTC", df)

    thresholds = RegimeThresholds(
        vol_low=5.0,
        vol_high=50.0,
        vol_extreme=80.0,
        trend_pos=0.2,
        trend_neg=-0.2,
        trend_strong_neg=-1.0,
        drawdown_mild=-2.0,
        drawdown_moderate=-10.0,
        drawdown_severe=-20.0,
        hysteresis_count=1,
    )
    engine = CryptoRegimeEngine(thresholds)
    signal = engine.analyze(ctx)
    assert signal.regime == MarketRegime.NEUTRAL


def test_regime_risk_off_high_vol_downtrend():
    noise = np.sin(np.linspace(0, 10, 200)) * 2
    prices = np.linspace(120, 80, 200) + noise
    df = _make_ohlcv(prices)
    ctx = build_regime_features("BTC", df)

    thresholds = RegimeThresholds(
        vol_low=10.0,
        vol_high=20.0,
        vol_extreme=80.0,
        trend_pos=0.2,
        trend_neg=-0.1,
        trend_strong_neg=-1.0,
        drawdown_mild=-2.0,
        drawdown_moderate=-10.0,
        drawdown_severe=-40.0,  # Increased to 40% so 33% drawdown = RISK_OFF not PANIC
        hysteresis_count=1,
    )
    engine = CryptoRegimeEngine(thresholds)
    signal = engine.analyze(ctx)
    assert signal.regime == MarketRegime.RISK_OFF


def test_regime_panic_crash_4h():
    noise = np.sin(np.linspace(0, 12, 200)) * 5
    prices = np.linspace(120, 60, 200) + noise
    df = _make_ohlcv(prices)
    ctx = build_regime_features("BTC", df)

    thresholds = RegimeThresholds(
        vol_low=10.0,
        vol_high=20.0,
        vol_extreme=100.0,
        trend_pos=0.2,
        trend_neg=-0.2,
        trend_strong_neg=-0.5,
        drawdown_mild=-2.0,
        drawdown_moderate=-10.0,
        drawdown_severe=-25.0,  # Trigger PANIC at 25%+ drawdown
        hysteresis_count=1,
    )
    engine = CryptoRegimeEngine(thresholds)
    signal = engine.analyze(ctx)
    assert signal.regime == MarketRegime.PANIC


def test_regime_hysteresis():
    prices_up = np.linspace(100, 110, 200)
    prices_down = np.linspace(110, 90, 200)

    ctx_up = build_regime_features("BTC", _make_ohlcv(prices_up))
    ctx_down = build_regime_features("BTC", _make_ohlcv(prices_down))

    thresholds = RegimeThresholds(hysteresis_count=2)
    engine = CryptoRegimeEngine(thresholds)

    signal1 = engine.analyze(ctx_up)
    assert signal1.regime in {MarketRegime.RISK_ON, MarketRegime.NEUTRAL}

    signal2 = engine.analyze(ctx_down)
    # Should not switch on first opposing signal
    assert signal2.regime == signal1.regime

    signal3 = engine.analyze(ctx_down)
    assert signal3.regime != signal1.regime
