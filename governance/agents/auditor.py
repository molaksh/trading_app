"""
Agent 3: Constitutional Auditor

Enforces constitutional rules. ZERO market analysis.
Only validates format, limits, and constitutional requirements.
"""

from typing import Dict, Any, List
from governance.schemas import AuditSchema, ConstitutionalViolation
from governance import constitution


class Auditor:
    """Enforce constitutional rules on proposals."""

    def audit_proposal(self, proposal: Dict[str, Any]) -> AuditSchema:
        """
        Audit proposal for constitutional compliance.

        Pure validation - no market analysis.

        Args:
            proposal: Proposal dict from Proposer

        Returns:
            AuditSchema instance
        """
        violations = []

        # Run full constitutional validation
        passed, validation_violations = constitution.validate_proposal(proposal)

        # Convert validation violations to ConstitutionalViolation objects
        for violation_msg in validation_violations:
            violation = ConstitutionalViolation(
                rule_name=self._get_rule_name(violation_msg),
                violation=violation_msg,
                severity=self._determine_severity(violation_msg),
            )
            violations.append(violation)

        audit = AuditSchema(
            proposal_id=proposal.get("proposal_id"),
            constitution_passed=passed,
            violations=violations,
        )

        return audit

    def _get_rule_name(self, violation_msg: str) -> str:
        """Extract rule name from violation message."""
        if "non_binding" in violation_msg.lower():
            return "NON_BINDING_REQUIREMENT"
        elif "proposal_type" in violation_msg.lower():
            return "PROPOSAL_TYPE_RESTRICTION"
        elif "symbols" in violation_msg.lower():
            return "SYMBOL_VALIDATION"
        elif "forbidden language" in violation_msg.lower():
            return "FORBIDDEN_LANGUAGE"
        else:
            return "CONSTITUTIONAL_VIOLATION"

    def _determine_severity(self, violation_msg: str) -> str:
        """Determine severity of violation."""
        if "non_binding" in violation_msg.lower():
            return "CRITICAL"
        elif "forbidden" in violation_msg.lower():
            return "CRITICAL"
        elif "proposal_type" in violation_msg.lower():
            return "MAJOR"
        else:
            return "MAJOR"
