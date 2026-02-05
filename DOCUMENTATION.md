# Repository Documentation (Single Source of Truth)

*Last updated: 2026-02-05*

---

## 🔔 Latest Updates (Newest First)

### 2026-02-05 — Phase 1: Kraken REST Adapter Implementation Complete

**Scope**: Phase 1 / Broker Adapter  
**Audience**: Engineer / Deployment  

**Status**: ✅ Complete — All 18 tests passing, zero Phase 0 regressions

#### Summary

Phase 1 implements a production-ready Kraken REST adapter with strict safety-first design. All orders are blocked by default (DRY_RUN=true) with explicit opt-in required for live trading.

#### Implementation

**New Modules** (4):
- `broker/kraken_signing.py` (175 lines) - HMAC-SHA512 deterministic signing per Kraken spec
- `broker/kraken_client.py` (295 lines) - REST HTTP client with rate limiting (3 req/sec), connection pooling, exponential backoff
- `broker/kraken_adapter.py` (630 lines) - Full BrokerAdapter interface (paper + live modes)
- `broker/kraken_preflight.py` (195 lines) - 5-check startup verification (env vars, connectivity, auth, permissions, sanity)

**Modified Modules** (4):
- `broker/broker_factory.py` - Kraken routing, DRY_RUN/ENABLE_LIVE_ORDERS env var reading, preflight integration
- `execution/runtime.py` - Preflight check hook after broker instantiation
- `config/crypto/live.kraken.crypto.global.yaml` - Phase 1 safety section (DRY_RUN=true, ENABLE_LIVE_ORDERS=false defaults)
- `README.md` - Phase 1 documentation and safety guarantees

**New Test File** (18 tests):
- `tests/broker/test_kraken_adapter.py` - Comprehensive Kraken adapter testing

#### Safety Architecture

**Dual Safety Gates**:
1. **DRY_RUN=true** (default) - Blocks all orders with logging
2. **ENABLE_LIVE_ORDERS=false** (default) - Requires explicit opt-in before live orders allowed

**Code-Level Guarantees**:
- No withdrawal methods exist (impossible to enable)
- Preflight verification aborts startup if credentials/connectivity invalid
- Symbol validation (BTC, ETH, SOL allowed)
- Min order size enforcement per symbol
- CASH_ONLY_TRADING=true preserved from Phase 0

**Startup Verification** (5 checks, live mode only):
1. Environment variables present (KRAKEN_API_KEY, KRAKEN_API_SECRET)
2. Connectivity (public SystemStatus endpoint reachable)
3. Authentication (private Balance endpoint responds)
4. Permissions (OpenOrders endpoint accessible)
5. Sanity (withdrawal not used)

#### Configuration Defaults

```yaml
KRAKEN:
  PHASE_1_SAFETY:
    DRY_RUN: true                      # Block all orders by default
    ENABLE_LIVE_ORDERS: false          # Require explicit approval
    MAX_NOTIONAL_PER_ORDER: 500.0      # Prevent large orders
    SYMBOL_ALLOWLIST: [BTC, ETH, SOL]  # Only safe symbols
```

#### Test Results

- Phase 1 tests: **18/18 PASSING**
- Phase 0 regression: **24/24 PASSING** (zero regressions)
- **Total: 42/42 PASSING**

#### Git Commit

- **Commit**: f3b55df
- **Branch**: feature/crypto-kraken-global
- **Date**: Feb 5, 2026

#### Phase Roadmap

- **Phase 1.1** (Current): Dry-run safe, read-only + simulated orders
- **Phase 1.2** (Next): Canary live orders (requires human approval + sandbox validation)
- **Phase 2** (Future): WebSocket market data, advanced order types

---

### 2026-02-05 — Documentation & Hygiene Pass Complete

**Scope**: Repository / Documentation  
**Audience**: Internal / Maintenance  

**Status**: ✅ Complete — All docs organized, no trading logic changes

#### Summary

Comprehensive documentation reorganization and repository hygiene pass after Phase 0 hardening completion. All internal development docs archived, public-facing docs restructured for clarity.

#### Documentation Structure

**Public Documentation**:
- `docs/crypto/kraken/phase0/HARDENING_PASS_SUMMARY.md` - Requirements checklist (Phase 0)
- `docs/crypto/kraken/phase0/KRAKEN_PHASE0_HARDENING_REPORT.md` - Technical architecture
- `docs/crypto/QUICKSTART.md` - How to run crypto strategies
- `docs/crypto/TESTING_GUIDE.md` - Test suite overview

**Internal/Archive Documentation**:
- `docs/archive/internal/` - All development notes (10 files):
  - CRYPTO_COMPLETION_REPORT.md
  - CRYPTO_DEPLOYMENT_CHECKLIST.md
  - CRYPTO_IMPLEMENTATION_SUMMARY.md
  - CRYPTO_README_old.md
  - DELIVERY_SUMMARY.md
  - DOCUMENTATION_INDEX.md
  - KRAKEN_FIXES_LOG.md
  - PROGRESS_CHECKPOINT_2026.md
  - PROJECT_CLEANUP_REPORT.md
  - SESSION_SUMMARY_FINAL.md
  - SCALE_IN_SUMMARY.md

**Code-Specific Documentation**:
- `core/strategies/crypto/legacy/README.md` - Legacy wrapper strategy info
- `scripts/README.md` - Script reference

#### Key Changes

- Created dedicated Phase 0 documentation directory
- Archived all internal session/tracking docs
- Updated README.md with Phase 0/1 clarity
- Added CI hygiene guard script (`.github/hooks/prevent-doc-sprawl.sh`)
- All 24 Phase 0 tests still passing (zero regressions)

#### CI Hygiene Guard

Added `.github/hooks/prevent-doc-sprawl.sh` to enforce:
- Prevent new `.md` files except DOCUMENTATION.md
- Validate documentation structure
- Catch drift before commits

---

## 📚 Historical Record (Older Entries Below)

### 2026-01 — Phase 0: Crypto Strategy Hardening Complete

**Scope**: Phase 0 / Crypto Strategies  
**Audience**: Engineer / Deployment  

**Status**: ✅ Complete — 24/24 tests passing

#### Summary

Phase 0 hardened the crypto strategy architecture, eliminating wrapper strategies and enforcing strict isolation/dependency guards. Foundation established for Phase 1 broker integration.

#### Key Achievements

- ✅ 6 canonical crypto strategies registered as first-class units
- ✅ Regime-based gating (RISK_ON, NEUTRAL, RISK_OFF, PANIC)
- ✅ 9-stage pipeline with dependency guards
- ✅ Artifact isolation (crypto ≠ swing roots)
- ✅ Zero wrapper strategy usage (all archived in legacy/)
- ✅ Comprehensive test suite (24/24 passing):
  - Strategy registration (9 tests)
  - Wrapper elimination (4 tests)
  - Pipeline order (8 tests)
  - Dependency guards (3 tests)

#### Safety Enforcement

- **CASH_ONLY_TRADING=true** enforced globally
- Paper trading only (no live order capability)
- Broker adapter stub (DRY_RUN mode)
- Strategy cannot import execution logic

#### Test Commands

```bash
# Run all Phase 0 tests
pytest tests/crypto/test_strategy_registration.py tests/crypto/test_pipeline_order.py -v

# Run specific test class
pytest tests/crypto/test_strategy_registration.py::TestCryptoStrategyRegistration -v
```

#### Git References

- Archive commit: 52c0d04 - "Hardening: Verify zero wrapper usage, enforce pipeline order, validate artifact isolation"
- Branch: main (integrated)

---

### 2025-12 — Swing Trading Architecture Refactor

**Scope**: Strategy Framework / Architecture  
**Audience**: Developer / Maintenance  

**Status**: Complete — Market-agnostic strategy framework established

#### Summary

Refactored swing trading strategies into market-agnostic design. Same 5 philosophies (Trend Pullback, Momentum Breakout, Mean Reversion, Volatility Squeeze, Event-Driven) work across US equities, Indian equities, and crypto.

#### Folder Structure

```
strategies/
├── us/equity/swing/
│   ├── swing.py (US container orchestrator)
│   ├── swing_base.py (Abstract base)
│   ├── swing_trend_pullback.py
│   ├── swing_momentum_breakout.py
│   ├── swing_mean_reversion.py
│   ├── swing_volatility_squeeze.py
│   └── swing_event_driven.py
├── india/equity/swing/
│   └── (same 7 files, India-tuned)
└── swing.py (Backward compatibility shim)
```

#### Key Features

- ✅ Philosophy metadata (risks, caveats, edge cases)
- ✅ Metadata-aware intents (entry/exit include philosophy origin)
- ✅ Backward compatible imports
- ✅ Market-specific variants
- ✅ ML-ready intent structure

#### Documentation

- [SWING_ARCHITECTURE_REFACTOR.md](archive/temp_scripts/SWING_ARCHITECTURE_REFACTOR.md) - Architecture design
- [SWING_MIGRATION_GUIDE.md](archive/temp_scripts/SWING_MIGRATION_GUIDE.md) - Developer migration guide

---

### 2025-11 — Screener: Rule-Based US Equities Filtering

**Scope**: Screener Tool / Feature Development  
**Audience**: User  

**Status**: Complete — Minimal, explainable screener

#### Summary

Minimal rule-based screener for 43+ US equities. Computes technical features, assigns confidence scores (1-5) using transparent logic, ranks symbols without ML.

#### Features

- Loads daily OHLCV data (yfinance)
- Computes 9 technical indicators (SMA, ATR, pullback depth, volume ratio)
- Assigns confidence via rule-based scoring (transparent, tunable)
- Ranks and displays top 20 candidates
- Demo mode (synthetic data, no network required)
- Production mode (real data, yfinance)

#### Scoring Rules

```
+1 if close > SMA_200 (above long-term trend)
+1 if SMA20_slope > 0 (short-term momentum positive)
+1 if pullback_depth < 5% (shallow pullback)
+1 if vol_ratio > 1.2 (volume 20% above average)
+1 if atr_pct < 3% (volatility < 3% of price)
→ Final confidence = max(1, min(score, 5))
```

#### Test & Run

```bash
# Demo (synthetic data)
python3 demo.py

# Production (real data)
python3 main.py
```

#### Symbols Included

43 liquid US equities: SPY, QQQ, IWM (ETFs); AAPL, MSFT, GOOGL, NVDA, TSLA (mega-cap tech); JPM, BAC, GS, BRK.B, AXP (finance); JNJ, UNH, PFE, ABBV, MRK (healthcare); and more.

---

## 🧭 Quick Reference

### Running Tests

```bash
# All Phase 0 tests
pytest tests/crypto/test_strategy_registration.py tests/crypto/test_pipeline_order.py -v

# All Phase 1 tests
pytest tests/broker/test_kraken_adapter.py -v

# Combined (42 total)
pytest tests/crypto/test_strategy_registration.py tests/crypto/test_pipeline_order.py tests/broker/test_kraken_adapter.py -v
```

### Running Paper Trading

```bash
# Phase 0 crypto strategies (paper only)
bash run_paper_kraken_crypto.sh

# Requires DRY_RUN=false to proceed past preflight (Phase 1.2+)
```

### Key Configuration Files

- `config/crypto/live.kraken.crypto.global.yaml` - Phase 1 safety settings (DRY_RUN, ENABLE_LIVE_ORDERS)
- `config/crypto/regime_definitions.yaml` - Regime thresholds
- `config/crypto/strategy_allocation.yaml` - Strategy weights per regime

### Key Code Locations

**Crypto Strategies**:
- `core/strategies/crypto/` - 6 canonical crypto strategies
- `core/strategies/crypto/legacy/` - Archived wrapper strategies

**Broker Adapter** (Phase 1):
- `broker/kraken_signing.py` - HMAC signing
- `broker/kraken_client.py` - REST client
- `broker/kraken_adapter.py` - BrokerAdapter implementation
- `broker/kraken_preflight.py` - Startup verification

**Tests**:
- `tests/crypto/` - Phase 0 hardening tests (24 tests)
- `tests/broker/test_kraken_adapter.py` - Phase 1 adapter tests (18 tests)

---

*This file is the single source of truth for all repository documentation. All new entries are prepended to the top under "Latest Updates". Historical entries are preserved below in chronological order.*
