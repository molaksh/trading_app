"""
Governance Job Orchestrator

Coordinates the 4-agent pipeline for Phase C governance.
Runs independently from trading containers.
"""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from config.governance_settings import (
    GOVERNANCE_LOOKBACK_DAYS,
    PAPER_SCOPE,
    LIVE_SCOPE,
)
from governance.summary_reader import SummaryReader
from governance.agents.proposer import Proposer
from governance.agents.critic import Critic
from governance.agents.auditor import Auditor
from governance.agents.synthesizer import Synthesizer
from governance.persistence import (
    GovernancePersistence,
    create_governance_event,
)

logger = logging.getLogger(__name__)


class CryptoGovernanceJob:
    """Main governance orchestrator."""

    def __init__(self, persist_path: str = "persist", dry_run: bool = False):
        """
        Initialize governance job.

        Args:
            persist_path: Base persistence directory
            dry_run: If True, don't write artifacts (for testing)
        """
        self.persist = GovernancePersistence(persist_path)
        self.summary_reader = SummaryReader("logs")
        self.proposer = Proposer()
        self.critic = Critic()
        self.auditor = Auditor()
        self.synthesizer = Synthesizer()
        self.dry_run = dry_run

    def run(self) -> Dict[str, Any]:
        """
        Execute full governance pipeline.

        Flow:
          1. Read summaries (paper + live)
          2. Generate proposal (Agent 1)
          3. Critique proposal (Agent 2)
          4. Audit proposal (Agent 3)
          5. If audit passes, synthesize (Agent 4)
          6. Persist all artifacts
          7. Exit (no application)

        Returns:
            Dict with pipeline results
        """
        logger.info("Starting crypto governance job")
        result = {
            "success": False,
            "proposal_id": None,
            "proposal": None,
            "critique": None,
            "audit": None,
            "synthesis": None,
            "errors": [],
        }

        try:
            # Phase 1: Read summaries
            logger.info("Reading trading summaries...")
            analysis = self.summary_reader.get_combined_analysis(
                PAPER_SCOPE,
                LIVE_SCOPE,
                GOVERNANCE_LOOKBACK_DAYS
            )
            logger.info(f"Loaded {analysis['paper']['summaries_count']} paper and "
                       f"{analysis['live']['summaries_count']} live summaries")

            # Phase 2: Generate proposals (for each environment)
            proposals_generated = []
            for environment in ["paper", "live"]:
                logger.info(f"Generating proposal for {environment} environment...")
                try:
                    proposal = self.proposer.generate_proposal(environment, analysis)
                    proposals_generated.append(proposal)
                    logger.info(f"Generated proposal {proposal.proposal_id} for {environment}")
                except Exception as e:
                    logger.warning(f"Failed to generate proposal for {environment}: {e}")

            if not proposals_generated:
                result["errors"].append("No proposals generated")
                self._log_job_event("GOVERNANCE_JOB_FAILED", details={"reason": "No proposals"})
                logger.warning("Governance job found no proposal opportunities")
                return result

            # Process first proposal (could extend to handle multiple)
            proposal = proposals_generated[0]
            result["proposal_id"] = proposal.proposal_id
            result["proposal"] = proposal.dict()

            # Phase 3: Critique
            logger.info(f"Critiquing proposal {proposal.proposal_id}...")
            critique = self.critic.critique_proposal(proposal.dict(), analysis)
            result["critique"] = critique.dict()
            logger.info(f"Critique recommendation: {critique.recommendation}")

            # Phase 4: Audit
            logger.info(f"Auditing proposal {proposal.proposal_id}...")
            audit = self.auditor.audit_proposal(proposal.dict())
            result["audit"] = audit.dict()
            logger.info(f"Constitutional compliance: {audit.constitution_passed}")

            if not audit.constitution_passed:
                logger.warning(f"Constitutional violations detected: {audit.violations}")
                self._log_job_event(
                    "GOVERNANCE_CONSTITUTION_VIOLATION",
                    proposal.proposal_id,
                    proposal.environment,
                    {"violations": [v.dict() for v in audit.violations]},
                )
                if not self.dry_run:
                    self.persist.write_proposal(proposal.proposal_id, proposal.dict())
                    self.persist.write_critique(proposal.proposal_id, critique.dict())
                    self.persist.write_audit(proposal.proposal_id, audit.dict())
                result["errors"].append("Constitutional audit failed")
                return result

            # Phase 5: Synthesize
            logger.info(f"Synthesizing decision packet for {proposal.proposal_id}...")
            synthesis = self.synthesizer.synthesize(
                proposal.dict(),
                critique.dict(),
                audit.dict()
            )
            result["synthesis"] = synthesis.dict()
            logger.info(f"Final recommendation: {synthesis.final_recommendation}")
            logger.info(f"Confidence: {synthesis.confidence:.1%}")

            # Phase 6: Persist artifacts
            if not self.dry_run:
                logger.info(f"Persisting artifacts to governance/{proposal.proposal_id}/...")
                self.persist.write_proposal(proposal.proposal_id, proposal.dict())
                self.persist.write_critique(proposal.proposal_id, critique.dict())
                self.persist.write_audit(proposal.proposal_id, audit.dict())
                self.persist.write_synthesis(proposal.proposal_id, synthesis.dict())
                logger.info("Artifacts persisted")

                # Log governance events
                self._log_job_event(
                    "GOVERNANCE_PROPOSAL_CREATED",
                    proposal.proposal_id,
                    proposal.environment,
                )
                self._log_job_event(
                    "GOVERNANCE_PROPOSAL_CRITIQUED",
                    proposal.proposal_id,
                    proposal.environment,
                    {"recommendation": critique.recommendation},
                )
                self._log_job_event(
                    "GOVERNANCE_PROPOSAL_AUDITED",
                    proposal.proposal_id,
                    proposal.environment,
                    {"passed": audit.constitution_passed},
                )
                self._log_job_event(
                    "GOVERNANCE_PROPOSAL_SYNTHESIZED",
                    proposal.proposal_id,
                    proposal.environment,
                    {"recommendation": synthesis.final_recommendation},
                )
            else:
                logger.info("Dry-run mode: artifacts not persisted")

            result["success"] = True
            logger.info("Governance job completed successfully")

        except Exception as e:
            logger.error(f"Governance job failed: {e}", exc_info=True)
            result["errors"].append(str(e))
            self._log_job_event("GOVERNANCE_JOB_FAILED", details={"error": str(e)})

        return result

    def _log_job_event(
        self,
        event_type: str,
        proposal_id: Optional[str] = None,
        environment: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a governance event."""
        if self.dry_run:
            return

        event = create_governance_event(event_type, proposal_id, environment, details)
        self.persist.log_event(event)


def run_governance_job(
    persist_path: str = "persist",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Run governance job (convenience function).

    Args:
        persist_path: Base persistence directory
        dry_run: If True, don't write artifacts

    Returns:
        Pipeline result dict
    """
    job = CryptoGovernanceJob(persist_path, dry_run)
    return job.run()
