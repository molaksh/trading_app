#!/usr/bin/env python3
"""
Check for pending governance proposals awaiting human approval.

Usage:
  python governance/check_pending_proposals.py              # List all pending
  python governance/check_pending_proposals.py --summary    # Brief summary
  python governance/check_pending_proposals.py --export     # Export to file for notification
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


class ProposalChecker:
    """Check pending governance proposals."""

    def __init__(self, persist_path: str = "logs"):
        self.persist_path = Path(persist_path)
        self.proposals_dir = self.persist_path / "governance" / "crypto" / "proposals"

    def get_pending_proposals(self) -> List[Dict[str, Any]]:
        """Get all proposals that haven't been approved yet."""
        pending = []

        if not self.proposals_dir.exists():
            return pending

        for proposal_dir in sorted(self.proposals_dir.iterdir()):
            if not proposal_dir.is_dir():
                continue

            # Check if already approved
            approval_file = proposal_dir / "approval.json"
            if approval_file.exists():
                continue  # Skip approved proposals

            # Read synthesis (human-readable decision)
            synthesis_file = proposal_dir / "synthesis.json"
            if not synthesis_file.exists():
                continue

            try:
                with open(synthesis_file) as f:
                    synthesis = json.load(f)

                # Read proposal for details
                proposal_file = proposal_dir / "proposal.json"
                with open(proposal_file) as f:
                    proposal = json.load(f)

                pending.append({
                    "proposal_id": proposal.get("proposal_id"),
                    "environment": proposal.get("environment"),
                    "proposal_type": proposal.get("proposal_type"),
                    "symbols": proposal.get("symbols", []),
                    "summary": synthesis.get("summary"),
                    "recommendation": synthesis.get("final_recommendation"),
                    "confidence": synthesis.get("confidence"),
                    "key_risks": synthesis.get("key_risks", []),
                    "proposal_dir": str(proposal_dir),
                })
            except (json.JSONDecodeError, KeyError):
                continue

        return pending

    def print_summary(self) -> None:
        """Print brief summary of pending proposals."""
        pending = self.get_pending_proposals()

        if not pending:
            print("✅ No pending proposals - all clear!")
            return

        print(f"\n⚠️  PENDING GOVERNANCE PROPOSALS: {len(pending)}")
        print("=" * 80)

        for i, proposal in enumerate(pending, 1):
            print(f"\n{i}. Proposal ID: {proposal['proposal_id']}")
            print(f"   Environment: {proposal['environment']}")
            print(f"   Type: {proposal['proposal_type']}")
            print(f"   Symbols: {', '.join(proposal['symbols'])}")
            print(f"   Summary: {proposal['summary']}")
            print(f"   Recommendation: {proposal['recommendation']}")
            print(f"   Confidence: {proposal['confidence']:.0%}")
            print(f"   Status: ⏳ AWAITING APPROVAL")

        print("\n" + "=" * 80)
        print(f"Total: {len(pending)} proposal(s) pending approval\n")

    def print_detailed(self) -> None:
        """Print detailed information for each proposal."""
        pending = self.get_pending_proposals()

        if not pending:
            print("✅ No pending proposals - all clear!")
            return

        print(f"\n⚠️  PENDING GOVERNANCE PROPOSALS: {len(pending)}")
        print("=" * 80)

        for proposal in pending:
            print(f"\n{'=' * 80}")
            print(f"PROPOSAL ID: {proposal['proposal_id']}")
            print(f"{'=' * 80}")
            print(f"Environment: {proposal['environment']}")
            print(f"Type: {proposal['proposal_type']}")
            print(f"Symbols: {', '.join(proposal['symbols'])}")
            print(f"\nSummary: {proposal['summary']}")
            print(f"\nRecommendation: {proposal['recommendation']}")
            print(f"Confidence: {proposal['confidence']:.0%}")
            print(f"\nKey Risks:")
            for risk in proposal['key_risks']:
                print(f"  - {risk}")
            print(f"\nLocation: {proposal['proposal_dir']}")
            print(f"\nTo review: cat {proposal['proposal_dir']}/synthesis.json")
            print(f"To approve: governance/approve_proposal.py --approve {proposal['proposal_id']}")
            print(f"To reject: governance/approve_proposal.py --reject {proposal['proposal_id']}")

        print("\n" + "=" * 80)

    def export_alert(self, output_file: str = "governance_alert.txt") -> None:
        """Export pending proposals to alert file (for notifications)."""
        pending = self.get_pending_proposals()

        alert_lines = []
        alert_lines.append("=" * 80)
        alert_lines.append("🚨 GOVERNANCE ALERT - PENDING PROPOSALS")
        alert_lines.append("=" * 80)
        alert_lines.append(f"Timestamp: {datetime.now().isoformat()}")
        alert_lines.append(f"Pending: {len(pending)} proposal(s)\n")

        if not pending:
            alert_lines.append("✅ No pending proposals.\n")
        else:
            for i, proposal in enumerate(pending, 1):
                alert_lines.append(f"\n[{i}] PROPOSAL {proposal['proposal_id']}")
                alert_lines.append(f"    Environment: {proposal['environment']}")
                alert_lines.append(f"    Type: {proposal['proposal_type']}")
                alert_lines.append(f"    Summary: {proposal['summary']}")
                alert_lines.append(f"    Recommendation: {proposal['recommendation']}")
                alert_lines.append(f"    Confidence: {proposal['confidence']:.0%}")
                alert_lines.append(f"    Status: AWAITING APPROVAL")
                alert_lines.append(f"    Artifacts: {proposal['proposal_dir']}\n")

        alert_lines.append("=" * 80)
        alert_lines.append("ACTION REQUIRED: Review and approve/reject proposals")
        alert_lines.append("=" * 80)

        alert_text = "\n".join(alert_lines)

        with open(output_file, "w") as f:
            f.write(alert_text)

        print(f"✅ Alert exported to: {output_file}")
        print(alert_text)

    def export_json(self, output_file: str = "governance_pending.json") -> None:
        """Export pending proposals as JSON for programmatic use."""
        pending = self.get_pending_proposals()

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "count": len(pending),
            "proposals": pending,
        }

        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2, default=str)

        print(f"✅ JSON exported to: {output_file}")
        print(json.dumps(output_data, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description="Check pending governance proposals")
    parser.add_argument("--summary", action="store_true", help="Brief summary")
    parser.add_argument("--detailed", action="store_true", help="Detailed view")
    parser.add_argument("--export", action="store_true", help="Export alert to file")
    parser.add_argument("--json", action="store_true", help="Export as JSON")
    parser.add_argument("--output", default="governance_alert.txt", help="Output file")
    parser.add_argument("--persist-path", default="logs", help="Persistence path")

    args = parser.parse_args()

    checker = ProposalChecker(args.persist_path)

    if args.json:
        checker.export_json(args.output.replace(".txt", ".json"))
    elif args.export:
        checker.export_alert(args.output)
    elif args.detailed:
        checker.print_detailed()
    else:
        # Default: summary
        checker.print_summary()


if __name__ == "__main__":
    main()
