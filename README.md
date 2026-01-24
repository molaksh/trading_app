"""
Trading Screener - ML-Ready Algorithmic Trading Prototype
=========================================================

This is a minimal, rule-based trading screener that:
- Loads daily OHLCV data for 43+ US equities
- Computes explainable technical features
- Assigns confidence scores (1-5) using rule-based logic
- Ranks symbols by confidence
- Displays top candidates for review

NOT INCLUDED (by design):
- No machine learning
- No live trading or broker APIs
- No external TA libraries (only pandas, numpy, scipy)
- No backtesting (screener only)

PROJECT STRUCTURE
=================

trading_app/
├── config/
│   ├── __init__.py
│   └── settings.py          # All configuration constants
├── universe/
│   ├── __init__.py
│   └── symbols.py           # List of symbols to screen
├── data/
│   ├── __init__.py
│   ├── price_loader.py      # Load real data (yfinance)
│   └── synthetic_data.py    # Generate test data (no network)
├── features/
│   ├── __init__.py
│   └── feature_engine.py    # Technical indicator computation
├── scoring/
│   ├── __init__.py
│   └── rule_scorer.py       # Confidence scoring logic
├── main.py                  # Production screener (real data)
├── demo.py                  # Demo screener (synthetic data)
└── requirements.txt         # Python dependencies


QUICK START
===========

1. Install dependencies:
   python3 -m pip install -r requirements.txt

2. Run the demo (no network required):
   python3 demo.py

3. Run the production screener (requires internet):
   python3 main.py


FEATURE SET
===========

Computed per symbol, latest day only:

- close:           Current close price
- sma_20:          20-day simple moving average
- sma_200:         200-day simple moving average
- dist_20sma:      % distance from 20-day SMA
- dist_200sma:     % distance from 200-day SMA
- sma20_slope:     5-day linear slope of SMA20 (trend direction)
- atr_pct:         Average True Range as % of price (volatility)
- vol_ratio:       Current volume / 20-day average volume
- pullback_depth:  % drawdown from 20-day rolling high (momentum)


SCORING RULES
=============

Each candidate receives 0-5 points:

+1 if close > sma_200           (above long-term trend)
+1 if sma20_slope > 0           (short-term momentum positive)
+1 if pullback_depth < 0.05     (shallow pullback = 5%)
+1 if vol_ratio > 1.2           (volume 20% above average)
+1 if atr_pct < 0.03            (volatility < 3% of price)

Final confidence = max(1, min(score, 5))  # Capped at 1-5


CONFIGURATION
=============

All settings in config/settings.py:

START_CAPITAL = 100000          # For future backtesting
LOOKBACK_DAYS = 252             # ~1 trading year
SMA_SHORT = 20                  # Short-term trend
SMA_LONG = 200                  # Long-term trend
ATR_PERIOD = 14                 # Volatility window
VOLUME_LOOKBACK = 20            # Volume average window

THRESHOLD_PULLBACK = 0.05       # 5% pullback threshold
THRESHOLD_VOLUME_RATIO = 1.2    # 20% above average
THRESHOLD_ATR_PCT = 0.03        # 3% volatility threshold

TOP_N_CANDIDATES = 20           # Display top N results


SYMBOLS
=======

43 liquid US equities including:
- ETFs: SPY, QQQ, IWM
- Mega-cap Tech: AAPL, MSFT, GOOGL, NVDA, TSLA
- Finance: JPM, BAC, GS, BRK.B, AXP
- Healthcare: JNJ, UNH, PFE, ABBV, MRK
- Industrials: CAT, BA, XOM, CVX
- Retail/Consumer: AMZN, MCD, SBUX, NKE
- Semiconductors: AMD, INTC, QCOM, NXPI
- Software: ADBE, CRM, ORCL, IBM


DATA SOURCES
============

Production (main.py):
- yfinance: Free, 1-minute limited, no API key required

Testing (demo.py):
- Synthetic data generator: Reproducible, realistic, no network


KEY DESIGN DECISIONS
====================

1. No Lookahead Bias
   - All features computed from current and past data only
   - Rolling windows use only available history
   - Latest row (today) scored for deployment

2. Explainability
   - All features have clear financial meaning
   - Rule scoring is transparent and tunable
   - No black-box models (yet)

3. ML-Ready
   - Features structured for sklearn/xgboost ingestion
   - Config separated for hyperparameter tuning
   - Scoring module easily replaceable with ML

4. Minimal Dependencies
   - pandas, numpy, scipy, matplotlib, yfinance only
   - No TA-lib or pandas-ta (to keep it simple)
   - Pure Python calculations


OUTPUTS
=======

Table format:
Rank | Symbol | Confidence | Dist200SMA | VolRatio | ATRPct

Example:
1      TSLA       5        +24.33%       1.30     1.98%
2      AMZN       5        +18.50%       1.25     2.15%
3      SPY        4        +15.22%       1.10     2.30%


EXTENDING TO ML
===============

To add machine learning:

1. Collect more features in feature_engine.py
2. Add backtest module (compute returns vs rules)
3. Generate labels: (good_returns > threshold) = 1, else 0
4. Train classifier on past data
5. Replace rule_scorer.py with ML scorer
6. Add validation and risk management


TROUBLESHOOTING
===============

Q: "No data for SYMBOL" / yfinance errors
A: Check internet connection. yfinance sometimes fails; retry or use demo.py

Q: Empty results
A: Some symbols may require longer lookback. Check LOOKBACK_DAYS in settings.py

Q: Scores all 1 or all 5
A: Adjust thresholds in scoring/rule_scorer.py

Q: Need different symbols?
A: Edit universe/symbols.py and re-run


FUTURE ENHANCEMENTS
====================

v2 Roadmap:
□ Regime detection (trending vs ranging)
□ Correlation filtering (remove correlated picks)
□ Sector rotation logic
□ Real-time alerts via email/Slack
□ Historical backtest module
□ ML-based scoring (RF, XGBoost, or Neural Network)
□ Risk-adjusted ranking
□ Portfolio optimizer
□ Live trading integration (with paper trading first!)


DISCLAIMER
==========

This is a prototype for education and research.
NOT for live trading without extensive validation.
Past performance ≠ future results.
Always backtest, validate, and paper trade first.

Created: 2026-01-24
Version: 1.0 (Screening only, no trading)
"""
