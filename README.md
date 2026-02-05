# Trading App

Algorithmic trading system for crypto and equities. Phase 0 complete, Phase 1 in development.

**Status**: 
- Phase 0: ✅ Complete (crypto strategies hardened, 24/24 tests)
- Phase 1: ✅ Complete (Kraken REST adapter, 18/18 tests)
- Phase 1.1: ✅ Dry-run safe (DRY_RUN=true by default)
- Phase 1.2: ✅ 24/7 Daemon (crypto scheduler with persistent state)

**All documentation**: See [DOCUMENTATION.md](DOCUMENTATION.md)

---

## Quick Start

### Crypto 24/7 Daemon (New: Continuous with Downtime Window)

```bash
# Paper crypto: run as 24/7 daemon with daily ML downtime
python crypto_main.py

# Via Docker:
bash run_paper_kraken_crypto.sh

# View scheduler configuration:
python crypto_main.py --help-config

# Custom downtime window (03:00-05:00 UTC by default):
docker run \
  -e CRYPTO_DOWNTIME_START_UTC="03:00" \
  -e CRYPTO_DOWNTIME_END_UTC="05:00" \
  -e CRYPTO_SCHEDULER_TICK_SECONDS=60 \
  -v /data/artifacts/crypto:/app/persist \
  trading-app python crypto_main.py
```

### Batch Mode (Legacy: One execution, then exit)

```bash
# Paper trading with crypto strategies (single run):
python main.py
bash run_paper_kraken_crypto.sh
```

### Swing Trading (Separate Daemon)

```bash
# US equities swing trading (24/5, continuous):
bash run_us_paper_swing.sh
```

---

## Crypto Scheduler Architecture

The crypto system now runs as a **daemon** (24/7 continuous), not batch mode.

**Key Features**:
- ✅ **Continuous operation**: Runs forever until Ctrl+C or container stop
- ✅ **Persistent state**: Tasks don't rerun after container restart
- ✅ **Daily downtime window** (UTC): ML training/validation, trading paused
- ✅ **Crypto-only isolation**: State file cannot be contaminated with swing paths
- ✅ **Configurable cadence**: Adjust trading/monitoring intervals via environment

**Default Downtime**: 03:00-05:00 UTC
- Trading blocked during downtime
- ML training runs only during downtime (paper only)
- Trading resumes at 05:00 UTC

**State File Location**:
```
/data/artifacts/crypto/kraken_global/state/crypto_scheduler_state.json
(NOT under swing scheduler roots - zero contamination enforced at startup)
```

**Scheduler Tasks**:
- `trading_tick`: Run trading pipeline every 1 minute (outside downtime)
- `monitor`: Check exits every 15 minutes (anytime)
- `ml_training`: Daily ML training (downtime only, paper only)
- `reconciliation`: Account reconciliation every 60 minutes

---

## Tests

```bash
# Run all crypto tests:
pytest tests/crypto/ -v

# Run scheduler-specific tests (mandatory tests for daemon behavior):
pytest tests/crypto/test_crypto_scheduler.py -v        # State persistence, downtime, daily tasks, crypto-only
pytest tests/crypto/test_downtime_scheduler.py -v      # Downtime window logic

# Run Kraken adapter tests:
pytest tests/broker/test_kraken_adapter.py -v
```

**Mandatory Test Coverage**:
- ✅ A) `test_crypto_scheduler_persists_state`: State survives restarts
- ✅ B) `test_crypto_downtime_blocks_trading_allows_ml`: Downtime enforcement
- ✅ C) `test_crypto_outside_downtime_allows_trading_blocks_ml`: Trading window
- ✅ D) `test_crypto_daily_task_runs_once_per_day_even_after_restart`: Daily idempotency
- ✅ E) `test_scheduler_state_is_crypto_only`: Zero swing contamination

---

**Safety by Default**:
- DRY_RUN=true (orders blocked)
- ENABLE_LIVE_ORDERS=false (explicit approval required)
- CASH_ONLY_TRADING=true (enforced)
- Crypto scheduler state isolated from swing scheduler (contamination check at startup)

---

**⚠️ This is R&D only. NOT for production live trading.**

**Risk Disclaimer**: Past performance ≠ future results. No guarantee of profitability. Use at own risk.

---

**All documentation**: [DOCUMENTATION.md](DOCUMENTATION.md)
"""
