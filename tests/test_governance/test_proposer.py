"""Test Proposer agent."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from governance.agents.proposer import Proposer
from governance.schemas import ProposalSchema


@pytest.fixture
def proposer():
    """Create proposer instance."""
    return Proposer()


@pytest.fixture
def mock_analysis():
    """Mock trading analysis."""
    return {
        "paper": {
            "summaries_count": 5,
            "latest": {"date": "2026-02-08", "ai_last_ranking": {"ranked_symbols": ["BTC", "ETH", "SOL"]}},
            "performance": {
                "total_trades": 10,
                "trades_skipped": 5,
                "total_pnl": 150.0,
                "max_drawdown": -2.0,
                "data_issues": 0,
            },
            "scan_analysis": {
                "total_days": 5,
                "avg_scan_symbols": 3.0,
                "scan_starvation": ["LINK", "DOT"],
                "scan_counts": {"BTC": 5, "ETH": 5, "SOL": 5, "LINK": 1, "DOT": 0},
            },
        },
        "live": {
            "summaries_count": 5,
            "latest": {"date": "2026-02-08"},
            "performance": {
                "total_trades": 0,
                "trades_skipped": 0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
                "data_issues": 0,
            },
            "scan_analysis": {
                "total_days": 5,
                "avg_scan_symbols": 3.0,
                "scan_starvation": [],
            },
        },
    }


class TestProposerGeneration:
    """Test proposal generation."""

    def test_generate_proposal_paper(self, proposer, mock_analysis):
        """Test generating proposal for paper environment."""
        proposal = proposer.generate_proposal("paper", mock_analysis)

        assert isinstance(proposal, ProposalSchema)
        assert proposal.proposal_id
        assert proposal.environment == "paper"
        assert proposal.non_binding is True
        assert proposal.proposal_type in [
            "ADD_SYMBOLS",
            "REMOVE_SYMBOLS",
            "ADJUST_RULE",
            "ADJUST_THRESHOLD",
        ]
        assert len(proposal.symbols) > 0
        assert proposal.confidence >= 0.0 and proposal.confidence <= 1.0

    def test_generate_proposal_live(self, proposer, mock_analysis):
        """Test generating proposal for live environment."""
        proposal = proposer.generate_proposal("live", mock_analysis)

        assert isinstance(proposal, ProposalSchema)
        assert proposal.environment == "live"
        assert proposal.non_binding is True

    def test_proposal_has_valid_symbols(self, proposer, mock_analysis):
        """Test that proposals have valid symbols."""
        proposal = proposer.generate_proposal("paper", mock_analysis)

        for symbol in proposal.symbols:
            assert isinstance(symbol, str)
            assert symbol.isupper()

    def test_proposal_has_rationale(self, proposer, mock_analysis):
        """Test that proposal has meaningful rationale."""
        proposal = proposer.generate_proposal("paper", mock_analysis)

        assert proposal.rationale
        assert len(proposal.rationale) > 10

    def test_proposal_identifies_scan_starvation(self, proposer, mock_analysis):
        """Test that proposer identifies scan starvation."""
        proposal = proposer.generate_proposal("paper", mock_analysis)

        # With scan starvation present, should identify it
        assert proposal.evidence.scan_starvation or proposal.proposal_type == "ADJUST_RULE"

    def test_proposal_confidence_reasonable(self, proposer, mock_analysis):
        """Test that confidence is reasonable."""
        proposal = proposer.generate_proposal("paper", mock_analysis)

        # Should be conservative (< 1.0)
        assert proposal.confidence < 0.95

    def test_proposal_has_risk_notes(self, proposer, mock_analysis):
        """Test that risk notes are generated."""
        proposal = proposer.generate_proposal("paper", mock_analysis)

        assert proposal.risk_notes
        assert len(proposal.risk_notes) > 0
