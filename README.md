# Trading App

Algorithmic trading system for crypto and equities. Phase 0 complete, Phase 1 in development.

**Status**: 
- Phase 0: ✅ Complete (crypto strategies hardened, 24/24 tests)
- Phase 1: ✅ Complete (Kraken REST adapter, 18/18 tests)
- Phase 1.1: ✅ Dry-run safe (DRY_RUN=true by default)
- Phase 1.2: 🔄 Next (canary orders with approval)

**All documentation**: See [DOCUMENTATION.md](DOCUMENTATION.md)

---

## Quick Start

```bash
# Paper trading with crypto strategies
bash run_paper_kraken_crypto.sh

# Run tests
pytest tests/crypto/ -v                          # Phase 0 tests
pytest tests/broker/test_kraken_adapter.py -v   # Phase 1 tests
```

**Safety by Default**:
- DRY_RUN=true (orders blocked)
- ENABLE_LIVE_ORDERS=false (explicit approval required)
- CASH_ONLY_TRADING=true (enforced)

---

**⚠️ This is R&D only. NOT for production live trading.**

**Risk Disclaimer**: Past performance ≠ future results. No guarantee of profitability. Use at own risk.

---

**All documentation**: [DOCUMENTATION.md](DOCUMENTATION.md)
"""
