"""
Generate concise, deterministic responses to user intents.
"""

import logging
from typing import Optional, Tuple
from datetime import datetime

from ops_agent.schemas import Intent, OpsDiagnostic, ObservabilitySnapshot
from ops_agent.observability_reader import ObservabilityReader
from ops_agent.summary_reader import SummaryReader

logger = logging.getLogger(__name__)


class ResponseGenerator:
    """Generate deterministic ops explanations."""

    def __init__(self, logs_root: str = "logs"):
        self.obs_reader = ObservabilityReader(logs_root)
        self.summary_reader = SummaryReader(logs_root)

    def generate_response(self, intent: Intent) -> str:
        """
        Generate a concise Telegram response for an intent.

        Returns plain text response (no Markdown, no speculation).
        """
        # Infer scope if not provided
        scope = intent.scope or self._infer_default_scope()
        if not scope:
            return "❓ Couldn't determine scope. Try: 'live crypto', 'paper us', etc."

        # Get observability state
        obs = self.obs_reader.get_snapshot(scope)
        if not obs:
            return f"⚠️ No data yet for {scope}. Check back soon."

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

    def _infer_default_scope(self) -> Optional[str]:
        """Infer default scope (live crypto, then live us)."""
        obs_reader = ObservabilityReader()
        if obs_reader.get_snapshot("live_kraken_crypto_global"):
            return "live_kraken_crypto_global"
        if obs_reader.get_snapshot("live_alpaca_swing_us"):
            return "live_alpaca_swing_us"
        return None


def generate_response(intent: Intent, logs_root: str = "logs") -> str:
    """Convenience function."""
    gen = ResponseGenerator(logs_root)
    return gen.generate_response(intent)
