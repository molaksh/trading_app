"""Test persistence layer."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
import tempfile
import pytest

from governance.persistence import GovernancePersistence, create_governance_event


@pytest.fixture
def temp_persist_dir():
    """Create temporary persistence directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def persistence(temp_persist_dir):
    """Create persistence instance with temp directory."""
    return GovernancePersistence(temp_persist_dir)


class TestArtifactPersistence:
    """Test artifact writing."""

    def test_write_proposal(self, persistence):
        """Test writing proposal artifact."""
        proposal_data = {
            "proposal_id": "test-123",
            "proposal_type": "ADD_SYMBOLS",
            "symbols": ["BTC"],
        }

        path = persistence.write_proposal("test-123", proposal_data)

        assert Path(path).exists()
        assert "proposal.json" in path

        # Verify content
        with open(path) as f:
            saved = json.load(f)
        assert saved["proposal_id"] == "test-123"

    def test_write_and_read_proposal(self, persistence):
        """Test write and read cycle."""
        proposal_data = {"proposal_id": "test-123", "data": "value"}

        persistence.write_proposal("test-123", proposal_data)
        read_data = persistence.read_proposal("test-123")

        assert read_data == proposal_data

    def test_write_critique(self, persistence):
        """Test writing critique artifact."""
        critique_data = {
            "proposal_id": "test-123",
            "criticisms": ["Risk 1", "Risk 2"],
        }

        path = persistence.write_critique("test-123", critique_data)

        assert Path(path).exists()
        assert "critique.json" in path

    def test_write_audit(self, persistence):
        """Test writing audit artifact."""
        audit_data = {
            "proposal_id": "test-123",
            "constitution_passed": True,
        }

        path = persistence.write_audit("test-123", audit_data)

        assert Path(path).exists()
        assert "audit.json" in path

    def test_write_synthesis(self, persistence):
        """Test writing synthesis artifact."""
        synthesis_data = {
            "proposal_id": "test-123",
            "summary": "Test summary",
            "final_recommendation": "APPROVE",
        }

        path = persistence.write_synthesis("test-123", synthesis_data)

        assert Path(path).exists()
        assert "synthesis.json" in path

    def test_directory_creation(self, persistence):
        """Test that directories are created."""
        persistence.ensure_directories()

        assert persistence.proposals_dir.exists()
        assert persistence.logs_dir.exists()

    def test_proposal_directory_structure(self, persistence):
        """Test proposal directory structure."""
        proposal_dir = persistence.get_proposal_dir("test-123")

        persistence.write_proposal("test-123", {"id": "test-123"})

        assert proposal_dir.exists()
        assert (proposal_dir / "proposal.json").exists()


class TestEventLogging:
    """Test event logging."""

    def test_log_event(self, persistence):
        """Test logging an event."""
        event = create_governance_event(
            "GOVERNANCE_PROPOSAL_CREATED",
            "test-123",
            "paper",
        )

        path = persistence.log_event(event)

        assert Path(path).exists()
        assert "governance_events.jsonl" in path

    def test_event_append_only(self, persistence):
        """Test that events are appended, not overwritten."""
        event1 = create_governance_event("GOVERNANCE_JOB_STARTED")
        event2 = create_governance_event("GOVERNANCE_JOB_COMPLETED")

        persistence.log_event(event1)
        persistence.log_event(event2)

        events = persistence.read_events()

        assert len(events) == 2

    def test_read_events_order(self, persistence):
        """Test that events are read in reverse order (most recent first)."""
        for i in range(3):
            event = create_governance_event("GOVERNANCE_JOB_STARTED", details={"index": i})
            persistence.log_event(event)

        events = persistence.read_events()

        assert len(events) == 3
        # Most recent first
        assert events[0]["details"]["index"] == 2

    def test_read_events_limit(self, persistence):
        """Test reading events with limit."""
        for i in range(5):
            event = create_governance_event("GOVERNANCE_JOB_COMPLETED")
            persistence.log_event(event)

        events = persistence.read_events(limit=2)

        assert len(events) == 2

    def test_read_events_empty(self, persistence):
        """Test reading events when none exist."""
        events = persistence.read_events()

        assert events == []


class TestListProposals:
    """Test listing proposals."""

    def test_list_proposals(self, persistence):
        """Test listing all proposals."""
        persistence.write_proposal("proposal-1", {"id": "1"})
        persistence.write_proposal("proposal-2", {"id": "2"})
        persistence.write_proposal("proposal-3", {"id": "3"})

        proposals = persistence.list_proposals()

        assert len(proposals) == 3
        assert "proposal-1" in proposals
        assert "proposal-2" in proposals

    def test_list_proposals_empty(self, persistence):
        """Test listing when no proposals exist."""
        proposals = persistence.list_proposals()

        assert proposals == []
