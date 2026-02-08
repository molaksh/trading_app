"""
Append-only persistence for governance artifacts and events.

All outputs are written to immutable JSONL format in governance-specific directories.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from governance.schemas import GovernanceEvent


class GovernancePersistence:
    """Manage append-only artifact and event persistence."""

    def __init__(self, base_path: str = "persist"):
        """
        Initialize persistence manager.

        Args:
            base_path: Base persistence directory (usually 'persist')
        """
        self.base_path = Path(base_path)
        self.governance_base = self.base_path / "governance" / "crypto"
        self.proposals_dir = self.governance_base / "proposals"
        self.logs_dir = self.governance_base / "logs"

    def ensure_directories(self) -> None:
        """Create all necessary directories."""
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def get_proposal_dir(self, proposal_id: str) -> Path:
        """Get directory for a specific proposal."""
        return self.proposals_dir / proposal_id

    def write_proposal(self, proposal_id: str, proposal_data: Dict[str, Any]) -> str:
        """
        Write proposal.json to proposal directory.

        Args:
            proposal_id: Unique proposal identifier
            proposal_data: Proposal dict

        Returns:
            Path to written file
        """
        self.ensure_directories()
        proposal_dir = self.get_proposal_dir(proposal_id)
        proposal_dir.mkdir(parents=True, exist_ok=True)

        proposal_path = proposal_dir / "proposal.json"
        with open(proposal_path, "w") as f:
            json.dump(proposal_data, f, indent=2, default=str)

        return str(proposal_path)

    def write_critique(self, proposal_id: str, critique_data: Dict[str, Any]) -> str:
        """
        Write critique.json to proposal directory.

        Args:
            proposal_id: Unique proposal identifier
            critique_data: Critique dict

        Returns:
            Path to written file
        """
        self.ensure_directories()
        proposal_dir = self.get_proposal_dir(proposal_id)
        proposal_dir.mkdir(parents=True, exist_ok=True)

        critique_path = proposal_dir / "critique.json"
        with open(critique_path, "w") as f:
            json.dump(critique_data, f, indent=2, default=str)

        return str(critique_path)

    def write_audit(self, proposal_id: str, audit_data: Dict[str, Any]) -> str:
        """
        Write audit.json to proposal directory.

        Args:
            proposal_id: Unique proposal identifier
            audit_data: Audit dict

        Returns:
            Path to written file
        """
        self.ensure_directories()
        proposal_dir = self.get_proposal_dir(proposal_id)
        proposal_dir.mkdir(parents=True, exist_ok=True)

        audit_path = proposal_dir / "audit.json"
        with open(audit_path, "w") as f:
            json.dump(audit_data, f, indent=2, default=str)

        return str(audit_path)

    def write_synthesis(self, proposal_id: str, synthesis_data: Dict[str, Any]) -> str:
        """
        Write synthesis.json to proposal directory.

        Args:
            proposal_id: Unique proposal identifier
            synthesis_data: Synthesis dict

        Returns:
            Path to written file
        """
        self.ensure_directories()
        proposal_dir = self.get_proposal_dir(proposal_id)
        proposal_dir.mkdir(parents=True, exist_ok=True)

        synthesis_path = proposal_dir / "synthesis.json"
        with open(synthesis_path, "w") as f:
            json.dump(synthesis_data, f, indent=2, default=str)

        return str(synthesis_path)

    def write_approval(
        self,
        proposal_id: str,
        approval_data: Dict[str, Any]
    ) -> str:
        """
        Write approval.json to proposal directory (human approval record).

        Args:
            proposal_id: Unique proposal identifier
            approval_data: Approval dict

        Returns:
            Path to written file
        """
        self.ensure_directories()
        proposal_dir = self.get_proposal_dir(proposal_id)
        proposal_dir.mkdir(parents=True, exist_ok=True)

        approval_path = proposal_dir / "approval.json"
        with open(approval_path, "w") as f:
            json.dump(approval_data, f, indent=2, default=str)

        return str(approval_path)

    def log_event(self, event: GovernanceEvent) -> str:
        """
        Append event to governance_events.jsonl (append-only).

        Args:
            event: GovernanceEvent to log

        Returns:
            Path to log file
        """
        self.ensure_directories()
        events_path = self.logs_dir / "governance_events.jsonl"

        event_dict = json.loads(event.json())
        with open(events_path, "a") as f:
            f.write(json.dumps(event_dict) + "\n")

        return str(events_path)

    def read_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Read proposal.json for a proposal."""
        proposal_path = self.get_proposal_dir(proposal_id) / "proposal.json"
        if not proposal_path.exists():
            return None

        with open(proposal_path) as f:
            return json.load(f)

    def read_critique(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Read critique.json for a proposal."""
        critique_path = self.get_proposal_dir(proposal_id) / "critique.json"
        if not critique_path.exists():
            return None

        with open(critique_path) as f:
            return json.load(f)

    def read_audit(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Read audit.json for a proposal."""
        audit_path = self.get_proposal_dir(proposal_id) / "audit.json"
        if not audit_path.exists():
            return None

        with open(audit_path) as f:
            return json.load(f)

    def read_synthesis(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Read synthesis.json for a proposal."""
        synthesis_path = self.get_proposal_dir(proposal_id) / "synthesis.json"
        if not synthesis_path.exists():
            return None

        with open(synthesis_path) as f:
            return json.load(f)

    def read_approval(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        """Read approval.json for a proposal."""
        approval_path = self.get_proposal_dir(proposal_id) / "approval.json"
        if not approval_path.exists():
            return None

        with open(approval_path) as f:
            return json.load(f)

    def list_proposals(self) -> List[str]:
        """List all proposal IDs."""
        self.ensure_directories()
        if not self.proposals_dir.exists():
            return []

        return [d.name for d in self.proposals_dir.iterdir() if d.is_dir()]

    def read_events(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Read governance events from JSONL.

        Args:
            limit: Maximum number of events to return (most recent first)

        Returns:
            List of event dicts
        """
        events_path = self.logs_dir / "governance_events.jsonl"
        if not events_path.exists():
            return []

        events = []
        with open(events_path) as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        # Return most recent first
        if limit:
            return list(reversed(events))[:limit]
        return list(reversed(events))


def create_governance_event(
    event_type: str,
    proposal_id: Optional[str] = None,
    environment: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> GovernanceEvent:
    """
    Create a governance event.

    Args:
        event_type: Type of event
        proposal_id: Associated proposal ID
        environment: paper or live
        details: Additional details

    Returns:
        GovernanceEvent instance
    """
    return GovernanceEvent(
        timestamp=datetime.utcnow().isoformat() + "Z",
        event_type=event_type,
        proposal_id=proposal_id,
        environment=environment,
        details=details or {},
    )
