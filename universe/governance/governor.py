"""
Phase G Governor: Orchestrates the full universe governance pipeline.

Pipeline: score -> rank -> apply guardrails -> decide adds/removes -> persist.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from universe.governance.scorer import UniverseScorer, ScoredCandidate
from universe.governance.guardrails import UniverseGuardrails
from universe.governance.persistence import UniverseGovernancePersistence
from universe.governance.logging import PhaseGLogger
from universe.governance.config import PHASE_G_DRY_RUN

logger = logging.getLogger(__name__)


@dataclass
class GovernanceDecision:
    run_id: str
    timestamp_utc: str
    scope: str
    regime_label: str
    candidate_scores: List[Dict[str, Any]]
    current_universe_scores: List[Dict[str, Any]]
    additions: List[str]
    removals: List[str]
    retained: List[str]
    final_universe: List[str]
    guardrail_checks: List[Dict[str, Any]]
    dry_run: bool
    reasoning: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class UniverseGovernor:
    """Orchestrates the full Phase G universe governance pipeline."""

    def __init__(
        self,
        scope,
        scorer: UniverseScorer,
        guardrails: UniverseGuardrails,
        persistence: UniverseGovernancePersistence,
        phase_g_logger: PhaseGLogger,
        trade_ledger,
        regime_provider,
        verdict_reader,
    ):
        self.scope = scope
        self.scorer = scorer
        self.guardrails = guardrails
        self.persistence = persistence
        self.phase_g_logger = phase_g_logger
        self.trade_ledger = trade_ledger
        self.regime_provider = regime_provider
        self.verdict_reader = verdict_reader

    def run_governance_cycle(
        self,
        candidate_pool: List[str],
        current_universe: List[str],
        trigger: str = "manual",
        dry_run: Optional[bool] = None,
        ohlcv_data: Optional[Dict[str, Any]] = None,
    ) -> GovernanceDecision:
        """
        Full governance cycle:
        1. Score all candidates in the pool
        2. Score all symbols in current universe
        3. Rank by total_score
        4. Apply guardrails (max add/remove, min/max size, cooldown)
        5. Produce GovernanceDecision with adds, removes, retained
        6. Log every step
        7. Persist decision
        """
        start_time = time.time()
        run_id = f"gov_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

        if dry_run is None:
            dry_run = PHASE_G_DRY_RUN

        scope_str = str(self.scope)

        self.phase_g_logger.log_governance_cycle_start(
            run_id=run_id,
            trigger=trigger,
            candidate_count=len(candidate_pool),
        )

        logger.info(
            "GOVERNANCE_CYCLE_START | run_id=%s | trigger=%s | "
            "candidates=%d | current_universe=%d | dry_run=%s",
            run_id, trigger, len(candidate_pool), len(current_universe), dry_run,
        )

        # Step 1: Get regime signal
        regime_label = self._get_regime_label(run_id)

        # Step 2: Get Phase F verdict
        verdict = self._get_verdict(run_id, scope_str)

        # Step 3: Build trade history map
        trade_history_by_symbol = self._build_trade_history(candidate_pool)

        # Step 4: Load OHLCV data if not provided
        if ohlcv_data is None:
            ohlcv_data = self._load_ohlcv_data(candidate_pool, scope_str)

        # Step 5: Score all candidates
        all_candidates = list(set(candidate_pool) | set(current_universe))
        scored = self.scorer.score_universe(
            candidates=all_candidates,
            ohlcv_data=ohlcv_data,
            trade_history_by_symbol=trade_history_by_symbol,
            regime_label=regime_label,
            verdict=verdict,
        )

        # Log each score
        for s in scored:
            self.phase_g_logger.log_symbol_score_computed(
                run_id=run_id,
                symbol=s.symbol,
                total_score=s.total_score,
                dimension_scores=s.dimension_scores,
                weighted_scores=s.weighted_scores,
                raw_metrics=s.raw_metrics,
            )

        # Persist scoring history
        self.persistence.append_scores([s.to_dict() for s in scored])

        # Step 6: Determine additions and removals
        scored_map = {s.symbol: s for s in scored}

        # Candidates not in current universe, sorted by score desc
        potential_adds = [
            s for s in scored if s.symbol not in current_universe
        ]

        # Current universe members, sorted by score asc (lowest first for removal)
        current_scored = [
            s for s in scored if s.symbol in current_universe
        ]
        current_scored.sort(key=lambda c: c.total_score)

        # Step 7: Apply guardrails for removals
        guardrail_checks: List[Dict[str, Any]] = []
        open_symbols = self._get_open_symbols()
        cooldowns = self.persistence.load_cooldowns()
        removals: List[str] = []
        removals_count = 0

        for candidate in current_scored:
            if candidate.total_score > from_config("MAX_SCORE_TO_REMOVE"):
                break  # Sorted by score asc, so we can stop early

            allowed, reason = self.guardrails.check_removal(
                symbol=candidate.symbol,
                score=candidate.total_score,
                current_size=len(current_universe) - removals_count,
                removals_this_cycle=removals_count,
                open_symbols=open_symbols,
            )

            check = {
                "check_type": "removal",
                "symbol": candidate.symbol,
                "score": candidate.total_score,
                "allowed": allowed,
                "reason": reason,
            }
            guardrail_checks.append(check)

            self.phase_g_logger.log_guardrail_check(
                run_id=run_id,
                check_type="removal",
                symbol=candidate.symbol,
                input_values={"score": candidate.total_score, "current_size": len(current_universe) - removals_count},
                decision="ALLOWED" if allowed else "BLOCKED",
                reason=reason,
            )

            has_open = candidate.symbol in open_symbols

            if allowed:
                removals.append(candidate.symbol)
                removals_count += 1
                self.phase_g_logger.log_removal_proposed(
                    run_id=run_id,
                    symbol=candidate.symbol,
                    score=candidate.total_score,
                    reason=f"score below threshold",
                    guardrail_result="ALLOWED",
                    has_open_position=has_open,
                )
            else:
                self.phase_g_logger.log_removal_proposed(
                    run_id=run_id,
                    symbol=candidate.symbol,
                    score=candidate.total_score,
                    reason=reason,
                    guardrail_result="BLOCKED",
                    has_open_position=has_open,
                )

        # Step 8: Apply guardrails for additions
        additions: List[str] = []
        additions_count = 0
        effective_size = len(current_universe) - removals_count

        for candidate in potential_adds:
            allowed, reason = self.guardrails.check_addition(
                symbol=candidate.symbol,
                score=candidate.total_score,
                current_size=effective_size + additions_count,
                additions_this_cycle=additions_count,
                cooldown_registry=cooldowns,
            )

            check = {
                "check_type": "addition",
                "symbol": candidate.symbol,
                "score": candidate.total_score,
                "allowed": allowed,
                "reason": reason,
            }
            guardrail_checks.append(check)

            self.phase_g_logger.log_guardrail_check(
                run_id=run_id,
                check_type="addition",
                symbol=candidate.symbol,
                input_values={"score": candidate.total_score, "current_size": effective_size + additions_count},
                decision="ALLOWED" if allowed else "BLOCKED",
                reason=reason,
            )

            if allowed:
                additions.append(candidate.symbol)
                additions_count += 1
                self.phase_g_logger.log_addition_proposed(
                    run_id=run_id,
                    symbol=candidate.symbol,
                    score=candidate.total_score,
                    reason=f"score above threshold",
                    guardrail_result="ALLOWED",
                )
            else:
                self.phase_g_logger.log_addition_proposed(
                    run_id=run_id,
                    symbol=candidate.symbol,
                    score=candidate.total_score,
                    reason=reason,
                    guardrail_result="BLOCKED",
                )

        # Step 9: Compute final universe
        retained = [s for s in current_universe if s not in removals]
        final_universe = retained + additions

        # Validate final universe
        violations = self.guardrails.validate_final_universe(final_universe, current_universe)
        if violations:
            for v in violations:
                logger.warning(
                    "GUARDRAIL_VIOLATION | check=%s | symbol=%s | reason=%s",
                    v.check_type, v.symbol, v.reason,
                )
                # If violations exist, fall back to current universe
            logger.warning("GUARDRAIL_VIOLATIONS_DETECTED | reverting to current universe")
            additions = []
            removals = []
            retained = list(current_universe)
            final_universe = list(current_universe)

        # Build reasoning summary
        reasoning = self._build_reasoning(
            regime_label, len(scored), additions, removals, retained, dry_run,
        )

        # Step 10: Build decision
        decision = GovernanceDecision(
            run_id=run_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            scope=scope_str,
            regime_label=regime_label,
            candidate_scores=[s.to_dict() for s in scored if s.symbol not in current_universe],
            current_universe_scores=[s.to_dict() for s in scored if s.symbol in current_universe],
            additions=additions,
            removals=removals,
            retained=retained,
            final_universe=final_universe,
            guardrail_checks=guardrail_checks,
            dry_run=dry_run,
            reasoning=reasoning,
        )

        # Step 11: Persist
        self.persistence.append_decision(decision.to_dict())

        if not dry_run:
            self.persistence.write_active_universe(final_universe)
            # Update cooldowns for removed symbols
            if removals:
                now_iso = datetime.now(timezone.utc).isoformat()
                for symbol in removals:
                    cooldowns[symbol] = now_iso
                self.persistence.save_cooldowns(cooldowns)
        else:
            self.phase_g_logger.log_dry_run_decision(run_id, {
                "additions": additions,
                "removals": removals,
                "final_universe": final_universe,
                "reasoning": reasoning,
            })

        # Step 12: Log decision
        decision_summary = {
            "additions": additions,
            "removals": removals,
            "retained_count": len(retained),
            "final_universe_size": len(final_universe),
            "regime_label": regime_label,
            "dry_run": dry_run,
            "reasoning": reasoning,
        }
        self.phase_g_logger.log_governance_decision(run_id, decision_summary)

        duration_ms = (time.time() - start_time) * 1000
        self.phase_g_logger.log_governance_cycle_complete(
            run_id=run_id,
            duration_ms=duration_ms,
            symbols_scored=len(scored),
            adds=additions,
            removes=removals,
        )

        logger.info(
            "GOVERNANCE_CYCLE_COMPLETE | run_id=%s | duration_ms=%.1f | "
            "scored=%d | adds=%s | removes=%s | final_size=%d | dry_run=%s",
            run_id, duration_ms, len(scored), additions, removals,
            len(final_universe), dry_run,
        )

        return decision

    # ========================================================================
    # Internal helpers
    # ========================================================================

    def _get_regime_label(self, run_id: str) -> str:
        """Get current regime label from provider."""
        try:
            if self.regime_provider is not None:
                # CryptoRegimeEngine has get_current_regime()
                regime = self.regime_provider.get_current_regime()
                if regime is not None:
                    label = regime.value if hasattr(regime, "value") else str(regime)
                    self.phase_g_logger.log_regime_signal_used(
                        run_id=run_id,
                        regime_label=label,
                        confidence=1.0,
                        source="crypto_regime_engine",
                    )
                    return label

            # Fallback: try SPY proxy for non-crypto
            from universe.governance.regime_proxy import SPYRegimeProxy
            proxy = SPYRegimeProxy()
            label = proxy.get_regime()
            if label:
                self.phase_g_logger.log_regime_signal_used(
                    run_id=run_id,
                    regime_label=label,
                    confidence=0.8,
                    source="spy_regime_proxy",
                )
                return label
        except Exception as e:
            logger.warning("REGIME_FALLBACK | error=%s | defaulting to neutral", e)

        self.phase_g_logger.log_regime_signal_used(
            run_id=run_id,
            regime_label="neutral",
            confidence=0.0,
            source="default_fallback",
        )
        return "neutral"

    def _get_verdict(self, run_id: str, scope_str: str) -> Optional[Dict[str, Any]]:
        """Get latest Phase F verdict."""
        try:
            if self.verdict_reader is not None:
                # Extract scope name for verdict reader (e.g. "crypto" from scope string)
                verdict_scope = "crypto"
                if "crypto" in scope_str.lower():
                    verdict_scope = "crypto"

                verdict = self.verdict_reader.read_latest_verdict(scope=verdict_scope)
                if verdict:
                    v = verdict.get("verdict", {})
                    self.phase_g_logger.log_verdict_consumed(
                        run_id=run_id,
                        verdict_type=v.get("verdict"),
                        confidence=v.get("regime_confidence"),
                        num_sources=v.get("num_sources_analyzed"),
                    )
                    return verdict
        except Exception as e:
            logger.warning("VERDICT_FALLBACK | error=%s", e)

        self.phase_g_logger.log_verdict_consumed(
            run_id=run_id,
            verdict_type=None,
            confidence=None,
            num_sources=None,
        )
        return None

    def _build_trade_history(self, symbols: List[str]) -> Dict[str, list]:
        """Build trade history map from trade ledger."""
        history = {}
        try:
            if self.trade_ledger is not None:
                for symbol in symbols:
                    trades = self.trade_ledger.get_trades_for_symbol(symbol)
                    history[symbol] = trades
        except Exception as e:
            logger.warning("TRADE_HISTORY_ERROR | error=%s", e)
        return history

    def _load_ohlcv_data(self, symbols: List[str], scope_str: str) -> Dict[str, Any]:
        """Load OHLCV data for all symbols."""
        data = {}
        is_crypto = "crypto" in scope_str.lower()

        for symbol in symbols:
            try:
                if is_crypto:
                    from data.crypto_price_loader import load_crypto_price_data
                    df = load_crypto_price_data(symbol, lookback_days=30)
                else:
                    from data.price_loader import load_price_data
                    df = load_price_data(symbol, lookback_days=30)

                if df is not None and len(df) > 0:
                    data[symbol] = df
            except Exception as e:
                logger.warning("OHLCV_LOAD_ERROR | symbol=%s | error=%s", symbol, e)

        return data

    def _get_open_symbols(self) -> List[str]:
        """Get list of symbols with open positions."""
        try:
            if self.trade_ledger is not None and hasattr(self.trade_ledger, "_open_positions"):
                return [s for s, p in self.trade_ledger._open_positions.items() if p]
        except Exception:
            pass
        return []

    def _build_reasoning(
        self,
        regime_label: str,
        scored_count: int,
        additions: List[str],
        removals: List[str],
        retained: List[str],
        dry_run: bool,
    ) -> str:
        """Build human-readable reasoning summary."""
        parts = [f"Regime: {regime_label}. Scored {scored_count} symbols."]

        if additions:
            parts.append(f"Adding {len(additions)}: {', '.join(additions)}.")
        else:
            parts.append("No additions.")

        if removals:
            parts.append(f"Removing {len(removals)}: {', '.join(removals)}.")
        else:
            parts.append("No removals.")

        parts.append(f"Retaining {len(retained)}. Final universe: {len(retained) + len(additions)} symbols.")

        if dry_run:
            parts.append("[DRY RUN - no changes applied]")

        return " ".join(parts)


def from_config(key: str):
    """Import config value by name to avoid circular import at module level."""
    from universe.governance import config
    return getattr(config, key)
