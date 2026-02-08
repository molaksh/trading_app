"""
Agent 4: Synthesizer

Combines proposal, critique, and audit into human-readable decision packet.
"""

from typing import Dict, Any
from governance.schemas import SynthesisSchema


class Synthesizer:
    """Generate human-readable synthesis of all agent outputs."""

    def synthesize(
        self,
        proposal: Dict[str, Any],
        critique: Dict[str, Any],
        audit: Dict[str, Any],
    ) -> SynthesisSchema:
        """
        Combine all agent outputs into synthesis.

        Args:
            proposal: Proposal dict from Proposer
            critique: Critique dict from Critic
            audit: Audit dict from Auditor

        Returns:
            SynthesisSchema instance
        """
        # Generate summary
        summary = self._generate_summary(proposal, critique, audit)

        # Extract key risks
        key_risks = self._extract_key_risks(proposal, critique, audit)

        # Determine final recommendation
        final_recommendation = self._determine_final_recommendation(
            proposal,
            critique,
            audit
        )

        # Calculate final confidence
        confidence = self._calculate_final_confidence(proposal, critique, audit)

        synthesis = SynthesisSchema(
            proposal_id=proposal.get("proposal_id"),
            summary=summary,
            key_risks=key_risks,
            final_recommendation=final_recommendation,
            confidence=confidence,
        )

        return synthesis

    def _generate_summary(
        self,
        proposal: Dict[str, Any],
        critique: Dict[str, Any],
        audit: Dict[str, Any]
    ) -> str:
        """Generate human-readable summary."""
        proposal_type = proposal.get("proposal_type", "UNKNOWN")
        environment = proposal.get("environment", "UNKNOWN")
        symbols = proposal.get("symbols", [])
        symbols_str = ", ".join(symbols[:3])

        # Build summary based on proposal type
        if proposal_type == "ADD_SYMBOLS":
            summary = (
                f"Add {symbols_str} to {environment} trading universe. "
                f"These symbols show strong signals but are underscanned due to capacity. "
                f"Paper results support inclusion."
            )
        elif proposal_type == "REMOVE_SYMBOLS":
            summary = (
                f"Remove {symbols_str} from {environment} trading universe. "
                f"These symbols have poor fill rates and low scan coverage, indicating "
                f"misalignment with current strategy."
            )
        elif proposal_type == "ADJUST_THRESHOLD":
            summary = (
                f"Lower signal threshold in {environment} trading. "
                f"Current universe is under-utilized. Lower threshold by ~5% to capture "
                f"additional signals."
            )
        else:
            summary = (
                f"Adjust {proposal_type.lower()} for {environment} trading. "
                f"Analysis suggests efficiency improvements."
            )

        # Add context if constitutional issues
        if not audit.get("constitution_passed", True):
            summary += " [Constitutional compliance review required]"

        return summary

    def _extract_key_risks(
        self,
        proposal: Dict[str, Any],
        critique: Dict[str, Any],
        audit: Dict[str, Any]
    ) -> list:
        """Extract and prioritize key risks."""
        risks = []

        # Constitutional violations are highest priority
        if not audit.get("constitution_passed", True):
            violations = audit.get("violations", [])
            for v in violations:
                if isinstance(v, dict):
                    risks.append(f"Constitutional violation: {v.get('violation', 'Unknown')}")
                else:
                    risks.append(f"Constitutional violation: {v.violation}")

        # Critic's concerns
        criticisms = critique.get("criticisms", [])
        if criticisms:
            # Add top criticisms as risks
            for criticism in criticisms[:2]:
                if criticism not in risks:
                    risks.append(criticism)

        # Proposal risk notes
        risk_notes = proposal.get("risk_notes", "")
        if risk_notes and risk_notes not in risks:
            risks.append(risk_notes)

        # Ensure at least one risk
        if not risks:
            risks.append("Proceed with caution due to inherent market uncertainty.")

        return risks[:5]  # Limit to 5 key risks

    def _determine_final_recommendation(
        self,
        proposal: Dict[str, Any],
        critique: Dict[str, Any],
        audit: Dict[str, Any]
    ) -> str:
        """Determine final recommendation."""
        # Constitutional violations = automatic REJECT
        if not audit.get("constitution_passed", True):
            return "REJECT"

        # Critic's recommendation is major input
        critic_rec = critique.get("recommendation", "CAUTION")
        if critic_rec == "REJECT":
            return "REJECT"

        # Strong criticism = DEFER for more analysis
        if critic_rec == "CAUTION":
            return "DEFER"

        # Critic says PROCEED + proposal confidence good = APPROVE
        proposal_confidence = proposal.get("confidence", 0.5)
        if critic_rec == "PROCEED" and proposal_confidence > 0.65:
            return "APPROVE"

        # Default to DEFER when uncertain
        return "DEFER"

    def _calculate_final_confidence(
        self,
        proposal: Dict[str, Any],
        critique: Dict[str, Any],
        audit: Dict[str, Any]
    ) -> float:
        """Calculate final confidence (0-1)."""
        # Start with proposal confidence
        confidence = proposal.get("confidence", 0.5)

        # Adjust based on critique
        critic_rec = critique.get("recommendation", "CAUTION")
        if critic_rec == "REJECT":
            confidence *= 0.3
        elif critic_rec == "CAUTION":
            confidence *= 0.6
        elif critic_rec == "PROCEED":
            confidence *= 0.9

        # Penalize if constitutional concerns
        if not audit.get("constitution_passed", True):
            confidence *= 0.2

        # Clamp to [0, 1]
        return min(1.0, max(0.0, confidence))
