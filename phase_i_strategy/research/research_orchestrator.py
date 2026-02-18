"""
ResearchOrchestrator: Coordinates full research cycles.

Reads observatory anomalies to prioritize strategies, runs grid search,
validates top candidates via walk-forward, and records findings.

Runs during downtime (no trading) to avoid competing for resources.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from phase_i_strategy.config import (
    PHASE_I_RESEARCH_ENABLED,
    PHASE_I_STRATEGY_KILL_SWITCH,
    PARAMETER_SEARCH_SPACES,
    RESEARCH_MIN_SHARPE_IMPROVEMENT,
    MAX_RESEARCH_CYCLE_SECONDS,
    BACKTEST_MIN_CANDLES,
)
from phase_i_strategy.persistence import PhaseIPersistence
from phase_i_strategy.research.parameter_grid import ParameterGridSearch
from phase_i_strategy.research.walk_forward import WalkForwardValidator

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    """
    Coordinates strategy research cycles.

    Flow:
    1. Read observatory anomalies → prioritize strategies (ZERO_SIGNAL first)
    2. For each prioritized strategy:
       a. Load historical 5m data
       b. Run parameter grid search
       c. Take top N parameter sets by Sharpe
       d. Walk-forward validate each
       e. Compare best validated params against current
    3. Record findings to persistence
    """

    def __init__(self, runtime, persistence: PhaseIPersistence):
        self.runtime = runtime
        self.persistence = persistence
        self.scope = persistence.scope

    def run_research_cycle(self, trigger: str = "scheduled") -> Dict[str, Any]:
        """
        Run a full research cycle.

        Returns summary dict with findings.
        """
        if not PHASE_I_RESEARCH_ENABLED or PHASE_I_STRATEGY_KILL_SWITCH:
            logger.info("RESEARCH_CYCLE_SKIPPED | reason=disabled")
            return {"status": "skipped", "reason": "disabled"}

        start = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()
        logger.info("RESEARCH_CYCLE_START | trigger=%s scope=%s", trigger, self.scope)

        findings: List[Dict[str, Any]] = []
        errors: List[str] = []

        try:
            # Step 1: Prioritize strategies
            strategies_to_research = self._prioritize_strategies()
            if not strategies_to_research:
                logger.info("RESEARCH_CYCLE_NO_STRATEGIES | no strategies to research")
                return {"status": "completed", "findings": 0, "reason": "no_strategies"}

            # Step 2: Research each strategy
            for strategy_name, priority_reason in strategies_to_research:
                elapsed = time.monotonic() - start
                if elapsed > MAX_RESEARCH_CYCLE_SECONDS * 0.9:
                    logger.warning(
                        "RESEARCH_CYCLE_TIME_LIMIT | elapsed=%.0fs",
                        elapsed,
                    )
                    break

                try:
                    finding = self._research_strategy(strategy_name, priority_reason)
                    if finding:
                        findings.append(finding)
                except Exception as e:
                    logger.error(
                        "RESEARCH_STRATEGY_FAILED | strategy=%s error=%s",
                        strategy_name, e, exc_info=True,
                    )
                    errors.append(f"{strategy_name}: {e}")

            # Step 3: Persist findings
            for finding in findings:
                self.persistence.append_research_finding(finding)

            # Update run state
            run_state = self.persistence.load_run_state()
            run_state["last_research_run"] = now_iso
            run_state["total_research_findings"] = run_state.get("total_research_findings", 0) + len(findings)
            self.persistence.save_run_state(run_state)

            elapsed = time.monotonic() - start
            logger.info(
                "RESEARCH_CYCLE_DONE | trigger=%s strategies=%d findings=%d "
                "errors=%d elapsed=%.1fs",
                trigger, len(strategies_to_research), len(findings),
                len(errors), elapsed,
            )

            return {
                "status": "completed",
                "timestamp": now_iso,
                "trigger": trigger,
                "strategies_researched": len(strategies_to_research),
                "findings": len(findings),
                "errors": len(errors),
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error(
                "RESEARCH_CYCLE_FAILED | error=%s elapsed=%.1fs",
                e, elapsed, exc_info=True,
            )
            return {"status": "failed", "error": str(e)}

    def _prioritize_strategies(self) -> List[tuple]:
        """
        Determine which strategies need research, ordered by priority.

        Priority:
        1. Strategies with ZERO_SIGNAL anomalies (broken)
        2. Strategies with DEGRADATION anomalies (underperforming)
        3. Strategies with search spaces but no recent research

        Returns list of (strategy_name, reason) tuples.
        """
        # Get strategies that have search spaces defined
        researchable = set(PARAMETER_SEARCH_SPACES.keys())
        if not researchable:
            return []

        # Load recent anomalies
        anomalies = self.persistence.load_recent_anomalies(max_lines=200)

        # Collect anomaly-flagged strategies
        zero_signal = set()
        degraded = set()
        for a in anomalies:
            name = a.get("strategy_name", "")
            if name not in researchable:
                continue
            atype = a.get("anomaly_type", "")
            if atype == "ZERO_SIGNAL":
                zero_signal.add(name)
            elif atype == "DEGRADATION":
                degraded.add(name)

        # Build priority list
        prioritized = []

        # Priority 1: Zero-signal strategies
        for name in zero_signal:
            prioritized.append((name, "ZERO_SIGNAL"))

        # Priority 2: Degraded strategies
        for name in degraded - zero_signal:
            prioritized.append((name, "DEGRADATION"))

        # Priority 3: All other researchable strategies
        already = zero_signal | degraded
        for name in researchable - already:
            prioritized.append((name, "routine"))

        return prioritized

    def _research_strategy(
        self, strategy_name: str, priority_reason: str
    ) -> Optional[Dict[str, Any]]:
        """
        Research a single strategy: grid search → walk-forward validate.

        Returns a finding dict if an improvement is found, None otherwise.
        """
        logger.info(
            "RESEARCH_STRATEGY_START | strategy=%s reason=%s",
            strategy_name, priority_reason,
        )

        # Get strategy instance
        strategy = self._get_strategy(strategy_name)
        if strategy is None:
            logger.warning("RESEARCH_STRATEGY_NOT_FOUND | strategy=%s", strategy_name)
            return None

        # Pick a representative symbol to test against
        symbol = self._get_test_symbol()
        if symbol is None:
            logger.warning("RESEARCH_NO_SYMBOL | no test symbol available")
            return None

        # Load historical data
        bars_5m = self._load_historical_data(symbol)
        if bars_5m is None or len(bars_5m) < BACKTEST_MIN_CANDLES:
            logger.warning(
                "RESEARCH_INSUFFICIENT_DATA | symbol=%s bars=%d",
                symbol, len(bars_5m) if bars_5m is not None else 0,
            )
            return None

        # Determine regime for backtesting (use first supported regime)
        regimes = strategy.supported_regimes()
        regime = next(iter(regimes)) if regimes else "neutral"

        # Step 1: Grid search
        grid = ParameterGridSearch(
            strategy=strategy,
            symbol=symbol,
            bars_5m=bars_5m,
            regime_state=regime,
        )
        grid_result = grid.run()

        if grid_result is None or not grid_result.top_results:
            logger.info(
                "RESEARCH_NO_GRID_RESULTS | strategy=%s", strategy_name,
            )
            return None

        # Step 2: Walk-forward validate top candidates
        best_validated = None
        best_oos_sharpe = -999.0

        for candidate in grid_result.top_results:
            wf = WalkForwardValidator(
                strategy=strategy,
                symbol=symbol,
                bars_5m=bars_5m,
                regime_state=regime,
                param_overrides=candidate["params"],
            )
            wf_result = wf.validate()

            if wf_result is None:
                continue

            if wf_result.passed and wf_result.avg_oos_sharpe > best_oos_sharpe:
                best_oos_sharpe = wf_result.avg_oos_sharpe
                best_validated = {
                    "params": candidate["params"],
                    "grid_sharpe": candidate["sharpe"],
                    "oos_sharpe": wf_result.avg_oos_sharpe,
                    "oos_win_rate": wf_result.avg_oos_win_rate,
                    "oos_pass_ratio": wf_result.oos_pass_ratio,
                    "folds": wf_result.total_folds,
                }

        if best_validated is None:
            logger.info(
                "RESEARCH_NO_VALIDATED_CANDIDATE | strategy=%s",
                strategy_name,
            )
            return None

        # Step 3: Compare against current params
        current_sharpe = 0.0
        if grid_result.current_result:
            current_sharpe = grid_result.current_result.get("sharpe_ratio", 0.0)

        improvement = best_validated["oos_sharpe"] - current_sharpe
        if improvement < RESEARCH_MIN_SHARPE_IMPROVEMENT:
            logger.info(
                "RESEARCH_NO_IMPROVEMENT | strategy=%s "
                "current_sharpe=%.3f best_oos=%.3f improvement=%.3f < threshold=%.3f",
                strategy_name, current_sharpe, best_validated["oos_sharpe"],
                improvement, RESEARCH_MIN_SHARPE_IMPROVEMENT,
            )
            return None

        # Build finding
        finding = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy_name": strategy_name,
            "symbol": symbol,
            "regime": regime,
            "priority_reason": priority_reason,
            "current_params": grid_result.current_params,
            "proposed_params": best_validated["params"],
            "current_sharpe": current_sharpe,
            "proposed_oos_sharpe": best_validated["oos_sharpe"],
            "sharpe_improvement": improvement,
            "oos_win_rate": best_validated["oos_win_rate"],
            "oos_pass_ratio": best_validated["oos_pass_ratio"],
            "walk_forward_folds": best_validated["folds"],
            "grid_combinations": grid_result.total_combinations,
        }

        logger.info(
            "RESEARCH_FINDING | strategy=%s improvement=%.3f "
            "current=%.3f proposed=%.3f params=%s",
            strategy_name, improvement, current_sharpe,
            best_validated["oos_sharpe"], best_validated["params"],
        )

        return finding

    def _get_strategy(self, name: str):
        """Get a strategy instance by name from the registry."""
        try:
            from crypto.strategies.strategies_collection import CRYPTO_STRATEGIES
            return CRYPTO_STRATEGIES.get(name)
        except ImportError:
            logger.error("RESEARCH_IMPORT_FAILED | cannot import CRYPTO_STRATEGIES")
            return None

    def _get_test_symbol(self) -> Optional[str]:
        """Get a representative symbol for backtesting (BTC preferred)."""
        # BTC is the most liquid and data-rich — best for parameter research
        try:
            from universe.governance.persistence import load_active_universe
            universe = load_active_universe(self.scope)
            if universe:
                symbols = universe.get("symbols", [])
                # Prefer BTC if in universe
                if "BTC" in symbols:
                    return "BTC"
                if symbols:
                    return symbols[0]
        except Exception:
            pass
        # Fallback
        return "BTC"

    def _load_historical_data(self, symbol: str):
        """Load historical 5m candles for backtesting."""
        try:
            from data.crypto_price_loader import load_crypto_price_data_interval
            # Load enough data for walk-forward: 37 days * 288 bars/day ≈ 10656 bars
            # Request extra for multiple folds
            lookback = 12000
            bars = load_crypto_price_data_interval(symbol, lookback, "5m")
            return bars
        except Exception as e:
            logger.error(
                "RESEARCH_DATA_LOAD_FAILED | symbol=%s error=%s",
                symbol, e, exc_info=True,
            )
            return None
