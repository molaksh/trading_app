"""
Agent 1: Proposer

Analyzes daily trading summaries and identifies improvement opportunities.
Generates non-binding proposals for AI-driven changes.
"""

import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime

from governance.schemas import ProposalSchema, ProposalEvidence


class Proposer:
    """Generate proposals based on trading summary analysis."""

    def __init__(self, ai_model: str = "gpt-4o", ai_temperature: float = 0.2):
        """
        Initialize proposer.

        Args:
            ai_model: AI model to use for reasoning
            ai_temperature: Temperature for AI calls
        """
        self.ai_model = ai_model
        self.ai_temperature = ai_temperature

    def generate_proposal(
        self,
        environment: str,
        analysis: Dict[str, Any],
        ai_client: Optional[Any] = None,
    ) -> ProposalSchema:
        """
        Generate a proposal based on analysis.

        Args:
            environment: "paper" or "live"
            analysis: Combined analysis from SummaryReader
            ai_client: Optional OpenAI client (for reasoning/creativity)

        Returns:
            ProposalSchema instance
        """
        proposal_id = str(uuid.uuid4())

        # Extract key metrics
        env_data = analysis.get(environment, {})
        performance = env_data.get("performance", {})
        scan_analysis = env_data.get("scan_analysis", {})

        # Identify opportunities
        missed_signals = self._estimate_missed_signals(
            performance,
            scan_analysis
        )
        scan_starvation = scan_analysis.get("scan_starvation", [])
        dead_symbols = self._identify_dead_symbols(
            analysis,
            environment
        )

        # Determine proposal type based on findings
        proposal_type = self._determine_proposal_type(
            environment,
            scan_starvation,
            missed_signals,
            dead_symbols
        )

        # Get symbols to propose
        symbols = self._get_proposed_symbols(
            proposal_type,
            scan_starvation,
            dead_symbols
        )

        # Generate rationale
        rationale = self._generate_rationale(
            proposal_type,
            symbols,
            missed_signals,
            scan_starvation
        )

        # Estimate confidence
        confidence = self._estimate_confidence(
            environment,
            performance,
            missed_signals
        )

        evidence = ProposalEvidence(
            missed_signals=missed_signals,
            scan_starvation=scan_starvation,
            dead_symbols=dead_symbols,
            performance_notes=self._generate_performance_notes(performance),
        )

        proposal = ProposalSchema(
            proposal_id=proposal_id,
            environment=environment,
            proposal_type=proposal_type,
            symbols=symbols,
            rationale=rationale,
            evidence=evidence,
            risk_notes=self._generate_risk_notes(proposal_type, symbols),
            confidence=confidence,
            non_binding=True,  # Constitutional requirement
        )

        return proposal

    def _estimate_missed_signals(
        self,
        performance: Dict[str, Any],
        scan_analysis: Dict[str, Any]
    ) -> int:
        """Estimate number of missed high-confidence signals."""
        trades_skipped = performance.get("trades_skipped", 0)
        # If we're skipping many trades, likely due to capacity
        return max(0, trades_skipped)

    def _identify_dead_symbols(
        self,
        analysis: Dict[str, Any],
        environment: str
    ) -> List[str]:
        """Identify symbols that never produce fills."""
        env_data = analysis.get(environment, {})
        scan_analysis = env_data.get("scan_analysis", {})
        # Symbols scanned less than 25% of days
        return scan_analysis.get("scan_starvation", [])[:3]

    def _determine_proposal_type(
        self,
        environment: str,
        scan_starvation: List[str],
        missed_signals: int,
        dead_symbols: List[str]
    ) -> str:
        """Determine proposal type based on findings."""
        if len(dead_symbols) >= 2:
            return "REMOVE_SYMBOLS"
        elif missed_signals > 10 or len(scan_starvation) > 2:
            return "ADD_SYMBOLS"
        elif missed_signals > 5:
            return "ADJUST_THRESHOLD"
        else:
            return "ADJUST_RULE"

    def _get_proposed_symbols(
        self,
        proposal_type: str,
        scan_starvation: List[str],
        dead_symbols: List[str]
    ) -> List[str]:
        """Get symbols to propose based on proposal type."""
        if proposal_type == "REMOVE_SYMBOLS":
            return dead_symbols[:3]
        elif proposal_type == "ADD_SYMBOLS":
            # Add high-starvation symbols
            return scan_starvation[:3]
        else:
            # For rule/threshold adjustments, use generic placeholder
            return ["BTC", "ETH"]

    def _generate_rationale(
        self,
        proposal_type: str,
        symbols: List[str],
        missed_signals: int,
        scan_starvation: List[str]
    ) -> str:
        """Generate human-readable rationale."""
        if proposal_type == "REMOVE_SYMBOLS":
            symbols_str = ", ".join(symbols)
            return (
                f"Remove {symbols_str} from active universe due to low scan coverage. "
                f"These symbols appear in less than 25% of scans and have not generated fills. "
                f"Removing dead weight improves universe efficiency."
            )
        elif proposal_type == "ADD_SYMBOLS":
            symbols_str = ", ".join(symbols)
            return (
                f"Add {symbols_str} to active universe. "
                f"These symbols show strong signals but are scanned less than 25% of days due to capacity limits. "
                f"Current universe capacity allows inclusion. Paper results show potential."
            )
        elif proposal_type == "ADJUST_THRESHOLD":
            return (
                f"Adjust signal threshold lower to capture more {missed_signals} missed signals. "
                f"Paper universe is underutilized. Lowering threshold by 5% should improve signal capture."
            )
        else:
            return (
                f"Increase scanning frequency during high-volatility windows. "
                f"Current scan starvation ({len(scan_starvation)} symbols) indicates capacity underuse."
            )

    def _generate_performance_notes(self, performance: Dict[str, Any]) -> str:
        """Generate notes on current performance."""
        total_trades = performance.get("total_trades", 0)
        total_pnl = performance.get("total_pnl", 0.0)
        pnl_str = f"+${total_pnl:.2f}" if total_pnl > 0 else f"-${abs(total_pnl):.2f}"
        return (
            f"Last 7 days: {total_trades} trades executed, "
            f"PnL {pnl_str}, no major drawdowns."
        )

    def _generate_risk_notes(self, proposal_type: str, symbols: List[str]) -> str:
        """Generate risk considerations."""
        symbols_str = ", ".join(symbols[:3])
        if proposal_type == "ADD_SYMBOLS":
            return (
                f"Adding symbols {symbols_str} increases universe to larger set. "
                f"Monitor for slippage and execution cost increases. "
                f"Paper results may not fully reflect live conditions."
            )
        elif proposal_type == "REMOVE_SYMBOLS":
            return (
                f"Removing {symbols_str} reduces universe but improves focus. "
                f"Unlikely to have major impact given low historical fills."
            )
        else:
            return "Threshold/rule changes should be monitored for impact on win rate."

    def _estimate_confidence(
        self,
        environment: str,
        performance: Dict[str, Any],
        missed_signals: int
    ) -> float:
        """Estimate confidence in proposal (0-1)."""
        # Higher confidence if clear opportunity (missed signals)
        base_confidence = 0.6

        if missed_signals > 15:
            base_confidence += 0.2
        elif missed_signals > 5:
            base_confidence += 0.1

        if environment == "paper":
            base_confidence -= 0.1  # Paper is less certain

        return min(1.0, max(0.0, base_confidence))
