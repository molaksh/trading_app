#!/usr/bin/env python3
"""
Approve or reject a pending governance proposal.

Usage:
  python governance/approve_proposal.py --approve <proposal_id> [--notes "notes"]
  python governance/approve_proposal.py --reject <proposal_id> [--reason "reason"]
  python governance/approve_proposal.py --list                  (list pending)
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime


class ProposalApprover:
    """Approve or reject governance proposals."""

    def __init__(self, persist_path: str = "logs"):
        self.persist_path = Path(persist_path)
        self.proposals_dir = self.persist_path / "governance" / "crypto" / "proposals"

    def list_pending(self) -> None:
        """List all pending proposals."""
        if not self.proposals_dir.exists():
            print("No proposals found")
            return

        pending = []
        for proposal_dir in sorted(self.proposals_dir.iterdir()):
            if not proposal_dir.is_dir():
                continue

            approval_file = proposal_dir / "approval.json"
            if approval_file.exists():
                continue  # Skip approved

            try:
                synthesis_file = proposal_dir / "synthesis.json"
                with open(synthesis_file) as f:
                    synthesis = json.load(f)

                proposal_file = proposal_dir / "proposal.json"
                with open(proposal_file) as f:
                    proposal = json.load(f)

                pending.append({
                    "id": proposal["proposal_id"],
                    "env": proposal["environment"],
                    "type": proposal["proposal_type"],
                    "rec": synthesis["final_recommendation"],
                    "conf": f"{synthesis['confidence']:.0%}",
                })
            except:
                continue

        if not pending:
            print("✅ No pending proposals")
            return

        print(f"\n⏳ PENDING PROPOSALS ({len(pending)}):\n")
        print(f"{'ID':<38} {'ENV':<6} {'TYPE':<15} {'REC':<8} {'CONF':<6}")
        print("-" * 80)
        for p in pending:
            print(f"{p['id']:<38} {p['env']:<6} {p['type']:<15} {p['rec']:<8} {p['conf']:<6}")
        print()

    def approve_proposal(self, proposal_id: str, notes: str = "", approved_by: str = "admin") -> None:
        """Approve a proposal."""
        proposal_dir = self.proposals_dir / proposal_id

        if not proposal_dir.exists():
            print(f"❌ Proposal not found: {proposal_id}")
            sys.exit(1)

        approval_file = proposal_dir / "approval.json"
        if approval_file.exists():
            print(f"❌ Proposal already approved: {proposal_id}")
            sys.exit(1)

        # Read proposal to display
        try:
            with open(proposal_dir / "proposal.json") as f:
                proposal = json.load(f)
            with open(proposal_dir / "synthesis.json") as f:
                synthesis = json.load(f)
        except:
            print(f"❌ Error reading proposal files")
            sys.exit(1)

        # Create approval record
        approval_data = {
            "proposal_id": proposal_id,
            "approved_at": datetime.utcnow().isoformat() + "Z",
            "approved_by": approved_by,
            "notes": notes,
            "proposal_type": proposal["proposal_type"],
            "symbols": proposal["symbols"],
            "recommendation": synthesis["final_recommendation"],
            "confidence": synthesis["confidence"],
        }

        # Write approval record
        with open(approval_file, "w") as f:
            json.dump(approval_data, f, indent=2, default=str)

        print(f"\n✅ PROPOSAL APPROVED")
        print(f"   ID: {proposal_id}")
        print(f"   Type: {proposal['proposal_type']}")
        print(f"   Symbols: {', '.join(proposal['symbols'])}")
        print(f"   Recommendation: {synthesis['final_recommendation']}")
        print(f"   Confidence: {synthesis['confidence']:.0%}")
        print(f"   Approved by: {approved_by}")
        if notes:
            print(f"   Notes: {notes}")
        print(f"\n⚠️  NEXT STEPS:")
        print(f"   1. Review approval.json: {approval_file}")
        print(f"   2. Manually edit config/settings based on proposal")
        print(f"   3. Redeploy to apply changes")
        print(f"   4. Document in your change log\n")

    def reject_proposal(self, proposal_id: str, reason: str = "", rejected_by: str = "admin") -> None:
        """Reject a proposal."""
        proposal_dir = self.proposals_dir / proposal_id

        if not proposal_dir.exists():
            print(f"❌ Proposal not found: {proposal_id}")
            sys.exit(1)

        rejection_file = proposal_dir / "rejection.json"
        if rejection_file.exists():
            print(f"❌ Proposal already rejected: {proposal_id}")
            sys.exit(1)

        # Read proposal to display
        try:
            with open(proposal_dir / "proposal.json") as f:
                proposal = json.load(f)
            with open(proposal_dir / "synthesis.json") as f:
                synthesis = json.load(f)
        except:
            print(f"❌ Error reading proposal files")
            sys.exit(1)

        # Create rejection record
        rejection_data = {
            "proposal_id": proposal_id,
            "rejected_at": datetime.utcnow().isoformat() + "Z",
            "rejected_by": rejected_by,
            "reason": reason,
            "proposal_type": proposal["proposal_type"],
            "symbols": proposal["symbols"],
        }

        # Write rejection record
        with open(rejection_file, "w") as f:
            json.dump(rejection_data, f, indent=2, default=str)

        print(f"\n❌ PROPOSAL REJECTED")
        print(f"   ID: {proposal_id}")
        print(f"   Type: {proposal['proposal_type']}")
        print(f"   Symbols: {', '.join(proposal['symbols'])}")
        print(f"   Rejected by: {rejected_by}")
        if reason:
            print(f"   Reason: {reason}")
        print(f"\n✅ Proposal archived (no changes will be applied)\n")


def main():
    parser = argparse.ArgumentParser(description="Approve or reject governance proposals")
    parser.add_argument("--approve", help="Approve proposal (provide proposal_id)")
    parser.add_argument("--reject", help="Reject proposal (provide proposal_id)")
    parser.add_argument("--defer", help="Defer proposal (same as reject, for clarity)")
    parser.add_argument("--list", action="store_true", help="List pending proposals")
    parser.add_argument("--notes", default="", help="Notes for approval")
    parser.add_argument("--reason", default="", help="Reason for rejection/deferral")
    parser.add_argument("--approved-by", default="admin", help="Who approved (default: admin)")
    parser.add_argument("--rejected-by", default="admin", help="Who rejected (default: admin)")
    parser.add_argument("--persist-path", default="logs", help="Persistence path")

    args = parser.parse_args()

    approver = ProposalApprover(args.persist_path)

    if args.list:
        approver.list_pending()
    elif args.approve:
        approver.approve_proposal(args.approve, args.notes, args.approved_by)
    elif args.defer:
        approver.reject_proposal(args.defer, args.reason, args.rejected_by)
    elif args.reject:
        approver.reject_proposal(args.reject, args.reason, args.rejected_by)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
