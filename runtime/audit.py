"""
Audit Logger for Live Trading Governance.

CRITICAL REQUIREMENTS:
- Log every manual phase change
- Log every model promotion
- Log every live trading decision
- Log every kill switch activation
- Attribute every action to human or system
- Immutable append-only audit trail

PHILOSOPHY:
- If it changes risk, it gets logged
- Audit logs are sacred (never delete/modify)
- Timestamps must be precise
- Attribution must be clear
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from config.scope import get_scope
from config.scope_paths import get_scope_path

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of events that require auditing."""
    
    # ML Governance
    ML_PHASE_CHANGE = "ml_phase_change"
    ML_MODEL_PROMOTED = "ml_model_promoted"
    ML_MODEL_LOADED = "ml_model_loaded"
    ML_MODEL_RETIRED = "ml_model_retired"
    
    # Trading Control
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"
    KILL_SWITCH_DEACTIVATED = "kill_switch_deactivated"
    SAFE_MODE_ENTERED = "safe_mode_entered"
    SAFE_MODE_EXITED = "safe_mode_exited"
    
    # Configuration
    CONFIG_CHANGED = "config_changed"
    CONTAINER_STARTED = "container_started"
    CONTAINER_STOPPED = "container_stopped"
    
    # Risk Events
    POSITION_LIMIT_BREACH = "position_limit_breach"
    LOSS_LIMIT_BREACH = "loss_limit_breach"
    RECONCILIATION_FAILURE = "reconciliation_failure"


class AuditAttribution(Enum):
    """Who/what triggered the event."""
    
    HUMAN = "human"           # Manual human action
    SYSTEM_AUTO = "system_auto"  # Automatic system action
    SYSTEM_RECOMMENDED = "system_recommended"  # System recommended, human approved


@dataclass
class AuditEvent:
    """Single audit log entry."""
    
    event_type: str  # AuditEventType value
    timestamp: str
    attribution: str  # AuditAttribution value
    environment: str  # 'paper' or 'live'
    scope: str  # Full scope string
    actor: Optional[str]  # Who did it (username, container ID, etc.)
    details: Dict[str, Any]  # Event-specific details
    previous_state: Optional[Dict] = None  # State before change
    new_state: Optional[Dict] = None  # State after change
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())


class AuditLogger:
    """
    Immutable append-only audit log.
    
    CRITICAL: Logs are append-only and never modified.
    """
    
    def __init__(self):
        """Initialize audit logger."""
        scope = get_scope()
        logs_dir = get_scope_path(scope, "logs")
        
        self.audit_file = logs_dir / "audit_trail.jsonl"
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"AuditLogger initialized: {self.audit_file}")
    
    def log_ml_phase_change(
        self,
        old_phase: str,
        new_phase: str,
        actor: str,
        reason: str,
        attribution: AuditAttribution = AuditAttribution.HUMAN
    ) -> None:
        """
        Log ML learning phase change.
        
        Args:
            old_phase: Previous phase (e.g., "PHASE_1")
            new_phase: New phase (e.g., "PHASE_2")
            actor: Who made the change
            reason: Why the change was made
            attribution: How the change was triggered
        """
        event = AuditEvent(
            event_type=AuditEventType.ML_PHASE_CHANGE.value,
            timestamp=datetime.now().isoformat(),
            attribution=attribution.value,
            environment=self._get_environment(),
            scope=str(get_scope()),
            actor=actor,
            details={
                "old_phase": old_phase,
                "new_phase": new_phase,
                "reason": reason,
            },
            previous_state={"phase": old_phase},
            new_state={"phase": new_phase},
        )
        
        self._write_event(event)
        
        logger.info(
            f"AUDIT: ML phase changed from {old_phase} → {new_phase} "
            f"(actor: {actor}, attribution: {attribution.value})"
        )
    
    def log_model_promotion(
        self,
        model_version: str,
        previous_active: Optional[str],
        metrics: Dict,
        actor: str,
        reason: str,
        attribution: AuditAttribution = AuditAttribution.HUMAN
    ) -> None:
        """
        Log model promotion to active status.
        
        Args:
            model_version: Version being promoted
            previous_active: Previously active version (if any)
            metrics: Model performance metrics
            actor: Who promoted it
            reason: Why it was promoted
            attribution: How promotion was triggered
        """
        event = AuditEvent(
            event_type=AuditEventType.ML_MODEL_PROMOTED.value,
            timestamp=datetime.now().isoformat(),
            attribution=attribution.value,
            environment=self._get_environment(),
            scope=str(get_scope()),
            actor=actor,
            details={
                "model_version": model_version,
                "previous_active": previous_active,
                "metrics": metrics,
                "reason": reason,
            },
            previous_state={"active_model": previous_active},
            new_state={"active_model": model_version},
        )
        
        self._write_event(event)
        
        logger.info(
            f"AUDIT: Model {model_version} promoted "
            f"(replaced: {previous_active}, actor: {actor})"
        )
    
    def log_kill_switch(
        self,
        activated: bool,
        reason: str,
        automatic: bool = False,
        actor: Optional[str] = None
    ) -> None:
        """
        Log kill switch activation/deactivation.
        
        Args:
            activated: True if activating, False if deactivating
            reason: Why it was triggered
            automatic: True if auto-triggered
            actor: Who triggered it (if manual)
        """
        attribution = AuditAttribution.SYSTEM_AUTO if automatic else AuditAttribution.HUMAN
        event_type = AuditEventType.KILL_SWITCH_ACTIVATED if activated else AuditEventType.KILL_SWITCH_DEACTIVATED
        
        event = AuditEvent(
            event_type=event_type.value,
            timestamp=datetime.now().isoformat(),
            attribution=attribution.value,
            environment=self._get_environment(),
            scope=str(get_scope()),
            actor=actor or ("system" if automatic else "unknown"),
            details={
                "activated": activated,
                "reason": reason,
                "automatic": automatic,
            },
        )
        
        self._write_event(event)
        
        action = "ACTIVATED" if activated else "DEACTIVATED"
        logger.critical(f"AUDIT: Kill switch {action} (reason: {reason}, actor: {event.actor})")
    
    def log_container_lifecycle(
        self,
        event: str,
        details: Optional[Dict] = None
    ) -> None:
        """
        Log container start/stop.
        
        Args:
            event: 'started' or 'stopped'
            details: Additional details
        """
        event_type = AuditEventType.CONTAINER_STARTED if event == "started" else AuditEventType.CONTAINER_STOPPED
        
        audit_event = AuditEvent(
            event_type=event_type.value,
            timestamp=datetime.now().isoformat(),
            attribution=AuditAttribution.SYSTEM_AUTO.value,
            environment=self._get_environment(),
            scope=str(get_scope()),
            actor="container_manager",
            details=details or {},
        )
        
        self._write_event(audit_event)
    
    def log_config_change(
        self,
        config_key: str,
        old_value: Any,
        new_value: Any,
        actor: str,
        reason: str
    ) -> None:
        """
        Log configuration change.
        
        Args:
            config_key: Configuration parameter changed
            old_value: Previous value
            new_value: New value
            actor: Who changed it
            reason: Why it was changed
        """
        event = AuditEvent(
            event_type=AuditEventType.CONFIG_CHANGED.value,
            timestamp=datetime.now().isoformat(),
            attribution=AuditAttribution.HUMAN.value,
            environment=self._get_environment(),
            scope=str(get_scope()),
            actor=actor,
            details={
                "config_key": config_key,
                "old_value": str(old_value),
                "new_value": str(new_value),
                "reason": reason,
            },
            previous_state={config_key: old_value},
            new_state={config_key: new_value},
        )
        
        self._write_event(event)
    
    def _write_event(self, event: AuditEvent) -> None:
        """
        Write event to immutable audit log.
        
        CRITICAL: Append-only, never modify existing entries.
        """
        try:
            with open(self.audit_file, "a") as f:
                f.write(event.to_json() + "\n")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to write audit event: {e}")
            # Also log to stderr as backup
            import sys
            sys.stderr.write(f"AUDIT_FAILURE: {event.to_json()}\n")
    
    def _get_environment(self) -> str:
        """Get current environment (paper or live)."""
        import os
        return os.getenv("ENV", "unknown").lower()
    
    def query_events(
        self,
        event_type: Optional[AuditEventType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        actor: Optional[str] = None
    ) -> list:
        """
        Query audit log.
        
        Args:
            event_type: Filter by event type
            start_date: Filter by start date
            end_date: Filter by end date
            actor: Filter by actor
            
        Returns:
            List of matching events
        """
        if not self.audit_file.exists():
            return []
        
        events = []
        
        with open(self.audit_file) as f:
            for line in f:
                if not line.strip():
                    continue
                
                try:
                    event_dict = json.loads(line)
                    
                    # Apply filters
                    if event_type and event_dict.get("event_type") != event_type.value:
                        continue
                    
                    if actor and event_dict.get("actor") != actor:
                        continue
                    
                    if start_date:
                        event_time = datetime.fromisoformat(event_dict["timestamp"])
                        if event_time < start_date:
                            continue
                    
                    if end_date:
                        event_time = datetime.fromisoformat(event_dict["timestamp"])
                        if event_time > end_date:
                            continue
                    
                    events.append(event_dict)
                except Exception as e:
                    logger.warning(f"Could not parse audit event: {e}")
        
        return events


# Global singleton
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
