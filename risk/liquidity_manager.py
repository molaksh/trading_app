"""
Autonomous position liquidation to restore account health.

Detects cash violations, excessive portfolio heat, or manual cash targets,
then sells lowest-priority positions (via PositionHealthScorer) until resolved.
Sets a cash reserve to prevent immediate redeployment of freed capital.

Called during startup reconciliation, after portfolio hydration.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

from config.scope import get_scope
from config.settings import CASH_ONLY_TRADING, MAX_PORTFOLIO_HEAT
from risk.position_health import PositionHealthScorer, ScoredPosition
from risk.portfolio_state import PortfolioState, OpenPosition

logger = logging.getLogger(__name__)


@dataclass
class CashReserve:
    """Cash reserved after liquidation to prevent immediate redeployment."""
    amount: float
    set_date: date
    expiry_date: date
    reason: str

    def is_active(self, today: Optional[date] = None) -> bool:
        if today is None:
            today = date.today()
        return today <= self.expiry_date and self.amount > 0

    def get_reserved_amount(self, today: Optional[date] = None) -> float:
        if self.is_active(today):
            return self.amount
        return 0.0

    def to_dict(self) -> dict:
        return {
            "amount": self.amount,
            "set_date": self.set_date.isoformat(),
            "expiry_date": self.expiry_date.isoformat(),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CashReserve":
        return cls(
            amount=data["amount"],
            set_date=date.fromisoformat(data["set_date"]),
            expiry_date=date.fromisoformat(data["expiry_date"]),
            reason=data["reason"],
        )


@dataclass
class LiquidationResult:
    """Result of a liquidation assessment."""
    triggered: bool
    trigger_reason: str
    violations_detected: List[str] = field(default_factory=list)
    positions_sold: List[str] = field(default_factory=list)
    positions_skipped_pdt: List[str] = field(default_factory=list)
    cash_before: float = 0.0
    cash_after: float = 0.0
    cash_freed: float = 0.0
    heat_before: float = 0.0
    heat_after: float = 0.0
    positions_evaluated: int = 0
    cash_reserve_set: Optional[CashReserve] = None
    errors: List[str] = field(default_factory=list)


class LiquidityManager:
    """
    Autonomous position liquidation manager.

    Called during startup reconciliation to sell positions and restore
    account health when cash is negative, heat exceeds limits, or a
    manual cash target is set.
    """

    def __init__(
        self,
        portfolio_state: PortfolioState,
        broker,
        cash_reserve_days: Optional[int] = None,
        state_dir: Optional[Path] = None,
        trade_ledger=None,
    ):
        self.portfolio = portfolio_state
        self.broker = broker
        self.scorer = PositionHealthScorer()
        self.state_dir = state_dir
        self.trade_ledger = trade_ledger

        # Determine scope for PDT filtering
        try:
            self.scope = get_scope()
        except Exception:
            self.scope = None

        # Reserve days: env var > constructor arg > default 3
        if cash_reserve_days is not None:
            self.reserve_days = cash_reserve_days
        else:
            self.reserve_days = int(os.getenv("LIQUIDITY_RESERVE_DAYS", "3"))

        # Stored after assess_and_liquidate for use in trade records
        self._trigger_reason = ""

    def assess_and_liquidate(
        self,
        account_cash: float,
        account_equity: float,
        target_cash: Optional[float] = None,
    ) -> LiquidationResult:
        """
        Assess account health and liquidate positions if needed.

        Args:
            account_cash: Current account cash from broker
            account_equity: Current account equity from broker
            target_cash: Optional manual cash target override

        Returns:
            LiquidationResult with full audit trail
        """
        mode = self.scope.mode if self.scope else "swing"

        # No-op for daytrade mode (positions close EOD)
        if mode == "daytrade":
            logger.info("LIQUIDITY_NOOP | mode=daytrade | positions close EOD")
            return LiquidationResult(
                triggered=False,
                trigger_reason="daytrade mode - positions close EOD",
            )

        # Detect ALL violations, use largest deficit
        deficit, trigger_reason, all_violations = self._detect_violations(
            account_cash, account_equity, target_cash
        )

        if deficit <= 0:
            logger.info(
                "LIQUIDITY_OK | cash=%.2f equity=%.2f | no violation detected",
                account_cash, account_equity,
            )
            return LiquidationResult(
                triggered=False,
                trigger_reason="no violation",
            )

        self._trigger_reason = trigger_reason

        # Log every detected violation
        logger.warning(
            "LIQUIDITY_VIOLATIONS_DETECTED | count=%d | governing_deficit=$%.2f",
            len(all_violations), deficit,
        )
        for i, v in enumerate(all_violations, 1):
            logger.warning("  VIOLATION %d: %s", i, v)
        logger.warning(
            "LIQUIDITY_GOVERNING | reason=%s | deficit=$%.2f | cash=%.2f equity=%.2f",
            trigger_reason, deficit, account_cash, account_equity,
        )

        # Compute heat before
        heat_before = self._compute_heat(account_equity)

        # Gather all open positions into flat list
        all_positions: List[OpenPosition] = []
        for positions in self.portfolio.open_positions.values():
            all_positions.extend(positions)

        if not all_positions:
            logger.warning("LIQUIDITY_NO_POSITIONS | no positions to liquidate")
            return LiquidationResult(
                triggered=True,
                trigger_reason=trigger_reason,
                errors=["No open positions available for liquidation"],
            )

        # Score positions
        today = pd.Timestamp.now(tz="UTC")
        scored = self.scorer.score_positions(all_positions, today)

        # Filter PDT-ineligible positions
        eligible, skipped_pdt = self._filter_pdt(scored, today, mode)

        # Log scoring table
        self._log_scoring_table(scored, eligible, skipped_pdt)

        # Sell loop
        result = LiquidationResult(
            triggered=True,
            trigger_reason=trigger_reason,
            violations_detected=all_violations,
            cash_before=account_cash,
            heat_before=heat_before,
            positions_evaluated=len(scored),
            positions_skipped_pdt=[s.symbol for s in skipped_pdt],
        )

        # Fix #2: Dynamic violation recheck after each sell.
        # Instead of comparing deficit (risk units) against cash_freed (notional),
        # recheck all violations with updated portfolio state after each sell.
        cash_freed = 0.0
        running_cash = account_cash
        for sp in eligible:
            # Recheck violations with updated portfolio + running cash
            remaining_deficit, _, _ = self._detect_violations(
                running_cash, account_equity, target_cash
            )
            if remaining_deficit <= 0:
                break

            success = self._sell_position(sp, result)
            if success:
                running_cash += sp.notional_value
                cash_freed += sp.notional_value
                result.positions_sold.append(sp.symbol)
                logger.info(
                    "LIQUIDATING | %s | score=%.1f | notional=$%.2f | "
                    "pnl=%.2f%% | freed_so_far=$%.2f | remaining_deficit=$%.2f",
                    sp.symbol, sp.score, sp.notional_value,
                    sp.unrealized_pnl_pct, cash_freed, remaining_deficit,
                )

        result.cash_freed = cash_freed
        result.cash_after = account_cash + cash_freed

        # Set cash reserve
        if cash_freed > 0:
            today_date = date.today()
            reserve = CashReserve(
                amount=cash_freed,
                set_date=today_date,
                expiry_date=today_date + timedelta(days=self.reserve_days),
                reason=trigger_reason,
            )
            self.portfolio.cash_reserve = reserve
            result.cash_reserve_set = reserve
            logger.info(
                "CASH_RESERVE_SET | amount=$%.2f | expires=%s | days=%d | reason=%s",
                reserve.amount, reserve.expiry_date, self.reserve_days, trigger_reason,
            )

            # Fix #3: Persist cash reserve to disk
            if self.state_dir:
                self._save_cash_reserve(reserve)

        # Compute heat after
        result.heat_after = self._compute_heat(account_equity)

        # Log summary
        self._log_summary(result)

        return result

    def _detect_violations(
        self,
        account_cash: float,
        account_equity: float,
        target_cash: Optional[float],
    ) -> tuple:
        """
        Detect ALL liquidity violations and return the largest deficit.

        Evaluates every violation type independently so that the sell loop
        covers the worst case (e.g. heat deficit >> cash deficit).

        Returns:
            (max_deficit, primary_reason, all_violations_list)
        """
        violations = []  # list of (deficit, reason)

        # 1. Manual target (env var or argument)
        env_target = os.getenv("LIQUIDITY_TARGET_CASH")
        effective_target = target_cash
        if env_target is not None and effective_target is None:
            try:
                effective_target = float(env_target)
            except ValueError:
                logger.warning(
                    "Invalid LIQUIDITY_TARGET_CASH=%s, ignoring", env_target
                )

        if effective_target is not None and account_cash < effective_target:
            deficit = effective_target - account_cash
            violations.append((
                deficit,
                f"manual_target (target=${effective_target:.2f}, cash=${account_cash:.2f}, deficit=${deficit:.2f})"
            ))

        # 2. Negative cash (cash-only enforcement)
        if CASH_ONLY_TRADING and account_cash < 0:
            buffer = abs(account_cash) * 0.01  # 1% buffer
            deficit = abs(account_cash) + buffer
            violations.append((
                deficit,
                f"negative_cash (cash=${account_cash:.2f}, deficit=${deficit:.2f})"
            ))

        # 3. Heat exceeded
        if account_equity > 0:
            total_risk = sum(
                pos.risk_amount
                for positions in self.portfolio.open_positions.values()
                for pos in positions
            )
            heat = total_risk / account_equity
            if heat > MAX_PORTFOLIO_HEAT:
                excess_risk = total_risk - (account_equity * MAX_PORTFOLIO_HEAT)
                violations.append((
                    excess_risk,
                    f"heat_exceeded (heat={heat:.2%}, max={MAX_PORTFOLIO_HEAT:.2%}, "
                    f"total_risk=${total_risk:,.2f}, allowed=${account_equity * MAX_PORTFOLIO_HEAT:,.2f}, "
                    f"excess=${excess_risk:,.2f})"
                ))

        if not violations:
            return 0.0, "", []

        # Use the largest deficit as the governing constraint
        violations.sort(key=lambda v: v[0], reverse=True)
        max_deficit, primary_reason = violations[0]

        return max_deficit, primary_reason, [v[1] for v in violations]

    def _filter_pdt(
        self,
        scored: List[ScoredPosition],
        today: pd.Timestamp,
        mode: str,
    ) -> tuple:
        """
        Filter out PDT-ineligible positions.

        Swing mode: skip positions entered today (selling same-day = day trade).
        Crypto mode: all eligible (no PDT rules).

        Returns:
            (eligible, skipped_pdt) lists
        """
        if mode == "crypto":
            return scored, []

        today_date = today.date()
        eligible = []
        skipped = []

        for sp in scored:
            entry_date = sp.entry_date
            if hasattr(entry_date, "date"):
                entry_date = entry_date.date()

            if entry_date == today_date:
                logger.info(
                    "PDT_FILTER | %s | entry_date=%s == today | skipped",
                    sp.symbol, entry_date,
                )
                skipped.append(sp)
            else:
                eligible.append(sp)

        return eligible, skipped

    def _sell_position(self, sp: ScoredPosition, result: LiquidationResult) -> bool:
        """
        Sell a single position via broker.close_position() and update portfolio state.

        Returns True if successful.
        """
        try:
            logger.info(
                "LIQUIDATION_ORDER_SUBMIT | %s | qty=%.6f | notional=$%.2f | "
                "entry=$%.2f | current=$%.2f",
                sp.symbol, sp.position_size, sp.notional_value,
                sp.entry_price, sp.current_price,
            )

            order_result = self.broker.close_position(sp.symbol)

            logger.info(
                "LIQUIDATION_ORDER_RESULT | %s | order_id=%s | status=%s | "
                "filled_qty=%.6f | filled_price=%s | side=%s",
                sp.symbol,
                order_result.order_id,
                order_result.status.value,
                order_result.filled_qty,
                f"${order_result.filled_price:.4f}" if order_result.filled_price else "None",
                order_result.side,
            )

            # Fix #4: Distinguish filled vs pending orders
            if order_result.is_filled():
                exit_price = order_result.filled_price or sp.current_price
                logger.info(
                    "LIQUIDATION_FILLED | %s | exit_price=$%.4f | order_id=%s",
                    sp.symbol, exit_price, order_result.order_id,
                )
            elif order_result.is_pending():
                exit_price = sp.current_price  # estimate
                logger.warning(
                    "LIQUIDATION_PENDING | %s | estimated_price=$%.4f | order_id=%s | "
                    "order is pending, not yet filled",
                    sp.symbol, exit_price, order_result.order_id,
                )
            else:
                error_msg = (
                    f"Order not filled for {sp.symbol}: "
                    f"status={order_result.status.value}, "
                    f"reason={order_result.rejection_reason}"
                )
                logger.error("LIQUIDATION_FAILED | %s", error_msg)
                result.errors.append(error_msg)
                return False

            # Update portfolio state
            self.portfolio.close_trade(
                symbol=sp.symbol,
                exit_date=pd.Timestamp.now(tz="UTC"),
                exit_price=exit_price,
            )
            logger.info(
                "LIQUIDATION_PORTFOLIO_UPDATED | %s | exit_price=$%.4f | "
                "remaining_positions=%d",
                sp.symbol, exit_price,
                sum(len(v) for v in self.portfolio.open_positions.values()),
            )

            # Fix #6: Record trade in ledger
            if self.trade_ledger:
                self._record_trade_in_ledger(sp, order_result, exit_price)

            return True

        except Exception as e:
            error_msg = f"Exception closing {sp.symbol}: {e}"
            logger.error("LIQUIDATION_ERROR | %s", error_msg, exc_info=True)
            result.errors.append(error_msg)
            return False

    def _record_trade_in_ledger(self, sp: ScoredPosition, order_result, exit_price: float) -> None:
        """Record a liquidation sell in the trade ledger."""
        try:
            from broker.trade_ledger import create_trade_from_fills

            entry_date_str = sp.entry_date.isoformat() if hasattr(sp.entry_date, "isoformat") else str(sp.entry_date)

            trade = create_trade_from_fills(
                symbol=sp.symbol,
                entry_order_id=f"HYDRATED_{sp.symbol}",
                entry_fill_timestamp=entry_date_str,
                entry_fill_price=sp.entry_price,
                entry_fill_quantity=sp.position_size,
                exit_order_id=order_result.order_id or f"LIQUIDATION_{sp.symbol}",
                exit_fill_timestamp=pd.Timestamp.now(tz="UTC").isoformat(),
                exit_fill_price=exit_price,
                exit_fill_quantity=sp.position_size,
                exit_type="LIQUIDITY_EXIT",
                exit_reason=f"Liquidation: {self._trigger_reason}",
                confidence=sp.confidence,
                risk_amount=None,
                fees=0.0,
            )
            self.trade_ledger.add_trade(trade)

            # Remove from ledger open_positions if present
            if hasattr(self.trade_ledger, "_open_positions") and sp.symbol in self.trade_ledger._open_positions:
                del self.trade_ledger._open_positions[sp.symbol]
                self.trade_ledger._save_open_positions()

            logger.info("LIQUIDATION_LEDGER_RECORDED | %s | trade_id=%s", sp.symbol, trade.trade_id)
        except Exception as e:
            logger.error("LIQUIDATION_LEDGER_ERROR | %s | %s", sp.symbol, e)

    def _compute_heat(self, equity: float) -> float:
        """Compute current portfolio heat."""
        if equity <= 0:
            return 0.0
        total_risk = sum(
            pos.risk_amount
            for positions in self.portfolio.open_positions.values()
            for pos in positions
        )
        return total_risk / equity

    def _save_cash_reserve(self, reserve: CashReserve) -> None:
        """Persist cash reserve to disk."""
        try:
            reserve_file = Path(self.state_dir) / "cash_reserve.json"
            reserve_file.parent.mkdir(parents=True, exist_ok=True)
            with open(reserve_file, "w") as f:
                json.dump(reserve.to_dict(), f, indent=2)
            logger.info("CASH_RESERVE_PERSISTED | file=%s", reserve_file)
        except Exception as e:
            logger.error("CASH_RESERVE_PERSIST_ERROR | %s", e)

    @staticmethod
    def load_cash_reserve(state_dir: Path, portfolio: PortfolioState) -> Optional[CashReserve]:
        """
        Load persisted cash reserve from disk and set on portfolio if still active.

        Returns the loaded CashReserve if active, else None.
        """
        reserve_file = Path(state_dir) / "cash_reserve.json"
        if not reserve_file.exists():
            return None

        try:
            with open(reserve_file, "r") as f:
                data = json.load(f)
            reserve = CashReserve.from_dict(data)

            if reserve.is_active():
                portfolio.cash_reserve = reserve
                logger.info(
                    "CASH_RESERVE_LOADED | amount=$%.2f | expires=%s | reason=%s",
                    reserve.amount, reserve.expiry_date, reserve.reason,
                )
                return reserve
            else:
                logger.info(
                    "CASH_RESERVE_EXPIRED | amount=$%.2f | expired=%s | removing",
                    reserve.amount, reserve.expiry_date,
                )
                reserve_file.unlink(missing_ok=True)
                return None
        except Exception as e:
            logger.error("CASH_RESERVE_LOAD_ERROR | %s", e)
            return None

    def _log_scoring_table(
        self,
        scored: List[ScoredPosition],
        eligible: List[ScoredPosition],
        skipped: List[ScoredPosition],
    ) -> None:
        """Log full scoring table for audit trail."""
        eligible_symbols = {s.symbol for s in eligible}
        skipped_symbols = {s.symbol for s in skipped}

        logger.info("=" * 100)
        logger.info("LIQUIDATION PRIORITY TABLE")
        logger.info("=" * 100)
        logger.info(
            "%-8s %6s %7s %5s %4s %10s %6s %6s %6s %6s %10s",
            "Symbol", "Score", "PnL%", "Days", "Conf", "Notional",
            "sPnL", "sStl", "sCnf", "sSiz", "Eligible",
        )
        logger.info("-" * 100)

        for sp in scored:
            elig_status = "YES"
            if sp.symbol in skipped_symbols:
                elig_status = "PDT_SKIP"
            elif sp.symbol not in eligible_symbols:
                elig_status = "NO"

            logger.info(
                "%-8s %6.1f %+6.2f%% %5d %4d $%9.2f %6.1f %6.1f %6.1f %6.1f %10s",
                sp.symbol, sp.score, sp.unrealized_pnl_pct, sp.holding_days,
                sp.confidence, sp.notional_value,
                sp.score_breakdown.get("pnl", 0),
                sp.score_breakdown.get("staleness", 0),
                sp.score_breakdown.get("confidence", 0),
                sp.score_breakdown.get("size", 0),
                elig_status,
            )

        logger.info("=" * 100)
        logger.info(
            "Total: %d scored | %d eligible | %d PDT-skipped",
            len(scored), len(eligible), len(skipped),
        )

    def _log_summary(self, result: LiquidationResult) -> None:
        """Log liquidation summary."""
        if result.positions_sold:
            logger.info("=" * 80)
            logger.info("LIQUIDITY_RESOLVED")
            logger.info("=" * 80)
            logger.info("  Violations detected: %d", len(result.violations_detected))
            for v in result.violations_detected:
                logger.info("    - %s", v)
            logger.info("  Governing trigger: %s", result.trigger_reason)
            logger.info("  Positions evaluated: %d", result.positions_evaluated)
            logger.info("  Positions sold: %d (%s)", len(result.positions_sold), ", ".join(result.positions_sold))
            logger.info("  Cash freed: $%.2f", result.cash_freed)
            logger.info("  Cash: $%.2f -> $%.2f", result.cash_before, result.cash_after)
            logger.info("  Heat: %.2f%% -> %.2f%%", result.heat_before * 100, result.heat_after * 100)
            if result.positions_skipped_pdt:
                logger.info("  PDT skipped: %s", ", ".join(result.positions_skipped_pdt))
            if result.errors:
                logger.warning("  Errors: %s", result.errors)
            logger.info("=" * 80)
        else:
            logger.warning(
                "LIQUIDITY_UNRESOLVED | trigger=%s | "
                "no positions sold (evaluated=%d, pdt_skipped=%d, errors=%d)",
                result.trigger_reason,
                result.positions_evaluated,
                len(result.positions_skipped_pdt),
                len(result.errors),
            )
            if result.violations_detected:
                for v in result.violations_detected:
                    logger.warning("  UNRESOLVED_VIOLATION: %s", v)
