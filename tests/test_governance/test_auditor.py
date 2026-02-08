"""Test Constitutional Auditor agent."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from governance.agents.auditor import Auditor
from governance.schemas import AuditSchema


@pytest.fixture
def auditor():
    """Create auditor instance."""
    return Auditor()


class TestAuditorValidation:
    """Test auditor validation."""

    def test_audit_valid_proposal(self, auditor):
        """Test auditing a valid proposal."""
        proposal = {
            "proposal_id": "test-123",
            "proposal_type": "ADD_SYMBOLS",
            "non_binding": True,
            "symbols": ["BTC", "ETH"],
            "rationale": "Add BTC and ETH",
            "risk_notes": "Monitor execution costs",
        }

        audit = auditor.audit_proposal(proposal)

        assert isinstance(audit, AuditSchema)
        assert audit.constitution_passed is True
        assert len(audit.violations) == 0

    def test_audit_non_binding_false_fails(self, auditor):
        """Test that non_binding=False fails audit."""
        proposal = {
            "proposal_id": "test-123",
            "proposal_type": "ADD_SYMBOLS",
            "non_binding": False,
            "symbols": ["BTC"],
        }

        audit = auditor.audit_proposal(proposal)

        assert audit.constitution_passed is False
        assert len(audit.violations) > 0
        assert any("non_binding" in str(v.violation).lower() for v in audit.violations)

    def test_audit_forbidden_proposal_type_fails(self, auditor):
        """Test that forbidden proposal type fails."""
        proposal = {
            "proposal_id": "test-123",
            "proposal_type": "EXECUTE_TRADE",
            "non_binding": True,
            "symbols": ["BTC"],
        }

        audit = auditor.audit_proposal(proposal)

        assert audit.constitution_passed is False
        assert len(audit.violations) > 0

    def test_audit_too_many_symbols_fails(self, auditor):
        """Test that adding too many symbols fails."""
        proposal = {
            "proposal_id": "test-123",
            "proposal_type": "ADD_SYMBOLS",
            "non_binding": True,
            "symbols": ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5", "SYM6"],
        }

        audit = auditor.audit_proposal(proposal)

        assert audit.constitution_passed is False
        assert any("too many" in str(v.violation).lower() for v in audit.violations)

    def test_audit_reports_multiple_violations(self, auditor):
        """Test that multiple violations are reported."""
        proposal = {
            "proposal_id": "test-123",
            "proposal_type": "EXECUTE_TRADE",
            "non_binding": False,
            "symbols": [],
            "rationale": "Execute immediately",
        }

        audit = auditor.audit_proposal(proposal)

        assert audit.constitution_passed is False
        assert len(audit.violations) >= 2

    def test_audit_violation_severity_levels(self, auditor):
        """Test that violations have appropriate severity."""
        proposal = {
            "proposal_id": "test-123",
            "proposal_type": "EXECUTE_TRADE",
            "non_binding": False,
            "symbols": ["BTC"],
        }

        audit = auditor.audit_proposal(proposal)

        # All violations should have severity
        for violation in audit.violations:
            assert violation.severity in ["CRITICAL", "MAJOR", "MINOR"]

    def test_audit_zero_market_analysis(self, auditor):
        """Test that auditor does pure compliance checking."""
        # Auditor should not care about market conditions
        proposal = {
            "proposal_id": "test-123",
            "proposal_type": "ADD_SYMBOLS",
            "non_binding": True,
            "symbols": ["BTC"],  # Even if not good timing, auditor doesn't check
            "rationale": "Add BTC to universe",
        }

        audit = auditor.audit_proposal(proposal)

        # Should pass constitution purely
        assert audit.constitution_passed is True
