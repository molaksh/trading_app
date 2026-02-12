"""Crypto account reconciliation (Kraken-only)."""

from __future__ import annotations

import logging
from typing import Dict

from broker.adapter import BrokerAdapter
from broker.trade_ledger import TradeLedger
from config.settings import RISK_PER_TRADE, CONFIDENCE_RISK_MULTIPLIER
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

            # Liquidity check (after hydration)
            self._check_and_liquidate(equity, buying_power)

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

            confidence = 3
            portfolio.open_trade(
                symbol=symbol,
                entry_date=entry_date,
                entry_price=entry_price,
                position_size=qty,
                risk_amount=portfolio.current_equity * RISK_PER_TRADE * CONFIDENCE_RISK_MULTIPLIER.get(confidence, 0.75),
                confidence=confidence,
            )

            # Update current price from broker (critical for P&L scoring)
            if isinstance(pos_data, dict):
                current_price = float(pos_data.get("current_price", pos_data.get("mark_price", 0)))
            else:
                current_price = float(getattr(pos_data, "current_price", 0))
            if current_price > 0 and symbol in portfolio.open_positions:
                for open_pos in portfolio.open_positions[symbol]:
                    open_pos.update_price(current_price)

            hydrated += 1

        if hydrated:
            logger.info(
                "PORTFOLIO_HYDRATED | count=%d | total_positions=%d",
                hydrated,
                sum(len(v) for v in portfolio.open_positions.values()),
            )

    def _check_and_liquidate(self, equity: float, buying_power: float) -> None:
        """
        Check for liquidity violations and sell positions if needed.

        Crypto has no PDT concern — all positions are eligible for liquidation.
        """
        import os
        from config.scope import get_scope
        from config.scope_paths import get_scope_path
        from config.settings import CASH_ONLY_TRADING, MAX_PORTFOLIO_HEAT

        portfolio = self.risk_manager.portfolio
        account_equity = float(equity)

        # Use buying_power as proxy for available cash in crypto
        account_cash = float(buying_power)

        # Resolve state_dir for cash reserve persistence
        state_dir = None
        try:
            scope = get_scope()
            state_dir = get_scope_path(scope, "state")
        except Exception:
            pass

        # Load persisted cash reserve (before violation check)
        from risk.liquidity_manager import LiquidityManager
        if state_dir:
            LiquidityManager.load_cash_reserve(state_dir, portfolio)

        # Read manual target
        target_cash = None
        env_target = os.getenv("LIQUIDITY_TARGET_CASH")
        if env_target:
            try:
                target_cash = float(env_target)
            except ValueError:
                pass

        # Quick-check: is there a violation?
        has_negative_cash = CASH_ONLY_TRADING and account_cash < 0
        has_target = target_cash is not None and account_cash < target_cash

        # Check heat
        has_heat_violation = False
        if account_equity > 0:
            total_risk = sum(
                pos.risk_amount
                for positions in portfolio.open_positions.values()
                for pos in positions
            )
            has_heat_violation = (total_risk / account_equity) > MAX_PORTFOLIO_HEAT

        if not (has_negative_cash or has_target or has_heat_violation):
            logger.info(
                "LIQUIDITY_CHECK_OK | cash=%.2f equity=%.2f | no liquidation needed",
                account_cash, account_equity,
            )
            return

        logger.warning(
            "LIQUIDITY_CHECK_TRIGGERED | cash=%.2f equity=%.2f | "
            "negative_cash=%s target=%s heat_violation=%s",
            account_cash, account_equity,
            has_negative_cash, target_cash, has_heat_violation,
        )

        lm = LiquidityManager(
            portfolio_state=portfolio,
            broker=self.broker,
            state_dir=state_dir,
            trade_ledger=self.trade_ledger,
        )
        result = lm.assess_and_liquidate(
            account_cash=account_cash,
            account_equity=account_equity,
            target_cash=target_cash,
        )

        if result.triggered:
            if result.positions_sold:
                logger.info(
                    "LIQUIDITY_RESOLVED: sold %d positions (%s), freed $%.2f",
                    len(result.positions_sold),
                    ", ".join(result.positions_sold),
                    result.cash_freed,
                )
            else:
                logger.warning(
                    "LIQUIDITY_UNRESOLVED: %s, no positions sold (errors: %s)",
                    result.trigger_reason, result.errors,
                )
