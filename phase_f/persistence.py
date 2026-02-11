"""
Phase F Persistence: Append-only episodic and versioned semantic memory.

CRITICAL CONSTRAINTS:
- Episodic memory: NEVER deleted, NEVER overwritten, ONLY appended
- Semantic memory: Versioned, never overwritten, only new versions added
- Memory never encodes decisions or "what worked"
- All writes are idempotent and safe
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from phase_f.schemas import EpistemicMemoryEvent, SemanticMemorySummary, Verdict

logger = logging.getLogger(__name__)


class Phase_F_Persistence:
    """Append-only persistence for Phase F memory."""

    def __init__(self, root: str = "persist/phase_f/crypto"):
        """Initialize persistence with guaranteed directory structure."""
        self.root = Path(root)

        # Create subdirectories
        self.episodic_dir = self.root / "episodic"
        self.semantic_dir = self.root / "semantic" / "summaries"
        self.verdicts_dir = self.root / "verdicts"

        for directory in [self.episodic_dir, self.semantic_dir, self.verdicts_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")

        # File paths
        self.episodic_path = self.episodic_dir / "events.jsonl"
        self.verdicts_path = self.verdicts_dir / "verdicts.jsonl"

        logger.info(
            f"Phase F Persistence initialized: root={self.root}"
        )

    # ========================================================================
    # Episodic Memory (Append-Only)
    # ========================================================================

    def append_episodic_event(self, event: EpistemicMemoryEvent) -> None:
        """
        Append event to episodic memory (never deleted, never overwritten).

        Args:
            event: EpistemicMemoryEvent to record

        Raises:
            IOError: If write fails
        """
        try:
            event_dict = event.model_dump(mode="json")

            with open(self.episodic_path, "a") as f:
                f.write(json.dumps(event_dict, default=str) + "\n")

            logger.debug(
                f"Appended episodic event: {event.event_type} from {event.source}"
            )

        except IOError as e:
            logger.error(f"Failed to append episodic event: {e}", exc_info=True)
            raise

    def read_episodic_events(
        self, lookback_days: int = 90, event_type: Optional[str] = None
    ) -> List[EpistemicMemoryEvent]:
        """
        Read episodic memory (read-only view).

        Args:
            lookback_days: Maximum days to look back
            event_type: Filter by event type (optional)

        Returns:
            List of EpistemicMemoryEvent objects, chronologically ordered
        """
        if not self.episodic_path.exists():
            return []

        events = []
        cutoff_ts = (
            datetime.utcnow().timestamp() - (lookback_days * 86400)
        )

        try:
            with open(self.episodic_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                        event = EpistemicMemoryEvent(**data)

                        # Check timestamp
                        event_ts = datetime.fromisoformat(
                            event.timestamp.replace("Z", "+00:00")
                        ).timestamp()
                        if event_ts < cutoff_ts:
                            continue

                        # Check event type filter
                        if event_type and event.event_type != event_type:
                            continue

                        events.append(event)

                    except Exception as e:
                        logger.warning(
                            f"Failed to parse episodic event: {e}"
                        )
                        continue

        except IOError as e:
            logger.error(f"Failed to read episodic memory: {e}")
            return []

        logger.debug(
            f"Read {len(events)} episodic events (lookback={lookback_days}d)"
        )
        return events

    def find_similar_claims(
        self, claim_text: str, lookback_days: int = 90
    ) -> List[EpistemicMemoryEvent]:
        """
        Find past events with similar claims (for confidence calibration).

        Args:
            claim_text: Claim to search for
            lookback_days: Maximum days to look back

        Returns:
            List of similar past events
        """
        all_events = self.read_episodic_events(lookback_days=lookback_days)

        similar = []
        claim_lower = claim_text.lower()

        for event in all_events:
            if claim_lower in event.claim.lower():
                similar.append(event)

        logger.debug(
            f"Found {len(similar)} similar past claims"
        )
        return similar

    # ========================================================================
    # Verdicts (Append-Only)
    # ========================================================================

    def append_verdict(self, verdict: Verdict, run_id: str) -> None:
        """
        Append verdict to verdict history (audit trail).

        Args:
            verdict: Verdict to record
            run_id: ID of the Phase F run

        Raises:
            IOError: If write fails
        """
        try:
            verdict_record = {
                "run_id": run_id,
                "timestamp": datetime.utcnow().isoformat(),
                "verdict": verdict.model_dump(mode="json"),
            }

            with open(self.verdicts_path, "a") as f:
                f.write(json.dumps(verdict_record, default=str) + "\n")

            logger.debug(f"Appended verdict: {verdict.verdict}")

        except IOError as e:
            logger.error(f"Failed to append verdict: {e}", exc_info=True)
            raise

    def read_verdicts(self, lookback_days: int = 30) -> List[Dict[str, Any]]:
        """
        Read verdict history.

        Args:
            lookback_days: Maximum days to look back

        Returns:
            List of verdict records, chronologically ordered
        """
        if not self.verdicts_path.exists():
            return []

        verdicts = []
        cutoff_ts = (
            datetime.utcnow().timestamp() - (lookback_days * 86400)
        )

        try:
            with open(self.verdicts_path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue

                    try:
                        data = json.loads(line)
                        verdict_ts = datetime.fromisoformat(
                            data["timestamp"].replace("Z", "+00:00")
                        ).timestamp()

                        if verdict_ts < cutoff_ts:
                            continue

                        verdicts.append(data)

                    except Exception as e:
                        logger.warning(f"Failed to parse verdict: {e}")
                        continue

        except IOError as e:
            logger.error(f"Failed to read verdicts: {e}")
            return []

        logger.debug(
            f"Read {len(verdicts)} verdicts (lookback={lookback_days}d)"
        )
        return verdicts

    def get_latest_verdict(self) -> Optional[Dict[str, Any]]:
        """
        Get the most recent verdict.

        Returns:
            Latest verdict or None if no verdicts exist
        """
        verdicts = self.read_verdicts(lookback_days=30)
        return verdicts[-1] if verdicts else None

    # ========================================================================
    # Semantic Memory (Versioned)
    # ========================================================================

    def write_semantic_summary(self, summary: SemanticMemorySummary) -> None:
        """
        Write semantic memory summary (versioned, never overwritten).

        Args:
            summary: SemanticMemorySummary to write

        Raises:
            IOError: If write fails
        """
        try:
            filename = (
                f"semantic_{summary.period_start}_{summary.period_end}_v{summary.version}.json"
            )
            path = self.semantic_dir / filename

            # Ensure no overwrite: check version exists
            if path.exists():
                logger.warning(
                    f"Semantic summary version already exists: {filename}"
                )
                return

            with open(path, "w") as f:
                json.dump(summary.model_dump(mode="json"), f, indent=2)

            logger.info(f"Wrote semantic summary: {filename}")

        except IOError as e:
            logger.error(f"Failed to write semantic summary: {e}", exc_info=True)
            raise

    def read_semantic_summary(
        self, period_start: str, period_end: str, version: int = 1
    ) -> Optional[SemanticMemorySummary]:
        """
        Read semantic memory summary by period and version.

        Args:
            period_start: Period start (ISO format)
            period_end: Period end (ISO format)
            version: Version number (default 1)

        Returns:
            SemanticMemorySummary or None if not found
        """
        filename = (
            f"semantic_{period_start}_{period_end}_v{version}.json"
        )
        path = self.semantic_dir / filename

        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                data = json.load(f)
                return SemanticMemorySummary(**data)

        except Exception as e:
            logger.error(f"Failed to read semantic summary: {e}")
            return None

    def list_semantic_summaries(self) -> List[str]:
        """
        List all semantic summary versions.

        Returns:
            List of filenames
        """
        if not self.semantic_dir.exists():
            return []

        return [f.name for f in self.semantic_dir.glob("semantic_*.json")]

    # ========================================================================
    # Data Cleanup & Archival
    # ========================================================================

    def archive_old_events(self, older_than_days: int = 30) -> None:
        """
        Archive episodic events older than specified days.

        Args:
            older_than_days: Events older than this many days are archived

        Note:
            This creates a compressed archive but NEVER deletes the original.
        """
        try:
            import gzip
            import shutil

            cutoff_ts = (
                datetime.utcnow().timestamp()
                - (older_than_days * 86400)
            )

            # Read all events
            all_events = self.read_episodic_events(
                lookback_days=365
            )  # 1 year lookback

            # Split into old and new
            old_events = [
                e
                for e in all_events
                if datetime.fromisoformat(
                    e.timestamp.replace("Z", "+00:00")
                ).timestamp()
                < cutoff_ts
            ]

            if len(old_events) == 0:
                logger.debug("No events to archive")
                return

            # Write to archive file
            archive_name = f"events_archive_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl.gz"
            archive_path = self.episodic_dir / archive_name

            with gzip.open(archive_path, "wt") as f:
                for event in old_events:
                    f.write(json.dumps(event.model_dump(mode="json")) + "\n")

            logger.info(
                f"Archived {len(old_events)} old events to {archive_path}"
            )

        except Exception as e:
            logger.error(f"Failed to archive events: {e}")

    def __repr__(self) -> str:
        return (
            f"Phase_F_Persistence(root={self.root}, "
            f"episodic={self.episodic_path}, "
            f"semantic={self.semantic_dir}, "
            f"verdicts={self.verdicts_path})"
        )


def get_persistence(root: str = "persist/phase_f/crypto") -> Phase_F_Persistence:
    """Convenience function to get persistence instance."""
    return Phase_F_Persistence(root)
