# Trading Platform - Algorithmic Trading System
## ML-Ready, Multi-Asset, Multi-Strategy Framework

> **Status**: Phase 0 complete (crypto/Kraken strategies hardened) + Phase 1 in development (Kraken REST adapter)  
> **Current**: Paper trading fully functional; live orders gated behind DRY_RUN=false + ENABLE_LIVE_ORDERS=true  
> **Caution**: Live adapter requires explicit preflight checks; never enable without full validation

---

## 🚀 Quick Start

### Running Phase 0 (Crypto Strategies - Paper Only)

```bash
# Paper trading with 6 canonical crypto strategies
bash run_paper_kraken_crypto.sh

# Verify hardening (all 24 Phase 0 tests must pass)
pytest tests/crypto/ -v

# Verify Phase 1 adapter tests (18 new Kraken tests)
pytest tests/broker/test_kraken_adapter.py -v
```

**Phase 0 Status**: Paper mode only, broker is stub/dry-run  
**Phase 1 Status**: REST API client implemented, live orders behind safety flags

**Documentation**:
- [Phase 0 Hardening Report](docs/crypto/kraken/phase0/KRAKEN_PHASE0_HARDENING_REPORT.md) - Complete architecture
- [Hardening Pass Summary](docs/crypto/kraken/phase0/HARDENING_PASS_SUMMARY.md) - Requirements checklist
- [Crypto Quickstart](docs/crypto/QUICKSTART.md) - How to run crypto strategies
- [Testing Guide](docs/crypto/TESTING_GUIDE.md) - Test suite overview

---

## 📋 Phase 0 vs Phase 1 vs Phase 2 Roadmap

### Phase 0: Architecture & Strategy Hardening ✅ COMPLETE

- ✅ 6 canonical crypto strategies registered as first-class units
- ✅ Regime-based gating (RISK_ON, NEUTRAL, RISK_OFF, PANIC)
- ✅ 9-stage pipeline with dependency guards
- ✅ Artifact isolation (crypto ≠ swing roots)
- ✅ Zero wrapper strategy usage (all archived in legacy/)
- ✅ Comprehensive test suite (24/24 passing)
- ✅ Hardening report & verification complete

**Key Constraint**: `CASH_ONLY_TRADING=true` enforced globally (prevents live orders)

### Phase 1: Broker Adapter & Safe Order Placement 🔄 IN DEVELOPMENT

**Core Implementation**:
- ✅ Kraken REST API client (signing, rate limits, retries)
- ✅ KrakenAdapter implementing BrokerAdapter interface
- ✅ Paper trading fully functional with order simulation
- ✅ DRY_RUN enforcement (default true - orders logged, not submitted)
- ✅ Startup preflight checks (credentials, connectivity, auth, permissions)
- ✅ Symbol normalization (internal ↔ Kraken)
- ✅ Request deterministic signing (HMAC-SHA512, testable)
- ✅ 18 new adapter tests (all passing, Phase 0 tests still green)

**Live Order Requirements**:
```bash
# Before enabling live orders, all must be true:
DRY_RUN=false                    # Explicitly disable dry-run mode
ENABLE_LIVE_ORDERS=true          # Explicitly enable live orders
KRAKEN_API_KEY=...               # API credentials present
KRAKEN_API_SECRET=...            # API credentials present
# Preflight checks must pass:
#  - Connectivity to Kraken API
#  - Valid authentication (can query balances)
#  - Correct permissions (can query/create/cancel orders)
#  - Withdraw permissions NOT enabled (code-level guarantee)
```

**Phase 1.1 (Current - Dry-Run Safe)**: 
- REST API read-only complete (balances, positions, orders)
- Dry-run order blocking functional
- Paper trading fully tested

**Phase 1.2 (Next - Canary Orders)**:
- Enable small live orders (after human approval)
- 1-2 manual canary orders on BTC/ETH only
- Full reconciliation & logging
- Rollback capability if issues arise

**Timeline**: Q1 2026

### Phase 2: ML & Advanced Features (Future)

- [ ] Regime prediction model
- [ ] Signal strength scoring
- [ ] Portfolio optimization
- [ ] Multi-asset strategies
- [ ] Backtesting framework

---

## 🪙 CRYPTO STRATEGY ARCHITECTURE (Phase 0)

### Six Canonical Strategies

All strategies are registered as first-class units in `CryptoStrategyRegistry`. No wrappers or adapters in production.

```
core/strategies/crypto/
├── registry.py                    (Strategy discovery & filtering)
├── long_term_trend_follower.py    (Trend Following - 35% allocation)
├── volatility_scaled_swing.py     (Volatility Scaling - 30% allocation)
├── mean_reversion.py              (Mean Reversion - 30% allocation)
├── defensive_hedge_short.py       (Defensive Hedging - 25% allocation)
├── cash_stable_allocator.py       (Cash Safety - 20% allocation)
└── recovery_reentry.py            (Panic Recovery - 25% allocation)
```

### Regime-Based Gating

Each strategy activates only in specific market regimes:

| Regime | Active Strategies | Purpose |
|--------|------------------|---------|
| RISK_ON | TrendFollower, VolatilitySwing | Uptrend capture |
| NEUTRAL | TrendFollower, VolatilitySwing, MeanReversion, Recovery | Balanced trading |
| RISK_OFF | MeanReversion, DefensiveHedge | Drawdown mitigation |
| PANIC | DefensiveHedge, CashStable, Recovery | Capital preservation |

**Max 2 concurrent strategies per cycle** (enforced by selector)

### 9-Stage Pipeline Architecture

```
1. Market Data Ingestion   → Fetch OHLCV for BTC/ETH/...
2. Feature Builder         → Compute technical indicators
3. Regime Engine           → Detect current market regime
4. Strategy Selector       → Choose 0-2 active strategies
5. Strategy Signals        → Generate LONG/SHORT/FLAT signals
6. Global Risk Manager     → Validate position limits, drawdown
7. Execution Engine        → Create limit/market orders
8. Broker Adapter          → (Phase 1) Submit to Kraken
9. Reconciliation & Log    → Record fills, P&L, outcomes
```

**Key Properties**:
- All stages independent (no circular imports)
- RegimeEngine isolated (strategies cannot import it)
- Execution reuses swing framework patterns
- Broker adapter deferred to Phase 1

### Testing & Validation

**Hardening Tests** (Phase 0):
- 9 strategy registration tests
- 4 wrapper elimination tests
- 8 pipeline order tests
- 4 artifact isolation tests

**Total**: 24/24 tests passing ✅

Run tests:
```bash
pytest tests/crypto/ -v
pytest tests/crypto/test_strategy_registration.py -v    # Registry tests
pytest tests/crypto/test_pipeline_order.py -v           # Pipeline tests
pytest tests/crypto/test_artifact_isolation.py -v       # Isolation tests
```

---

## Phase 1: Kraken REST Adapter (Dry-Run Safe)

**Status**: ✅ Implementation complete, 18/18 tests passing

**What's New**:
- Kraken REST API client with HMAC-SHA512 signing
- Full `BrokerAdapter` interface implementation
- Paper trading + live trading with safety gates
- 5-point startup preflight verification
- Configuration-driven safety defaults

**Phase 1.1 (Current - Dry-Run Safe)**:
- Orders logged, not submitted (DRY_RUN=true default)
- Paper trading mode: simulated instant fills
- No credentials required to run tests
- Safe for CI/CD pipeline validation

**Phase 1.2 (Next - Canary Orders)**:
- Requires explicit human approval
- DRY_RUN=false + ENABLE_LIVE_ORDERS=true
- Real orders on Kraken with position limits
- Max notional per order: $500 (configurable)
- Sandbox validation required before enabling

**Kraken Components**:

| Component | File | Purpose |
|-----------|------|---------|
| Signing | `broker/kraken_signing.py` | HMAC-SHA512 deterministic signing |
| HTTP Client | `broker/kraken_client.py` | Rate limiting, retries, connection pooling |
| Adapter | `broker/kraken_adapter.py` | BrokerAdapter implementation |
| Preflight | `broker/kraken_preflight.py` | 5-check startup verification |
| Tests | `tests/broker/test_kraken_adapter.py` | 18 comprehensive tests |

**Safety Guarantees**:

```
┌─────────────────────────────────────────────────────────────┐
│                    DRY_RUN SAFETY GATE                      │
├─────────────────────────────────────────────────────────────┤
│ When DRY_RUN=true (DEFAULT):                                │
│   ✅ Orders rejected with REJECTED status                   │
│   ✅ Reason logged: "DRY_RUN: Order blocked"                │
│   ✅ No HTTP calls to Kraken API                            │
│   ✅ No credentials required                                │
│                                                              │
│ When DRY_RUN=false (REQUIRES APPROVAL):                     │
│   ⚠️  Preflight checks enforce auth/connectivity            │
│   ⚠️  ENABLE_LIVE_ORDERS must be explicitly set             │
│   ⚠️  Only then are real orders submitted                   │
└─────────────────────────────────────────────────────────────┘
```

**Configuration Defaults** (live.kraken.crypto.global.yaml):

```yaml
KRAKEN:
  PHASE_1_SAFETY:
    DRY_RUN: true                          # Block all orders by default
    ENABLE_LIVE_ORDERS: false              # Require explicit approval
    MAX_NOTIONAL_PER_ORDER: 500.0          # Max order size in USD
    SYMBOL_ALLOWLIST: [BTC, ETH, SOL]      # Only these symbols allowed
```

**No Withdrawal Functionality**: Code-level guarantee
- KrakenAdapter implements zero withdrawal methods
- Even with live credentials, withdrawals impossible
- Prevents accidental fund transfers

**Preflight Checks** (run on startup if DRY_RUN=false):
1. **Environment Variables**: KRAKEN_API_KEY, KRAKEN_API_SECRET present
2. **Connectivity**: Public SystemStatus endpoint reachable
3. **Authentication**: Private Balance endpoint responds (correct credentials)
4. **Permissions**: OpenOrders endpoint accessible (query, create, cancel allowed)
5. **Sanity**: Withdrawal not used (documentation only, never called)

Run tests:
```bash
# Phase 1 tests (18 new tests)
pytest tests/broker/test_kraken_adapter.py -v

# Phase 0 + Phase 1 (42 total tests)
pytest tests/crypto/ tests/broker/test_kraken_adapter.py -v

# Specific test classes
pytest tests/broker/test_kraken_adapter.py::TestKrakenSigning -v
pytest tests/broker/test_kraken_adapter.py::TestKrakenAdapter -v
pytest tests/broker/test_kraken_adapter.py::TestPhase0Invariants -v
```

### Important Notes

- ✅ **Phase 0 preserved** - 24/24 hardening tests still passing
- ✅ **Dry-run safe** - Orders blocked by default (DRY_RUN=true)
- ✅ **No withdrawals** - Code-level guarantee, impossible to enable
- ⚠️ **Live trading requires approval** - Explicit env var + human review
- ⚠️ **Preflight verification required** - Aborts startup if credentials invalid
- ✅ **Ready for sandbox testing** - With Kraken API credentials

---

## 🏗️ SWING TRADING ARCHITECTURE (Updated Jan 2026)

The project now includes a modular swing trading strategy framework:

**Five Distinct Trading Philosophies:**
- **Trend Pullback**: Trade shallow pullbacks in confirmed uptrends
- **Momentum Breakout**: Trade strength continuation with volume confirmation  
- **Mean Reversion**: Trade snapbacks within valid uptrends
- **Volatility Squeeze**: Trade volatility expansion after compression
- **Event-Driven**: Trade predictable post-event behavior

**Market-Agnostic Design:**
- Same 5 philosophies work for US equities, Indian equities, and cryptocurrencies
- Strategy container automatically loads appropriate market variant
- No hardcoded assumptions about market hours, lot sizes, or brokers

**Folder Structure:**
```
strategies/
├── us/equity/swing/
│   ├── swing.py                    (US container orchestrator)
│   ├── swing_base.py               (Abstract base class)
│   ├── swing_trend_pullback.py     (Philosophy #1)
│   ├── swing_momentum_breakout.py  (Philosophy #2)
│   ├── swing_mean_reversion.py     (Philosophy #3)
│   ├── swing_volatility_squeeze.py (Philosophy #4)
│   └── swing_event_driven.py       (Philosophy #5)
├── india/equity/swing/             (India-specific variants)
│   └── (same 7 files, India-tuned)
└── swing.py                        (Backward compatibility shim)
```

**Key Features:**
- ✅ Philosophy metadata: Each strategy declares risks, caveats, and edge  
- ✅ Metadata-aware intents: Entry/exit intents include philosophy origin
- ✅ Backward compatible: Old imports still work via shim  
- ✅ Market-specific imports: `from strategies.us.equity.swing.swing import SwingEquityStrategy`
- ✅ ML-ready: Each intent carries philosophy ID, risks, caveats for downstream scoring

**Documentation:**
- [SWING_ARCHITECTURE_REFACTOR.md](SWING_ARCHITECTURE_REFACTOR.md) - Complete architecture design
- [SWING_MIGRATION_GUIDE.md](SWING_MIGRATION_GUIDE.md) - Developer migration guide

---

## SCREENER

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


---

## 📚 Documentation Map

| Document | Purpose | Audience |
|----------|---------|----------|
| [Phase 0 Hardening Report](docs/crypto/kraken/phase0/KRAKEN_PHASE0_HARDENING_REPORT.md) | Complete architecture & verification | Engineers, reviewers |
| [Hardening Pass Summary](docs/crypto/kraken/phase0/HARDENING_PASS_SUMMARY.md) | Requirements checklist & results | QA, stakeholders |
| [Crypto Quickstart](docs/crypto/QUICKSTART.md) | How to run Phase 0 | Developers |
| [Testing Guide](docs/crypto/TESTING_GUIDE.md) | Test suite overview | QA engineers |
| [Legacy README](core/strategies/crypto/legacy/README.md) | Wrapper migration guide | Developers |
| [Archive](docs/archive/) | Old reports & internal tracking | Historical reference |

---

## ⚠️ DISCLAIMER & STATUS

**This is a research & development platform. NOT for production live trading.**

**Current Status**:
- Phase 0: ✅ Complete (hardened strategy architecture, paper trading only)
- Phase 1: ✅ Complete (Kraken REST adapter, DRY_RUN safe)
- Phase 1.1: ✅ Complete (dry-run default, 18/18 tests passing)
- Phase 1.2: 🔄 Next (canary live orders, requires human approval)
- Enforcement: `CASH_ONLY_TRADING=true` + `DRY_RUN=true` (default safe)

**Broker Adapter Status**:
- ❌ NOT functional for live orders until Phase 1 complete
- Stub mode: Dry-run order simulation only
- Kraken REST API integration deferred to Phase 1

**Safety Requirements**:
1. All strategies paper-trade in dry-run mode by default
2. Zero live orders without explicit Phase 1 approval
3. Comprehensive testing required before each release
4. Risk limits enforced at multiple pipeline stages
5. Always validate extensively before production deployment

**Risk Disclaimer**:
- Past performance ≠ future results
- No guarantee of profitability
- Use at own risk with proper risk management
- Not suitable for inexperienced traders

---

**Last Updated**: February 5, 2026  
**Version**: 1.1 (Phase 0 complete, Phase 1 in development)  
**Branch**: feature/crypto-kraken-global  
**Status**: Research/Development (Not for production use without full Phase 1 validation)
"""
