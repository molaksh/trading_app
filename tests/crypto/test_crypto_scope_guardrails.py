"""Guardrails to prevent crypto scope contamination."""

import json
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs

import pytest

from config.scope import Scope
from config.scope_paths import ScopePathResolver
from crypto.scope_guard import enforce_crypto_scope_guard, validate_crypto_universe_symbols
from core.data.providers.kraken_provider import KrakenMarketDataProvider, KrakenOHLCConfig
from broker.kraken_adapter import KrakenAdapter
from broker.trade_ledger import TradeLedger
from risk.portfolio_state import PortfolioState
from risk.risk_manager import RiskManager
from execution.runtime import reconcile_runtime


def test_crypto_scope_never_uses_yfinance():
    files = [
        "data/crypto_price_loader.py",
        "core/data/providers/kraken_provider.py",
    ]
    for path in files:
        content = open(path, "r", encoding="utf-8").read()
        assert "yfinance" not in content


def test_crypto_scope_rejects_equity_symbols():
    with pytest.raises(ValueError):
        validate_crypto_universe_symbols(["SPY", "QQQ", "IWM"])


def test_crypto_scope_never_instantiates_alpaca(monkeypatch):
    # Provide a detonating Alpaca adapter to ensure it is not used
    class ExplodingAlpaca:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("ALPACA_SHOULD_NOT_BE_INSTANTIATED")

    monkeypatch.setitem(
        __import__("sys").modules,
        "broker.alpaca_adapter",
        SimpleNamespace(AlpacaAdapter=ExplodingAlpaca),
    )

    from broker.broker_factory import get_broker_adapter

    scope = Scope.from_string("paper_kraken_crypto_global")
    broker = get_broker_adapter(scope)
    assert broker.__class__.__name__ == "KrakenAdapter"


def test_kraken_market_data_provider_uses_ohlc_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("PERSISTENCE_ROOT", str(tmp_path))
    scope = Scope.from_string("paper_kraken_crypto_global")
    config = KrakenOHLCConfig(interval="1d", enable_ws=False)
    provider = KrakenMarketDataProvider(scope, config)

    captured = {}

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def read(self):
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=10):
        captured["url"] = req.full_url
        payload = {
            "error": [],
            "result": {
                "XXBTZUSD": [
                    [1700000000, "1", "2", "0.5", "1.5", "1.2", "100", 10]
                ],
                "last": 1700000000,
            },
        }
        return FakeResponse(payload)

    monkeypatch.setattr(
        "core.data.providers.kraken_provider.urlopen",
        fake_urlopen,
    )

    df = provider.fetch_ohlcv("BTC", 1)
    assert df is not None
    parsed = urlparse(captured["url"])
    assert parsed.path.endswith("/0/public/OHLC")
    qs = parse_qs(parsed.query)
    assert qs.get("pair") == ["XXBTZUSD"]


def test_reconciliation_uses_kraken_only(monkeypatch, tmp_path):
    # Ensure alpaca reconciler is not used under crypto scope
    def exploding_reconciler(*args, **kwargs):
        raise RuntimeError("ALPACA_RECONCILIATION_SHOULD_NOT_RUN")

    monkeypatch.setattr("execution.runtime.AccountReconciler", exploding_reconciler)
    monkeypatch.setenv("PERSISTENCE_ROOT", str(tmp_path))
    monkeypatch.setenv("SCOPE", "paper_kraken_crypto_global")

    scope = Scope.from_string("paper_kraken_crypto_global")
    broker = KrakenAdapter(paper_mode=True)
    trade_ledger = TradeLedger()
    risk_manager = RiskManager(PortfolioState(100000))

    class DummyExecutor:
        safe_mode_enabled = False
        startup_status = "UNKNOWN"
        external_symbols = set()

    runtime = SimpleNamespace(
        scope=scope,
        broker=broker,
        trade_ledger=trade_ledger,
        risk_manager=risk_manager,
        executor=DummyExecutor(),
    )

    result = reconcile_runtime(runtime)
    assert result["reconciliation_adapter"] == "KrakenAdapter"


def test_crypto_scope_guard_enforces_provider_and_universe(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSISTENCE_ROOT", str(tmp_path))
    scope = Scope.from_string("paper_kraken_crypto_global")
    broker = KrakenAdapter(paper_mode=True)
    scope_paths = ScopePathResolver(scope)

    summary = enforce_crypto_scope_guard(scope, broker, scope_paths)
    assert summary["market_data_provider"] == "KRAKEN"
    assert set(summary["crypto_universe"]) == {
        "BTC",
        "ETH",
        "SOL",
        "LINK",
        "AVAX",
        "ADA",
        "XRP",
        "DOT",
        "DOGE",
        "LTC",
        "BCH",
    }
