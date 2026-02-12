"""Crypto account reconciliation (Kraken-only)."""

from __future__ import annotations

import logging
from typing import Dict

from broker.adapter import BrokerAdapter
from broker.trade_ledger import TradeLedger
from risk.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class CryptoAccountReconciler:
    """
    Reconcile crypto scope using KrakenAdapter only.

    If adapter does not support reconciliation, run in DRY_RUN and log
    RECONCILIATION_UNAVAILABLE_CRYPTO_ADAPTER_STUB.
    """

    def __init__(self, broker: BrokerAdapter, trade_ledger: TradeLedger, risk_manager: RiskManager):
        self.broker = broker
        self.trade_ledger = trade_ledger
        self.risk_manager = risk_manager
        self.unreconciled_broker_symbols = set()

    def reconcile_on_startup(self) -> Dict:
        logger.info("crypto_reconciliation_start broker=%s", self.broker.__class__.__name__)

        try:
            equity = self.broker.account_equity
            buying_power = self.broker.buying_power
            positions = self.broker.get_positions()

            logger.info(
                "crypto_reconciliation_snapshot equity=%.2f buying_power=%.2f positions=%d",
                float(equity),
                float(buying_power),
                len(positions),
            )

            # Hydrate portfolio.open_positions from broker positions
            self._hydrate_portfolio_positions(positions)

            return {
                "status": "READY",
                "safe_mode": False,
                "warnings": [],
                "errors": [],
                "reconciliation_adapter": self.broker.__class__.__name__,
            }

        except NotImplementedError:
            logger.warning("RECONCILIATION_UNAVAILABLE_CRYPTO_ADAPTER_STUB")
            return {
                "status": "UNKNOWN",
                "safe_mode": True,
                "warnings": ["RECONCILIATION_UNAVAILABLE_CRYPTO_ADAPTER_STUB"],
                "errors": [],
                "reconciliation_adapter": self.broker.__class__.__name__,
            }
        except Exception as e:
            logger.error("crypto_reconciliation_failed error=%s", e)
            return {
                "status": "FAILED",
                "safe_mode": True,
                "warnings": [],
                "errors": [str(e)],
                "reconciliation_adapter": self.broker.__class__.__name__,
            }

    def _hydrate_portfolio_positions(self, positions) -> None:
        """
        Populate risk_manager.portfolio.open_positions from broker positions.

        Without this, the exit evaluator sees an empty portfolio after restart
        and skips all exit evaluations.
        """
        import pandas as pd

        portfolio = self.risk_manager.portfolio
        hydrated = 0

        if not positions or not isinstance(positions, dict):
            return

        for symbol, pos_data in positions.items():
            # Skip if already in portfolio state
            if symbol in portfolio.open_positions and portfolio.open_positions[symbol]:
                continue

            # Extract fields from broker position dict
            if isinstance(pos_data, dict):
                entry_price = float(pos_data.get("entry_price", pos_data.get("cost", 0)))
                qty = float(pos_data.get("vol", pos_data.get("quantity", 0)))
            else:
                entry_price = float(getattr(pos_data, "entry_price", 0))
                qty = float(getattr(pos_data, "quantity", getattr(pos_data, "vol", 0)))

            if qty <= 0:
                continue

            # Resolve entry_date from ledger or fallback
            entry_date = pd.Timestamp.now(tz="UTC")
            if hasattr(self.trade_ledger, "_open_positions"):
                ledger_meta = self.trade_ledger._open_positions.get(symbol, {})
                ts = ledger_meta.get("entry_timestamp")
                if ts:
                    try:
                        entry_date = pd.Timestamp(ts, tz="UTC")
                    except Exception:
                        pass

            portfolio.open_trade(
                symbol=symbol,
                entry_date=entry_date,
                entry_price=entry_price,
                position_size=qty,
                risk_amount=0.0,
                confidence=3,
            )
            hydrated += 1

        if hydrated:
            logger.info(
                "PORTFOLIO_HYDRATED | count=%d | total_positions=%d",
                hydrated,
                sum(len(v) for v in portfolio.open_positions.values()),
            )
