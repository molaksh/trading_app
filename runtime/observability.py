"""
Operational observability for live crypto trading.

Provides:
- Human-readable live status snapshots
- Daily immutable JSONL summaries
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, Optional, Set, Any

from config.scope import get_scope
from config.scope_paths import get_scope_path
from config.crypto_scheduler_settings import (
    STATUS_SNAPSHOT_INTERVAL_MINUTES,
    DAILY_SUMMARY_OUTPUT_PATH,
    AI_ADVISOR_ENABLED,
)
from runtime.trade_permission import get_trade_permission, set_trade_permission_hook

logger = logging.getLogger(__name__)


@dataclass
class ObservabilityCounters:
    trades_taken: int = 0
    trades_skipped: int = 0
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    blocks_encountered: Set[str] = field(default_factory=set)
    data_issues: int = 0
    reconciliation_issues: int = 0
    risk_blocks: int = 0
    manual_halt_used: bool = False
    ai_calls_today: int = 0
    ai_last_call_time: Optional[str] = None
    ai_last_success_time: Optional[str] = None
    ai_last_error: Optional[str] = None
    ai_last_ranking: Optional[Dict[str, Any]] = None
    ai_ranked_universe_size: Optional[int] = None
    ai_scan_coverage_count: Optional[int] = None
    signals_skipped_due_to_capacity: int = 0
    # Current regime tracking
    current_regime: str = "UNKNOWN"
    regime_changed: bool = False
    regime_change_ts: Optional[str] = None
    # Phase D: Regime block tracking
    regime_block_active: bool = False
    regime_block_start_ts: Optional[str] = None
    regime_block_regime: Optional[str] = None
    regime_block_strategies_eligible: int = 0


class RuntimeObservability:
    def __init__(self) -> None:
        self._runtime = None
        self._start_time = datetime.now(timezone.utc)
        self._last_snapshot_time: Optional[datetime] = None
        self._last_summary_date: Optional[str] = None
        self._market_data_status: str = "FRESH"
        self._counters = ObservabilityCounters()

    def attach_runtime(self, runtime) -> None:
        self._runtime = runtime

    def record_trade_taken(self) -> None:
        self._counters.trades_taken += 1

    def record_trade_skipped(self, state: str) -> None:
        self._counters.trades_skipped += 1
        self._counters.skip_reasons[state] = self._counters.skip_reasons.get(state, 0) + 1

    def record_block(self, state: str) -> None:
        self._counters.blocks_encountered.add(state)
        if state == "MARKET_DATA_BLOCKED":
            self._counters.data_issues += 1
            self._market_data_status = "BLOCKED"
        elif state == "RECONCILIATION_BLOCKED":
            self._counters.reconciliation_issues += 1
        elif state == "RISK_LIMIT_BLOCKED":
            self._counters.risk_blocks += 1
        elif state == "MANUAL_HALT":
            self._counters.manual_halt_used = True

    def record_unblock(self, state: str) -> None:
        if state == "MARKET_DATA_BLOCKED":
            self._market_data_status = "FRESH"

    def mark_market_data_stale(self) -> None:
        if self._market_data_status != "BLOCKED":
            self._market_data_status = "STALE"

    def mark_market_data_fresh(self) -> None:
        self._market_data_status = "FRESH"

    def record_ai_attempt(self, calls_today: int, call_time: datetime) -> None:
        self._counters.ai_calls_today = calls_today
        self._counters.ai_last_call_time = call_time.isoformat()

    def record_ai_success(self, success_time: datetime, ranked_symbols: list, reasoning: str) -> None:
        self._counters.ai_last_success_time = success_time.isoformat()
        self._counters.ai_last_error = None
        self._counters.ai_last_ranking = {
            "ranked_symbols": ranked_symbols,
            "reasoning": reasoning,
        }

    def record_ai_error(self, error: str) -> None:
        self._counters.ai_last_error = error

    def record_scan_metrics(
        self,
        ai_ranked_universe_size: int,
        ai_scan_coverage_count: int,
        skipped_due_to_capacity: int,
    ) -> None:
        self._counters.ai_ranked_universe_size = int(ai_ranked_universe_size)
        self._counters.ai_scan_coverage_count = int(ai_scan_coverage_count)
        if skipped_due_to_capacity > 0:
            self._counters.signals_skipped_due_to_capacity += int(skipped_due_to_capacity)

    def on_block_change(self, state: str, reason: str, action: str) -> None:
        if action == "block":
            self.record_block(state)
        elif action == "unblock":
            self.record_unblock(state)
        self.emit_live_status_snapshot(trigger=f"{action}:{state}")

    def on_strategies_selected(self, eligible_strategies: list, regime: str) -> None:
        """Hook called after strategy selection. Used for Phase D regime block tracking and current regime tracking."""
        # Track current regime
        if regime and regime != self._counters.current_regime:
            self._counters.regime_changed = True
            self._counters.regime_change_ts = datetime.now(timezone.utc).isoformat()
            logger.debug(f"REGIME_CHANGED | from={self._counters.current_regime} to={regime}")
        self._counters.current_regime = regime if regime else "UNKNOWN"

        # Phase D block tracking
        is_blocked = len(eligible_strategies) == 0

        if is_blocked and not self._counters.regime_block_active:
            # Block started
            self._counters.regime_block_active = True
            self._counters.regime_block_start_ts = datetime.now(timezone.utc).isoformat()
            self._counters.regime_block_regime = regime
            self._counters.regime_block_strategies_eligible = 0
            logger.debug(f"REGIME_BLOCK_STARTED | regime={regime}")

        elif not is_blocked and self._counters.regime_block_active:
            # Block ended
            if self._counters.regime_block_start_ts:
                duration = (datetime.now(timezone.utc) - datetime.fromisoformat(self._counters.regime_block_start_ts)).total_seconds()
                logger.debug(f"REGIME_BLOCK_ENDED | regime={self._counters.regime_block_regime} duration={duration:.0f}s")
            self._counters.regime_block_active = False
            self._counters.regime_block_start_ts = None
            self._counters.regime_block_regime = None

        elif is_blocked and self._counters.regime_block_active:
            # Block still active, update strategy count
            self._counters.regime_block_strategies_eligible = len(eligible_strategies)

    def _uptime_seconds(self) -> int:
        return int((datetime.now(timezone.utc) - self._start_time).total_seconds())

    def _daily_realized_pnl(self) -> float:
        if self._runtime is None:
            return 0.0
        ledger = self._runtime.trade_ledger
        today = datetime.now(timezone.utc).date().isoformat()
        realized = 0.0
        for trade in ledger.get_all_trades():
            try:
                exit_date = datetime.fromisoformat(trade.exit_timestamp).date().isoformat()
                if exit_date == today:
                    realized += float(trade.net_pnl)
            except Exception:
                continue
        return float(realized)

    def _unrealized_pnl(self) -> float:
        if self._runtime is None:
            return 0.0
        portfolio = self._runtime.risk_manager.portfolio
        total = 0.0
        for positions in portfolio.open_positions.values():
            for pos in positions:
                total += float(getattr(pos, "unrealized_pnl", 0.0))
        return float(total)

    def _max_drawdown(self) -> float:
        if self._runtime is None:
            return 0.0
        portfolio = self._runtime.risk_manager.portfolio
        equity_values = [value for _, value in portfolio.equity_history]
        if not equity_values:
            return 0.0
        peak = equity_values[0]
        max_dd = 0.0
        for value in equity_values:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak if peak > 0 else 0.0
            if drawdown > max_dd:
                max_dd = drawdown
        return float(max_dd)

    def emit_live_status_snapshot(self, trigger: str) -> None:
        scope = get_scope()
        if scope.env.lower() != "live":
            return

        now = datetime.now(timezone.utc)
        interval_seconds = max(1, STATUS_SNAPSHOT_INTERVAL_MINUTES) * 60
        if trigger.startswith("interval"):
            if self._last_snapshot_time is not None:
                elapsed = (now - self._last_snapshot_time).total_seconds()
                if elapsed < interval_seconds:
                    return

        permission = get_trade_permission()
        block = permission.get_primary_block()

        if block is not None:
            active_state = block.state
            block_reason = block.reason
        else:
            active_state = "NONE"
            block_reason = "NONE"

        open_positions = 0
        if self._runtime is not None:
            try:
                positions = self._runtime.broker.get_positions()
                open_positions = len(positions)
            except Exception:
                open_positions = 0

        realized = self._daily_realized_pnl()
        unrealized = self._unrealized_pnl()
        last_trade_ts = "NONE"
        if self._runtime is not None:
            trades = self._runtime.trade_ledger.get_all_trades()
            if trades:
                last_trade_ts = trades[-1].exit_timestamp

        reconciliation_status = "OK" if active_state != "RECONCILIATION_BLOCKED" else "BLOCKED"

        logger.info("================ LIVE STATUS =================")
        logger.info(f"ENV: {scope.env.upper()}")
        logger.info(f"BROKER: {scope.broker.upper()}")
        logger.info(f"MARKET: {scope.market.upper()}")
        logger.info(f"TRADING_ALLOWED: {'YES' if permission.trade_allowed() else 'NO'}")
        logger.info(f"ACTIVE_BLOCK_STATE: {active_state}")
        logger.info(f"BLOCK_REASON: {block_reason}")
        logger.info(f"MARKET_DATA_STATUS: {self._market_data_status}")
        logger.info(f"RECONCILIATION_STATUS: {reconciliation_status}")
        logger.info(f"AI_ENABLED: {'YES' if AI_ADVISOR_ENABLED else 'NO'}")
        logger.info(f"AI_CALLS_TODAY: {self._counters.ai_calls_today}")
        logger.info(f"AI_LAST_CALL_TIME: {self._counters.ai_last_call_time or 'NONE'}")
        logger.info(f"AI_LAST_SUCCESS_TIME: {self._counters.ai_last_success_time or 'NONE'}")
        logger.info(f"AI_LAST_ERROR: {self._counters.ai_last_error or 'NONE'}")
        logger.info(f"AI_RANKED_UNIVERSE_SIZE: {self._counters.ai_ranked_universe_size or 0}")
        logger.info(f"AI_SCAN_COVERAGE_COUNT: {self._counters.ai_scan_coverage_count or 0}")
        logger.info(
            f"SIGNALS_SKIPPED_DUE_TO_CAPACITY: {self._counters.signals_skipped_due_to_capacity}"
        )
        logger.info(f"OPEN_POSITIONS: {open_positions}")
        logger.info(f"DAILY_PNL: {realized + unrealized:.2f}")
        logger.info(f"LAST_TRADE_TIMESTAMP: {last_trade_ts}")
        logger.info(f"UPTIME_SECONDS: {self._uptime_seconds()}")
        logger.info("=============================================")

        self._last_snapshot_time = now

    def _summary_path(self) -> Path:
        if DAILY_SUMMARY_OUTPUT_PATH:
            return Path(DAILY_SUMMARY_OUTPUT_PATH)
        scope = get_scope()
        logs_dir = get_scope_path(scope, "logs")
        return Path(logs_dir) / "daily_summary.jsonl"

    def _summary_exists(self, summary_path: Path, day: str) -> bool:
        if not summary_path.exists():
            return False
        try:
            with summary_path.open("r") as f:
                for line in f:
                    try:
                        payload = json.loads(line.strip())
                    except Exception:
                        continue
                    if payload.get("date") == day:
                        return True
        except Exception as e:
            logger.error(f"SUMMARY_READ_FAILED | error={e}")
        return False

    def emit_daily_summary(self, force: bool = False) -> None:
        scope = get_scope()
        # Emit daily summaries for ALL scopes (live, paper, all strategies)

        today = date.today().isoformat()
        if self._last_summary_date == today and not force:
            return

        summary_path = self._summary_path()
        logger.debug(f"SUMMARY_PATH | path={summary_path}")

        try:
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(f"SUMMARY_DIR_CREATED | path={summary_path.parent}")
        except Exception as e:
            logger.error(f"SUMMARY_DIR_CREATE_FAILED | path={summary_path.parent} error={e}")
            return

        if self._summary_exists(summary_path, today):
            logger.error(f"SUMMARY_DUPLICATE_ATTEMPT | date={today} path={summary_path}")
            self._last_summary_date = today
            return

        # Compute regime block duration
        block_duration_seconds = 0
        if self._counters.regime_block_active and self._counters.regime_block_start_ts:
            try:
                block_start = datetime.fromisoformat(self._counters.regime_block_start_ts)
                block_duration_seconds = int((datetime.now(timezone.utc) - block_start).total_seconds())
            except Exception:
                block_duration_seconds = 0

        payload = {
            "date": today,
            "env": scope.env.lower(),
            "broker": scope.broker.lower(),
            "uptime_seconds": self._uptime_seconds(),
            "trades_taken": self._counters.trades_taken,
            "trades_skipped": self._counters.trades_skipped,
            "skip_reasons": self._counters.skip_reasons,
            "realized_pnl": self._daily_realized_pnl(),
            "unrealized_pnl": self._unrealized_pnl(),
            "max_drawdown": self._max_drawdown(),
            "blocks_encountered": sorted(self._counters.blocks_encountered),
            "data_issues": self._counters.data_issues,
            "reconciliation_issues": self._counters.reconciliation_issues,
            "risk_blocks": self._counters.risk_blocks,
            "manual_halt_used": self._counters.manual_halt_used,
            "ai_calls_today": self._counters.ai_calls_today,
            "ai_last_call_time": self._counters.ai_last_call_time,
            "ai_last_success_time": self._counters.ai_last_success_time,
            "ai_last_error": self._counters.ai_last_error,
            "ai_last_ranking": self._counters.ai_last_ranking,
            "ai_ranked_universe_size": self._counters.ai_ranked_universe_size,
            "ai_scan_coverage_count": self._counters.ai_scan_coverage_count,
            "signals_skipped_due_to_capacity": self._counters.signals_skipped_due_to_capacity,
            # Current regime
            "regime": self._counters.current_regime,
            "regime_changed": self._counters.regime_changed,
            "regime_change_ts": self._counters.regime_change_ts,
            # Phase D: Regime block state
            "regime_blocked_period": {
                "is_blocked": self._counters.regime_block_active,
                "block_duration_seconds": block_duration_seconds,
                "regime": self._counters.regime_block_regime or "UNKNOWN",
                "strategies_eligible": self._counters.regime_block_strategies_eligible,
            },
        }

        try:
            with summary_path.open("a") as f:
                f.write(json.dumps(payload) + "\n")
            self._last_summary_date = today
            logger.info(f"DAILY_SUMMARY_WRITTEN | date={today} path={summary_path}")
        except Exception as e:
            logger.error(f"DAILY_SUMMARY_WRITE_FAILED | date={today} error={e}")

    def check_daily_summary(self) -> None:
        today = date.today().isoformat()

        # If this is first time OR day has changed, emit summary
        if self._last_summary_date is None or today != self._last_summary_date:
            logger.info(f"Daily summary trigger | date={today} last_date={self._last_summary_date}")
            self.emit_daily_summary(force=True)
            self._last_summary_date = today

        # Periodic health check summary (every 12 hours) for continuous monitoring
        # This ensures data flows even if market hours are limited
        if hasattr(self, '_last_health_summary_time'):
            from datetime import datetime, timedelta
            now = datetime.now()
            if (now - self._last_health_summary_time).total_seconds() > (12 * 3600):
                logger.info(f"Periodic health summary | interval=12h")
                self.emit_daily_summary(force=True)
                self._last_health_summary_time = now
        else:
            from datetime import datetime
            self._last_health_summary_time = datetime.now()


_OBSERVABILITY: Optional[RuntimeObservability] = None


def get_observability() -> RuntimeObservability:
    global _OBSERVABILITY
    if _OBSERVABILITY is None:
        _OBSERVABILITY = RuntimeObservability()
        set_trade_permission_hook(_OBSERVABILITY.on_block_change)
    return _OBSERVABILITY
