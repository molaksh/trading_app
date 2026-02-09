"""
Phase D append-only JSONL persistence.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from phase_d.schemas import BlockEvent, BlockEvidence, PhaseEligibilityResult, PhaseDEvent
from config.phase_d_settings import PHASE_D_PERSIST_ROOT

logger = logging.getLogger(__name__)


class PhaseDPersistence:
    """Append-only JSONL persistence for Phase D."""

    def __init__(self):
        self.root = Path(PHASE_D_PERSIST_ROOT)
        self.blocks_dir = self.root / "crypto" / "blocks"
        self.evidence_dir = self.root / "crypto" / "evidence"
        self.eligibility_dir = self.root / "crypto" / "eligibility"
        self.events_file = self.root / "crypto" / "events" / "phase_d_events.jsonl"

        # Create directories
        self.blocks_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.eligibility_dir.mkdir(parents=True, exist_ok=True)
        self.events_file.parent.mkdir(parents=True, exist_ok=True)

    def write_block_event(self, event: BlockEvent) -> bool:
        """Write block event to events file (append-only)."""
        try:
            with self.blocks_dir / "block_events.jsonl" as f:
                # This will fail, need to open properly
                pass
        except Exception:
            pass

        try:
            events_file = self.blocks_dir / "block_events.jsonl"
            with events_file.open("a") as f:
                payload = {
                    "block_id": event.block_id,
                    "scope": event.scope,
                    "event_type": event.event_type,
                    "timestamp": event.timestamp.isoformat(),
                    "regime": event.regime,
                    "reason": event.reason,
                    "block_start_ts": event.block_start_ts.isoformat(),
                    "block_end_ts": event.block_end_ts.isoformat() if event.block_end_ts else None,
                    "duration_seconds": event.duration_seconds,
                    "block_type": event.block_type.value if event.block_type else None,
                    "regime_changes_during_block": event.regime_changes_during_block,
                }
                f.write(json.dumps(payload) + "\n")
            logger.info(f"PHASE_D_BLOCK_EVENT_WRITTEN | block_id={event.block_id} type={event.event_type}")
            return True
        except Exception as e:
            logger.error(f"PHASE_D_BLOCK_EVENT_WRITE_FAILED | error={e}")
            return False

    def write_block_evidence(self, evidence: BlockEvidence) -> bool:
        """Write evidence for a block (separate JSON file)."""
        try:
            evidence_file = self.evidence_dir / f"evidence_{evidence.block_id}.json"
            payload = {
                "block_id": evidence.block_id,
                "scope": evidence.scope,
                "duration_seconds": evidence.duration_seconds,
                "historical_median_duration": evidence.historical_median_duration,
                "historical_p90_duration": evidence.historical_p90_duration,
                "btc_max_upside_pct": evidence.btc_max_upside_pct,
                "eth_max_upside_pct": evidence.eth_max_upside_pct,
                "alt_max_upside_pct": evidence.alt_max_upside_pct,
                "btc_max_drawdown_pct": evidence.btc_max_drawdown_pct,
                "eth_max_drawdown_pct": evidence.eth_max_drawdown_pct,
                "portfolio_simulated_pnl": evidence.portfolio_simulated_pnl,
                "volatility_before_block_end": evidence.volatility_before_block_end,
                "volatility_after_block_end": evidence.volatility_after_block_end,
                "volatility_expansion_ratio": evidence.volatility_expansion_ratio,
                "regime_at_start": evidence.regime_at_start,
                "regime_at_end": evidence.regime_at_end,
                "regime_changes_during_block": evidence.regime_changes_during_block,
                "time_of_day_utc": evidence.time_of_day_utc,
                "day_of_week": evidence.day_of_week,
            }
            with evidence_file.open("w") as f:
                json.dump(payload, f, indent=2)
            logger.info(f"PHASE_D_EVIDENCE_WRITTEN | block_id={evidence.block_id}")
            return True
        except Exception as e:
            logger.error(f"PHASE_D_EVIDENCE_WRITE_FAILED | block_id={evidence.block_id} error={e}")
            return False

    def write_eligibility_result(self, result: PhaseEligibilityResult) -> bool:
        """Write eligibility evaluation result (append-only)."""
        try:
            with self.eligibility_dir / "eligibility_history.jsonl" as f:
                pass
        except Exception:
            pass

        try:
            history_file = self.eligibility_dir / "eligibility_history.jsonl"
            with history_file.open("a") as f:
                payload = {
                    "timestamp": result.timestamp.isoformat(),
                    "scope": result.scope,
                    "current_block_id": result.current_block_id,
                    "eligible": result.eligible,
                    "evidence_sufficiency_passed": result.evidence_sufficiency_passed,
                    "duration_anomaly_passed": result.duration_anomaly_passed,
                    "block_type_passed": result.block_type_passed,
                    "cost_benefit_passed": result.cost_benefit_passed,
                    "regime_safety_passed": result.regime_safety_passed,
                    "rule_details": result.rule_details,
                    "expiry_timestamp": result.expiry_timestamp.isoformat() if result.expiry_timestamp else None,
                }
                f.write(json.dumps(payload) + "\n")
            logger.info(f"PHASE_D_ELIGIBILITY_WRITTEN | scope={result.scope} eligible={result.eligible}")
            return True
        except Exception as e:
            logger.error(f"PHASE_D_ELIGIBILITY_WRITE_FAILED | scope={result.scope} error={e}")
            return False

    def write_event(self, event: PhaseDEvent) -> bool:
        """Write Phase D event (append-only)."""
        try:
            with self.events_file.open("a") as f:
                payload = {
                    "timestamp": event.timestamp.isoformat(),
                    "event_type": event.event_type,
                    "scope": event.scope,
                    "block_id": event.block_id,
                    "details": event.details,
                }
                f.write(json.dumps(payload) + "\n")
            logger.debug(f"PHASE_D_EVENT_WRITTEN | type={event.event_type} scope={event.scope}")
            return True
        except Exception as e:
            logger.error(f"PHASE_D_EVENT_WRITE_FAILED | type={event.event_type} error={e}")
            return False

    def read_latest_eligibility(self, scope: str) -> Optional[PhaseEligibilityResult]:
        """Read most recent eligibility evaluation for a scope."""
        try:
            history_file = self.eligibility_dir / "eligibility_history.jsonl"
            if not history_file.exists():
                return None

            latest = None
            with history_file.open("r") as f:
                for line in f:
                    try:
                        payload = json.loads(line.strip())
                        if payload.get("scope") == scope:
                            latest = payload
                    except Exception:
                        continue

            if not latest:
                return None

            return PhaseEligibilityResult(
                timestamp=datetime.fromisoformat(latest["timestamp"]),
                scope=latest["scope"],
                current_block_id=latest.get("current_block_id"),
                eligible=latest.get("eligible", False),
                evidence_sufficiency_passed=latest.get("evidence_sufficiency_passed", False),
                duration_anomaly_passed=latest.get("duration_anomaly_passed", False),
                block_type_passed=latest.get("block_type_passed", False),
                cost_benefit_passed=latest.get("cost_benefit_passed", False),
                regime_safety_passed=latest.get("regime_safety_passed", False),
                rule_details=latest.get("rule_details", {}),
                expiry_timestamp=datetime.fromisoformat(latest["expiry_timestamp"]) if latest.get("expiry_timestamp") else None,
            )
        except Exception as e:
            logger.error(f"PHASE_D_ELIGIBILITY_READ_FAILED | scope={scope} error={e}")
            return None

    def read_block_evidence(self, block_id: str) -> Optional[BlockEvidence]:
        """Read evidence for a specific block."""
        try:
            evidence_file = self.evidence_dir / f"evidence_{block_id}.json"
            if not evidence_file.exists():
                return None

            with evidence_file.open("r") as f:
                payload = json.load(f)

            return BlockEvidence(**payload)
        except Exception as e:
            logger.error(f"PHASE_D_EVIDENCE_READ_FAILED | block_id={block_id} error={e}")
            return None

    def read_block_events(self, scope: str) -> List[BlockEvent]:
        """Read all block events for a scope."""
        try:
            events_file = self.blocks_dir / "block_events.jsonl"
            if not events_file.exists():
                return []

            events = []
            with events_file.open("r") as f:
                for line in f:
                    try:
                        payload = json.loads(line.strip())
                        if payload.get("scope") == scope:
                            event = BlockEvent(
                                block_id=payload["block_id"],
                                scope=payload["scope"],
                                event_type=payload["event_type"],
                                timestamp=datetime.fromisoformat(payload["timestamp"]),
                                regime=payload["regime"],
                                reason=payload["reason"],
                                block_start_ts=datetime.fromisoformat(payload["block_start_ts"]),
                                block_end_ts=datetime.fromisoformat(payload["block_end_ts"]) if payload.get("block_end_ts") else None,
                                duration_seconds=payload.get("duration_seconds"),
                                block_type=BlockEvent.__fields__["block_type"].type_(payload.get("block_type")) if payload.get("block_type") else None,
                                regime_changes_during_block=payload.get("regime_changes_during_block", []),
                            )
                            events.append(event)
                    except Exception:
                        continue

            return events
        except Exception as e:
            logger.error(f"PHASE_D_BLOCK_EVENTS_READ_FAILED | scope={scope} error={e}")
            return []
