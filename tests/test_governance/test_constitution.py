"""Test constitutional rules enforcement."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from governance import constitution


class TestProposalTypeValidation:
    """Test proposal_type validation."""

    def test_allowed_proposal_types(self):
        """Test that allowed types pass."""
        for ptype in constitution.ALLOWED_PROPOSAL_TYPES:
            valid, msg = constitution.validate_proposal_type(ptype)
            assert valid, f"Type {ptype} should be allowed"
            assert msg == ""

    def test_forbidden_proposal_types(self):
        """Test that forbidden types fail."""
        for ptype in constitution.FORBIDDEN_PROPOSAL_TYPES:
            valid, msg = constitution.validate_proposal_type(ptype)
            assert not valid, f"Type {ptype} should be forbidden"
            assert "forbidden" in msg.lower()

    def test_invalid_proposal_type(self):
        """Test that invalid types fail."""
        valid, msg = constitution.validate_proposal_type("INVALID_TYPE")
        assert not valid
        assert "not allowed" in msg.lower()


class TestNonBindingValidation:
    """Test non_binding flag validation."""

    def test_non_binding_true_passes(self):
        """Test that non_binding=True passes."""
        valid, msg = constitution.validate_non_binding(True)
        assert valid
        assert msg == ""

    def test_non_binding_false_fails(self):
        """Test that non_binding=False fails."""
        valid, msg = constitution.validate_non_binding(False)
        assert not valid
        assert "non_binding" in msg.lower()


class TestSymbolValidation:
    """Test symbol name validation."""

    def test_valid_symbols(self):
        """Test valid symbol names."""
        symbols = ["BTC", "ETH", "SOL", "LINK", "DOT"]
        valid, msg = constitution.validate_symbols(symbols)
        assert valid
        assert msg == ""

    def test_symbol_with_suffix(self):
        """Test symbols with dash suffix."""
        symbols = ["BTC-USD", "ETH-USD"]
        valid, msg = constitution.validate_symbols(symbols)
        assert valid

    def test_empty_symbols_fails(self):
        """Test that empty symbols list fails."""
        valid, msg = constitution.validate_symbols([])
        assert not valid
        assert "empty" in msg.lower()

    def test_lowercase_symbol_fails(self):
        """Test that lowercase symbols fail."""
        valid, msg = constitution.validate_symbols(["btc", "eth"])
        assert not valid
        assert "format" in msg.lower()

    def test_too_many_symbols_fails(self):
        """Test that too many symbols fails."""
        symbols = [f"SYM{i}" for i in range(15)]
        valid, msg = constitution.validate_symbols(symbols)
        assert not valid

    def test_non_string_symbol_fails(self):
        """Test that non-string symbols fail."""
        valid, msg = constitution.validate_symbols(["BTC", 123, "ETH"])
        assert not valid


class TestSymbolCountByType:
    """Test symbol count limits by proposal type."""

    def test_add_symbols_limit(self):
        """Test ADD_SYMBOLS limit."""
        symbols = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]
        valid, msg = constitution.validate_symbol_count_by_type("ADD_SYMBOLS", symbols)
        assert valid

        symbols_over = ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5", "SYM6"]
        valid, msg = constitution.validate_symbol_count_by_type("ADD_SYMBOLS", symbols_over)
        assert not valid

    def test_remove_symbols_limit(self):
        """Test REMOVE_SYMBOLS limit."""
        symbols = ["SYM1", "SYM2", "SYM3"]
        valid, msg = constitution.validate_symbol_count_by_type("REMOVE_SYMBOLS", symbols)
        assert valid

        symbols_over = ["SYM1", "SYM2", "SYM3", "SYM4"]
        valid, msg = constitution.validate_symbol_count_by_type("REMOVE_SYMBOLS", symbols_over)
        assert not valid


class TestForbiddenLanguage:
    """Test detection of forbidden execution language."""

    def test_forbidden_keywords(self):
        """Test detection of forbidden keywords."""
        forbidden_texts = [
            "Execute trade immediately",
            "Auto-apply these changes",
            "Bypass the risk check",
            "Override the threshold",
            "Force this change",
        ]

        for text in forbidden_texts:
            valid, msg = constitution.validate_no_forbidden_language(text)
            assert not valid, f"Should reject: {text}"
            assert "forbidden" in msg.lower()

    def test_allowed_text(self):
        """Test that normal text passes."""
        texts = [
            "Add BTC and ETH to the universe",
            "Recommend removing dead symbols",
            "Consider adjusting threshold",
        ]

        for text in texts:
            valid, msg = constitution.validate_no_forbidden_language(text)
            assert valid, f"Should allow: {text}"


class TestFullProposalValidation:
    """Test full proposal validation."""

    def test_valid_proposal(self):
        """Test that valid proposal passes."""
        proposal = {
            "proposal_id": "test-id",
            "proposal_type": "ADD_SYMBOLS",
            "non_binding": True,
            "symbols": ["BTC", "ETH"],
            "rationale": "Add BTC and ETH to improve coverage",
            "risk_notes": "Liquidity is good for these symbols",
        }
        passed, violations = constitution.validate_proposal(proposal)
        assert passed
        assert len(violations) == 0

    def test_non_binding_false_fails(self):
        """Test that non_binding=False fails."""
        proposal = {
            "proposal_id": "test-id",
            "proposal_type": "ADD_SYMBOLS",
            "non_binding": False,
            "symbols": ["BTC"],
        }
        passed, violations = constitution.validate_proposal(proposal)
        assert not passed
        assert any("non_binding" in v.lower() for v in violations)

    def test_forbidden_proposal_type_fails(self):
        """Test that forbidden proposal type fails."""
        proposal = {
            "proposal_id": "test-id",
            "proposal_type": "EXECUTE_TRADE",
            "non_binding": True,
            "symbols": ["BTC"],
        }
        passed, violations = constitution.validate_proposal(proposal)
        assert not passed

    def test_forbidden_language_in_rationale_fails(self):
        """Test that forbidden language in rationale fails."""
        proposal = {
            "proposal_id": "test-id",
            "proposal_type": "ADD_SYMBOLS",
            "non_binding": True,
            "symbols": ["BTC"],
            "rationale": "Execute this proposal immediately",
        }
        passed, violations = constitution.validate_proposal(proposal)
        assert not passed
        assert any("forbidden" in v.lower() for v in violations)

    def test_multiple_violations_reported(self):
        """Test that multiple violations are reported."""
        proposal = {
            "proposal_id": "test-id",
            "proposal_type": "EXECUTE_TRADE",
            "non_binding": False,
            "symbols": [],
            "rationale": "Execute this now",
        }
        passed, violations = constitution.validate_proposal(proposal)
        assert not passed
        # Should report multiple issues
        assert len(violations) >= 2
