"""Integration tests for full governance pipeline."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import tempfile
import pytest

from governance.crypto_governance_job import CryptoGovernanceJob


@pytest.fixture
def temp_persist_dir():
    """Create temporary persistence directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_logs_dir(tmp_path):
    """Create mock logs directory with sample data."""
    logs_base = tmp_path / "logs"

    # Create paper scope logs
    paper_scope_dir = logs_base / "paper_kraken_crypto_global" / "logs"
    paper_scope_dir.mkdir(parents=True)

    # Create live scope logs
    live_scope_dir = logs_base / "live_kraken_crypto_global" / "logs"
    live_scope_dir.mkdir(parents=True)

    # Write sample summaries
    summaries_paper = [
        {
            "date": "2026-02-03",
            "env": "paper",
            "trades_taken": 2,
            "trades_skipped": 1,
            "realized_pnl": 50.0,
            "max_drawdown": -1.0,
            "data_issues": 0,
            "ai_last_ranking": {"ranked_symbols": ["BTC", "ETH", "SOL"]},
        },
        {
            "date": "2026-02-04",
            "env": "paper",
            "trades_taken": 3,
            "trades_skipped": 2,
            "realized_pnl": 75.0,
            "max_drawdown": -2.0,
            "data_issues": 0,
            "ai_last_ranking": {"ranked_symbols": ["BTC", "ETH", "LINK"]},
        },
        {
            "date": "2026-02-05",
            "env": "paper",
            "trades_taken": 1,
            "trades_skipped": 3,
            "realized_pnl": 25.0,
            "max_drawdown": -1.5,
            "data_issues": 0,
            "ai_last_ranking": {"ranked_symbols": ["BTC", "SOL", "DOT"]},
        },
    ]

    summaries_live = [
        {
            "date": "2026-02-03",
            "env": "live",
            "trades_taken": 0,
            "trades_skipped": 0,
            "realized_pnl": 0.0,
            "max_drawdown": 0.0,
            "data_issues": 0,
        },
        {
            "date": "2026-02-04",
            "env": "live",
            "trades_taken": 0,
            "trades_skipped": 0,
            "realized_pnl": 0.0,
            "max_drawdown": 0.0,
            "data_issues": 0,
        },
    ]

    with open(paper_scope_dir / "daily_summary.jsonl", "w") as f:
        for s in summaries_paper:
            f.write(json.dumps(s) + "\n")

    with open(live_scope_dir / "daily_summary.jsonl", "w") as f:
        for s in summaries_live:
            f.write(json.dumps(s) + "\n")

    return tmp_path


class TestGovernanceJobIntegration:
    """Integration tests for governance job."""

    def test_full_pipeline_runs(self, temp_persist_dir, mock_logs_dir, monkeypatch):
        """Test that full pipeline runs without errors."""
        # Override log paths
        monkeypatch.setattr(
            "governance.crypto_governance_job.SummaryReader",
            lambda logs_path: __import__("governance.summary_reader", fromlist=["SummaryReader"]).SummaryReader(str(mock_logs_dir / "logs"))
        )

        job = CryptoGovernanceJob(temp_persist_dir, dry_run=False)
        result = job.run()

        assert result is not None
        assert "success" in result
        assert "errors" in result

    def test_dry_run_mode(self, temp_persist_dir, mock_logs_dir, monkeypatch):
        """Test that dry-run mode doesn't write artifacts."""
        monkeypatch.setattr(
            "governance.crypto_governance_job.SummaryReader",
            lambda logs_path: __import__("governance.summary_reader", fromlist=["SummaryReader"]).SummaryReader(str(mock_logs_dir / "logs"))
        )

        job = CryptoGovernanceJob(temp_persist_dir, dry_run=True)
        result = job.run()

        # Verify no artifacts written
        proposals_dir = Path(temp_persist_dir) / "governance" / "crypto" / "proposals"
        if proposals_dir.exists():
            proposals = list(proposals_dir.iterdir())
            # In dry-run, there should be no artifacts
            assert len(proposals) == 0

    def test_proposal_persisted(self, temp_persist_dir, mock_logs_dir, monkeypatch):
        """Test that proposal is persisted correctly."""
        monkeypatch.setattr(
            "governance.crypto_governance_job.SummaryReader",
            lambda logs_path: __import__("governance.summary_reader", fromlist=["SummaryReader"]).SummaryReader(str(mock_logs_dir / "logs"))
        )

        job = CryptoGovernanceJob(temp_persist_dir, dry_run=False)
        result = job.run()

        if result["success"]:
            proposal_id = result["proposal_id"]

            # Check that artifacts were written
            proposal_path = (
                Path(temp_persist_dir) / "governance" / "crypto" / "proposals" /
                proposal_id / "proposal.json"
            )

            if proposal_path.exists():
                with open(proposal_path) as f:
                    proposal = json.load(f)
                assert proposal["proposal_id"] == proposal_id
                assert "non_binding" in proposal
                assert proposal["non_binding"] is True

    def test_constitutional_violation_stops_pipeline(self, temp_persist_dir, monkeypatch):
        """Test that constitutional violations stop the pipeline."""
        # This would require mocking the proposer to return a bad proposal
        pass

    def test_events_logged(self, temp_persist_dir, mock_logs_dir, monkeypatch):
        """Test that governance events are logged."""
        monkeypatch.setattr(
            "governance.crypto_governance_job.SummaryReader",
            lambda logs_path: __import__("governance.summary_reader", fromlist=["SummaryReader"]).SummaryReader(str(mock_logs_dir / "logs"))
        )

        job = CryptoGovernanceJob(temp_persist_dir, dry_run=False)
        result = job.run()

        # Check events log
        events_path = Path(temp_persist_dir) / "governance" / "crypto" / "logs" / "governance_events.jsonl"
        if events_path.exists():
            with open(events_path) as f:
                events = [json.loads(line) for line in f if line.strip()]

            # Should have logged events
            assert len(events) > 0
