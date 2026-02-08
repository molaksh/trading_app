"""
Generate concise, deterministic responses to user intents.
"""

import logging
from typing import Optional, Tuple
from datetime import datetime
from pathlib import Path

from ops_agent.schemas import Intent, OpsDiagnostic, ObservabilitySnapshot
from ops_agent.observability_reader import ObservabilityReader
from ops_agent.summary_reader import SummaryReader
from ops_agent.logs_reader import LogsReader
from ops_agent.positions_reader import PositionsReader

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """Generate deterministic ops explanations."""

    def __init__(self, logs_root: str = "logs"):
        self.obs_reader = ObservabilityReader(logs_root)
        self.summary_reader = SummaryReader(logs_root)
        self.logs_reader = LogsReader(logs_root)
        self.positions_reader = PositionsReader(logs_root)

    def generate_response(self, intent: Intent) -> str:
        """
        Generate a concise Telegram response for an intent.

        Returns plain text response (no Markdown, no speculation).
        """
        # If user asked for "all containers", check all scopes
        if intent.all_scopes:
            if intent.intent_type == "EXPLAIN_JOBS":
                return self._explain_all_jobs()
            elif intent.intent_type == "EXPLAIN_ERRORS":
                return self._explain_all_errors()
            elif intent.intent_type == "EXPLAIN_TODAY":
                return self._explain_all_today()
            elif intent.intent_type == "EXPLAIN_AI_RANKING":
                return self._explain_all_ai_rankings()
            elif intent.intent_type == "EXPLAIN_HOLDINGS":
                return self._explain_all_holdings()
            elif intent.intent_type in ["STATUS", "EXPLAIN_NO_TRADES"]:
                return self._explain_all_status()

        # For system-wide checks (jobs, errors), check all scopes if not specified
        if intent.intent_type in ["EXPLAIN_JOBS", "EXPLAIN_ERRORS"] and not intent.scope:
            if intent.intent_type == "EXPLAIN_JOBS":
                return self._explain_all_jobs()
            else:
                return self._explain_all_errors()

        # Infer scope if not provided
        scope = intent.scope or self._infer_default_scope()
        if not scope:
            return "❓ Couldn't determine scope. Try: 'live crypto', 'paper us', etc."

        # Get observability state (try snapshot, fall back to daily summary)
        obs = self.obs_reader.get_snapshot(scope)
        if not obs:
            # Fall back to daily summary
            latest_summary = self.summary_reader.get_latest_summary(scope)
            if not latest_summary:
                return f"⏳ {scope}: No data yet. Check back soon."

            # Build minimal snapshot from daily summary
            obs = ObservabilitySnapshot(
                scope=scope,
                timestamp=latest_summary.timestamp,
                regime=latest_summary.regime,
                trading_active=latest_summary.trades_executed > 0 or not latest_summary.blocks,
                blocks=latest_summary.blocks,
                recent_trades=latest_summary.trades_executed,
                daily_pnl=latest_summary.realized_pnl,
                max_drawdown=latest_summary.max_drawdown,
                scan_coverage=1 if latest_summary.trades_executed > 0 else 0,
                signals_skipped=0,
                trades_executed=latest_summary.trades_executed,
                data_issues=latest_summary.data_issues,
            )

        # Route to specific explanation
        if intent.intent_type == "EXPLAIN_NO_TRADES":
            return self._explain_no_trades(scope, obs)
        elif intent.intent_type == "EXPLAIN_TRADES":
            return self._explain_trades(scope, obs)
        elif intent.intent_type == "EXPLAIN_REGIME":
            return self._explain_regime(scope, obs)
        elif intent.intent_type == "EXPLAIN_BLOCKS":
            return self._explain_blocks(scope, obs)
        elif intent.intent_type == "EXPLAIN_TODAY":
            return self._explain_today(scope, obs)
        elif intent.intent_type == "EXPLAIN_GOVERNANCE":
            return self._explain_governance()
        elif intent.intent_type == "EXPLAIN_AI_RANKING":
            return self._explain_ai_ranking(scope)
        elif intent.intent_type == "EXPLAIN_JOBS":
            return self._explain_jobs(scope)
        elif intent.intent_type == "EXPLAIN_ERRORS":
            return self._explain_errors(scope)
        elif intent.intent_type == "EXPLAIN_HOLDINGS":
            return self._explain_holdings(scope)
        else:  # STATUS
            return self._explain_status(scope, obs)

    def _explain_no_trades(self, scope: str, obs: ObservabilitySnapshot) -> str:
        """Why are trades not happening?"""
        if obs.trading_active and obs.trades_executed > 0:
            return f"✓ {scope}: Trades ARE happening (executed {obs.trades_executed} today)"

        # Determine reason
        if obs.blocks:
            reason = obs.blocks[0]  # SINGLE dominant reason
            return f"⛔ {scope}: Not trading — {reason}"

        if obs.regime == "PANIC":
            return f"⛔ {scope}: Not trading — in PANIC regime (safety off)"

        if not obs.trading_active:
            return f"⛔ {scope}: Trading inactive"

        if obs.scan_coverage == 0:
            return f"⛔ {scope}: No scan coverage yet"

        return f"⏸ {scope}: No trade signals at this time (regime: {obs.regime})"

    def _explain_trades(self, scope: str, obs: ObservabilitySnapshot) -> str:
        """Why are trades happening?"""
        if obs.trades_executed == 0:
            return f"⏸ {scope}: No trades executed yet today"

        return f"✓ {scope}: {obs.trades_executed} trades executed (regime: {obs.regime}, PnL: ${obs.daily_pnl:,.2f})"

    def _explain_regime(self, scope: str, obs: ObservabilitySnapshot) -> str:
        """What regime are we in?"""
        regime = obs.regime
        emoji_map = {"RISK_ON": "🟢", "NEUTRAL": "🟡", "RISK_OFF": "🔴", "PANIC": "🔴"}
        emoji = emoji_map.get(regime, "❓")

        return f"{emoji} {scope}: {regime}"

    def _explain_blocks(self, scope: str, obs: ObservabilitySnapshot) -> str:
        """Is anything blocked?"""
        if not obs.blocks:
            return f"✓ {scope}: Nothing blocked (trading active)"

        blocks_text = "\n  • ".join(obs.blocks)
        return f"⛔ {scope}: Blocked:\n  • {blocks_text}"

    def _explain_today(self, scope: str, obs: ObservabilitySnapshot) -> str:
        """What happened today?"""
        latest = self.summary_reader.get_latest_summary(scope)
        if not latest:
            return f"⏳ {scope}: No data yet"

        return (
            f"📊 {scope} (today):\n"
            f"  Trades: {latest.trades_executed}\n"
            f"  PnL: ${latest.realized_pnl:,.2f}\n"
            f"  Drawdown: {latest.max_drawdown:.1%}\n"
            f"  Regime: {latest.regime}"
        )

    def _explain_governance(self) -> str:
        """Is governance waiting?"""
        # Simple check: do pending proposals exist?
        try:
            from pathlib import Path

            proposals_dir = Path("logs/governance/crypto/proposals")
            if not proposals_dir.exists():
                return "✓ No governance activity"

            # Count pending (approved/rejected skip)
            pending = 0
            for proposal_dir in proposals_dir.iterdir():
                if proposal_dir.is_dir():
                    if not (proposal_dir / "approval.json").exists() and not (
                        proposal_dir / "rejection.json"
                    ).exists():
                        pending += 1

            if pending == 0:
                return "✓ No pending governance proposals"
            elif pending == 1:
                return "⚠️ 1 governance proposal awaiting your review"
            else:
                return f"⚠️ {pending} governance proposals awaiting review"
        except Exception as e:
            logger.warning(f"Error checking governance: {e}")
            return "❓ Could not check governance status"

    def _explain_status(self, scope: str, obs: ObservabilitySnapshot) -> str:
        """General status."""
        emoji = "🟢" if obs.trading_active else "⏸"
        block_text = f" — {obs.blocks[0]}" if obs.blocks else ""
        return f"{emoji} {scope}: {obs.regime}, {obs.trades_executed} trades{block_text}"

    def _explain_ai_ranking(self, scope: str) -> str:
        """Show latest AI ranking."""
        ranking = self.logs_reader.get_latest_ai_ranking(scope)
        if not ranking:
            return f"📊 {scope}: No AI ranking data yet"

        top_3 = ", ".join(ranking.get("top_3", []))
        return f"🤖 {scope} AI ranking:\n  Top 3: {top_3}\n  ({ranking.get('timestamp', 'unknown time')})"

    def _explain_jobs(self, scope: str) -> str:
        """Show job freshness (last run times)."""
        state = self.logs_reader.get_scheduler_state(scope)
        if not state:
            return f"⏳ {scope}: No scheduler state"

        stale_jobs = []
        fresh_jobs = []

        for job_name, timestamp_str in state.items():
            is_stale = self.logs_reader.job_is_stale(scope, job_name, max_age_seconds=3600)
            if is_stale:
                stale_jobs.append(job_name)
            else:
                fresh_jobs.append(job_name)

        if stale_jobs:
            return f"⚠️ {scope}: Stale jobs: {', '.join(stale_jobs)}"
        else:
            return f"✓ {scope}: All jobs fresh (last hour)"

    def _explain_all_jobs(self) -> str:
        """Check job health across all scopes."""
        all_scopes = [
            "live_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_kraken_crypto_global",
            "paper_alpaca_swing_us",
            "governance",
        ]

        results = []
        for scope in all_scopes:
            state = self.logs_reader.get_scheduler_state(scope)
            if not state:
                continue

            stale_jobs = []
            for job_name in state.keys():
                if self.logs_reader.job_is_stale(scope, job_name, max_age_seconds=3600):
                    stale_jobs.append(job_name)

            if stale_jobs:
                results.append(f"⚠️ {scope}: {', '.join(stale_jobs)}")
            else:
                results.append(f"✓ {scope}: Fresh")

        if not results:
            return "⏳ No job data found"

        return "📋 All containers:\n" + "\n".join(results)

    def _explain_errors(self, scope: str) -> str:
        """Show recent errors from logs."""
        errors = self.logs_reader.get_recent_errors(scope, lines=5)
        if not errors:
            return f"✓ {scope}: No recent errors"

        error_lines = "\n  ".join(errors[:3])
        return f"🚨 {scope}: Recent errors:\n  {error_lines}"

    def _explain_all_errors(self) -> str:
        """Check for errors across all scopes."""
        all_scopes = [
            "live_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_kraken_crypto_global",
            "paper_alpaca_swing_us",
            "governance",
        ]

        results = []
        for scope in all_scopes:
            errors = self.logs_reader.get_recent_errors(scope, lines=3)
            if errors:
                results.append(f"🚨 {scope}:")
                for error in errors[:1]:  # Show just first error per scope
                    results.append(f"  {error[:80]}")
            else:
                results.append(f"✓ {scope}: OK")

        if not results:
            return "⏳ No log data found"

        return "📋 All containers:\n" + "\n".join(results)

    def _explain_all_today(self) -> str:
        """Get today's stats across all scopes."""
        all_scopes = [
            "live_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_kraken_crypto_global",
            "paper_alpaca_swing_us",
        ]

        results = []
        for scope in all_scopes:
            latest = self.summary_reader.get_latest_summary(scope)
            if latest:
                results.append(
                    f"📊 {scope}: {latest.trades_executed} trades, "
                    f"${latest.realized_pnl:,.2f} PnL, {latest.max_drawdown:.1%} DD"
                )
            else:
                results.append(f"⏳ {scope}: No data")

        return "📊 Today across all scopes:\n" + "\n".join(results)

    def _explain_all_ai_rankings(self) -> str:
        """Get AI rankings across all trading scopes."""
        all_scopes = [
            "live_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_kraken_crypto_global",
            "paper_alpaca_swing_us",
        ]

        results = []
        for scope in all_scopes:
            ranking = self.logs_reader.get_latest_ai_ranking(scope)
            if ranking:
                top_3 = ", ".join(ranking.get("top_3", []))
                results.append(f"🤖 {scope}: {top_3}")
            else:
                results.append(f"⏳ {scope}: No ranking data")

        return "🤖 AI Rankings (all scopes):\n" + "\n".join(results)

    def _explain_all_status(self) -> str:
        """Get status across all scopes."""
        all_scopes = [
            "live_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_kraken_crypto_global",
            "paper_alpaca_swing_us",
            "governance",
        ]

        results = []
        for scope in all_scopes:
            if scope == "governance":
                # Governance doesn't have observability data
                pending = 0
                proposals_dir = Path("logs/governance/crypto/proposals")
                if proposals_dir.exists():
                    for proposal_dir in proposals_dir.iterdir():
                        if proposal_dir.is_dir():
                            if not (proposal_dir / "approval.json").exists() and not (
                                proposal_dir / "rejection.json"
                            ).exists():
                                pending += 1
                results.append(f"🏛️ governance: {pending} pending proposals")
            else:
                latest = self.summary_reader.get_latest_summary(scope)
                if latest:
                    emoji = "🟢" if latest.trades_executed > 0 else "⏸"
                    results.append(f"{emoji} {scope}: {latest.regime}, {latest.trades_executed} trades")
                else:
                    results.append(f"⏳ {scope}: No data")

        return "📋 Status (all containers):\n" + "\n".join(results)

    def _explain_holdings(self, scope: str) -> str:
        """Show holdings for a scope."""
        count = self.positions_reader.get_position_count(scope)
        if count == 0:
            return f"💼 {scope}: No open positions"

        summary = self.positions_reader.get_position_summary(scope)
        if not summary:
            return f"💼 {scope}: No holdings data"

        return f"💼 {scope} Holdings ({count} positions):\n{summary}"

    def _explain_all_holdings(self) -> str:
        """Get holdings across all scopes."""
        all_scopes = [
            "live_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_kraken_crypto_global",
            "paper_alpaca_swing_us",
        ]

        results = []
        for scope in all_scopes:
            count = self.positions_reader.get_position_count(scope)
            if count == 0:
                results.append(f"💼 {scope}: No positions")
            else:
                results.append(f"💼 {scope}: {count} open positions")

        return "💼 Holdings (all scopes):\n" + "\n".join(results)

    def _infer_default_scope(self) -> Optional[str]:
        """Infer default scope (try all available scopes, prefer live)."""
        all_scopes = [
            "live_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_kraken_crypto_global",
            "paper_alpaca_swing_us",
        ]

        # First try live scopes
        for scope in all_scopes:
            if "live" in scope:
                latest = self.summary_reader.get_latest_summary(scope)
                if latest:
                    return scope

        # Fall back to paper scopes
        for scope in all_scopes:
            if "paper" in scope:
                latest = self.summary_reader.get_latest_summary(scope)
                if latest:
                    return scope

        return None


def generate_response(intent: Intent, logs_root: str = "logs") -> str:
    """Convenience function."""
    gen = ResponseGenerator(logs_root)
    return gen.generate_response(intent)
