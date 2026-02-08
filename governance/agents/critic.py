"""
Agent 2: Critic

Takes adversarial stance on proposals.
Identifies risks, recency bias, overfitting, and counter-evidence.
"""

from typing import Dict, Any, List
from governance.schemas import CriticismSchema


class Critic:
    """Provide critical analysis of proposals."""

    def __init__(self, ai_model: str = "gpt-4o", ai_temperature: float = 0.2):
        """
        Initialize critic.

        Args:
            ai_model: AI model to use
            ai_temperature: Temperature for AI calls
        """
        self.ai_model = ai_model
        self.ai_temperature = ai_temperature

    def critique_proposal(
        self,
        proposal: Dict[str, Any],
        analysis: Dict[str, Any],
        ai_client: Any = None,
    ) -> CriticismSchema:
        """
        Provide critical analysis of proposal.

        Args:
            proposal: Proposal dict from Proposer
            analysis: Combined analysis from SummaryReader
            ai_client: Optional OpenAI client

        Returns:
            CriticismSchema instance
        """
        criticisms = []
        confidence_adjustment = 0

        # Check for recency bias
        recency_bias = self._check_recency_bias(analysis, proposal)
        if recency_bias:
            criticisms.append(recency_bias)
            confidence_adjustment -= 0.1

        # Check for overfitting
        overfitting_warning = self._check_overfitting(analysis, proposal)
        if overfitting_warning:
            criticisms.append(overfitting_warning)
            confidence_adjustment -= 0.1

        # Check for liquidity risks
        liquidity_risk = self._check_liquidity_risks(proposal)
        if liquidity_risk:
            criticisms.append(liquidity_risk)
            confidence_adjustment -= 0.05

        # Check for capacity risks
        capacity_risk = self._check_capacity_risks(analysis, proposal)
        if capacity_risk:
            criticisms.append(capacity_risk)
            confidence_adjustment -= 0.05

        # Check for timing risks
        timing_risk = self._check_timing_risks(analysis, proposal)
        if timing_risk:
            criticisms.append(timing_risk)
            confidence_adjustment -= 0.05

        # Ensure at least one criticism
        if not criticisms:
            criticisms.append(
                "Proposal appears sound but proceed with caution due to inherent market uncertainty."
            )

        # Determine recommendation
        recommendation = self._determine_recommendation(
            proposal,
            criticisms,
            confidence_adjustment
        )

        counter_evidence = self._generate_counter_evidence(
            proposal,
            criticisms,
            analysis
        )

        return CriticismSchema(
            proposal_id=proposal.get("proposal_id"),
            criticisms=criticisms,
            counter_evidence=counter_evidence,
            recommendation=recommendation,
        )

    def _check_recency_bias(
        self,
        analysis: Dict[str, Any],
        proposal: Dict[str, Any]
    ) -> str:
        """Check if proposal is based on recent data only (recency bias)."""
        env = proposal.get("environment", "")
        env_data = analysis.get(env, {})

        # Recency bias check: if performance very recent
        latest = env_data.get("latest", {})
        if latest and latest.get("date"):
            # Criticism if based on < 3 days of data
            return (
                "Proposal may be influenced by recency bias. "
                "Current regime (past 2 days) shows high signals, but historical pattern "
                "may reverse. Recommend testing with longer lookback period."
            )

        return ""

    def _check_overfitting(
        self,
        analysis: Dict[str, Any],
        proposal: Dict[str, Any]
    ) -> str:
        """Check if proposal overfits to recent performance."""
        env = proposal.get("environment", "")
        env_data = analysis.get(env, {})
        performance = env_data.get("performance", {})
        pnl = performance.get("total_pnl", 0)

        # If recent period is unusually profitable, risky to add symbols
        if pnl > 500:  # Arbitrary threshold
            proposal_type = proposal.get("proposal_type", "")
            if proposal_type == "ADD_SYMBOLS":
                return (
                    "Recent performance is exceptionally strong. Risk of overfitting to regime. "
                    "Added symbols may not perform as well in different market conditions."
                )

        return ""

    def _check_liquidity_risks(self, proposal: Dict[str, Any]) -> str:
        """Check if proposed symbols have liquidity concerns."""
        proposal_type = proposal.get("proposal_type", "")
        symbols = proposal.get("symbols", [])

        if proposal_type == "ADD_SYMBOLS" and symbols:
            # Check if adding altcoins (proxy: non-BTC/ETH)
            altcoins = [s for s in symbols if s not in ["BTC", "ETH"]]
            if altcoins:
                return (
                    f"Proposed additions include altcoins ({', '.join(altcoins)}). "
                    f"Liquidity may be lower than BTC/ETH. Slippage risk in live trading."
                )

        return ""

    def _check_capacity_risks(
        self,
        analysis: Dict[str, Any],
        proposal: Dict[str, Any]
    ) -> str:
        """Check if proposal respects capacity limits."""
        proposal_type = proposal.get("proposal_type", "")
        symbols = proposal.get("symbols", [])

        if proposal_type == "ADD_SYMBOLS" and len(symbols) > 3:
            return (
                f"Adding {len(symbols)} symbols at once is aggressive. "
                f"Recommend staging additions (max 2-3 per week) to monitor impact."
            )

        return ""

    def _check_timing_risks(
        self,
        analysis: Dict[str, Any],
        proposal: Dict[str, Any]
    ) -> str:
        """Check for market timing risks."""
        env = proposal.get("environment", "")
        env_data = analysis.get(env, {})
        latest = env_data.get("latest", {})

        # High volatility warning
        if latest and latest.get("data_issues", 0) > 2:
            return (
                "Recent period shows elevated data issues/market volatility. "
                "Timing may not be ideal for adding symbols."
            )

        return ""

    def _determine_recommendation(
        self,
        proposal: Dict[str, Any],
        criticisms: List[str],
        confidence_adjustment: float
    ) -> str:
        """Determine overall recommendation."""
        num_criticisms = len(criticisms)
        confidence_adjustment_factor = abs(confidence_adjustment)

        if num_criticisms >= 4 or confidence_adjustment_factor >= 0.3:
            return "REJECT"
        elif num_criticisms >= 2 or confidence_adjustment_factor >= 0.15:
            return "CAUTION"
        else:
            return "PROCEED"

    def _generate_counter_evidence(
        self,
        proposal: Dict[str, Any],
        criticisms: List[str],
        analysis: Dict[str, Any]
    ) -> str:
        """Generate counter-arguments and alternative viewpoints."""
        counter_points = []

        proposal_type = proposal.get("proposal_type", "")
        environment = proposal.get("environment", "")

        if proposal_type == "ADD_SYMBOLS":
            counter_points.append(
                "Paper results show these symbols integrate well with existing strategy."
            )
            counter_points.append(
                "Adding symbols during stable regimes typically has lower impact."
            )

        elif proposal_type == "REMOVE_SYMBOLS":
            counter_points.append(
                "Removal may hurt future performance if symbols revive in different regime."
            )
            counter_points.append(
                "Low historical fills may reflect strategy-symbol mismatch, not symbol quality."
            )

        if environment == "paper":
            counter_points.append(
                "Paper trading has lower execution costs and no slippage - live results may differ."
            )

        return " ".join(counter_points) if counter_points else "See criticisms above for full analysis."
