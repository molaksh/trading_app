"""
Exit Intent Tracker - Two-Phase Swing Exit System

Separates swing exit DECISION (after close) from EXECUTION (next trading day).

CRITICAL DESIGN:
- Swing exits are decided after market close (EOD data)
- Exit orders placed next trading day during execution window
- Prevents after-hours market orders
- Persists intent across restarts (idempotent)

Exit States:
- EXIT_PLANNED: Decision made, awaiting execution window
- FORCE_EXIT: Emergency exit, execute immediately
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional
from enum import Enum

from config.scope import get_scope
from config.scope_paths import get_scope_paths

logger = logging.getLogger(__name__)


class ExitIntentState(Enum):
    """Exit intent states."""
    EXIT_PLANNED = "EXIT_PLANNED"      # Planned exit, execute during next window
    FORCE_EXIT = "FORCE_EXIT"          # Emergency exit, execute immediately


@dataclass
class ExitIntent:
    """
    Represents a pending exit decision.
    
    This is the bridge between EOD decision and next-day execution.
    """
    symbol: str
    state: ExitIntentState
    decision_timestamp: str  # When exit was decided (ISO format)
    decision_date: str       # Date of decision (ISO format)
    exit_type: str           # "SWING_EXIT" | "EMERGENCY_EXIT"
    exit_reason: str         # Human-readable reason
    entry_date: str          # When position was opened
    holding_days: int
    confidence: Optional[int] = None
    urgency: str = 'eod'     # 'eod' or 'immediate'
    
    def to_dict(self) -> Dict:
        """Convert to dict for persistence."""
        return {
            **asdict(self),
            'state': self.state.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ExitIntent':
        """Create from dict."""
        data['state'] = ExitIntentState(data['state'])
        return cls(**data)


class ExitIntentTracker:
    """
    Tracks pending exit intents (two-phase swing exits).
    
    Phase 1: Record exit decision (after close)
    Phase 2: Execute exit order (next trading day)
    
    Responsibilities:
    - Persist exit intents to disk
    - Track which symbols have pending exits
    - Mark intents as executed
    - Survive restarts
    """
    
    def __init__(self, intent_file: Optional[Path] = None):
        """
        Initialize exit intent tracker.
        
        Args:
            intent_file: Path to persist intents (JSON). If None, uses ScopePathResolver.
        """
        if intent_file is None:
            scope = get_scope()
            scope_paths = get_scope_paths(scope)
            data_dir = scope_paths.get_data_dir()
            intent_file = data_dir / "exit_intents.json"
        
        self.intent_file = Path(intent_file)
        self.intent_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Active intents keyed by symbol
        self.pending_intents: Dict[str, ExitIntent] = {}
        
        # Load from disk
        self._load_from_disk()
        
        scope = get_scope()
        logger.info("=" * 80)
        logger.info(f"EXIT INTENT TRACKER INITIALIZED (SCOPE: {scope})")
        logger.info(f"  Intent file: {self.intent_file}")
        logger.info(f"  Pending intents: {len(self.pending_intents)}")
        logger.info("=" * 80)
    
    def add_intent(self, intent: ExitIntent) -> None:
        """
        Record an exit intent.
        
        Args:
            intent: ExitIntent to record
        """
        self.pending_intents[intent.symbol] = intent
        logger.info(
            f"EXIT INTENT RECORDED: {intent.symbol} | "
            f"State: {intent.state.value} | "
            f"Type: {intent.exit_type} | "
            f"Reason: {intent.exit_reason}"
        )
        self._save_to_disk()
    
    def get_intent(self, symbol: str) -> Optional[ExitIntent]:
        """
        Get pending exit intent for symbol.
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            ExitIntent if pending, None otherwise
        """
        return self.pending_intents.get(symbol)
    
    def has_intent(self, symbol: str) -> bool:
        """
        Check if symbol has a pending exit intent.
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            True if intent exists
        """
        return symbol in self.pending_intents
    
    def get_all_intents(self, state: Optional[ExitIntentState] = None) -> List[ExitIntent]:
        """
        Get all pending intents, optionally filtered by state.
        
        Args:
            state: Filter by state (optional)
        
        Returns:
            List of ExitIntent objects
        """
        if state is None:
            return list(self.pending_intents.values())
        
        return [
            intent for intent in self.pending_intents.values()
            if intent.state == state
        ]
    
    def mark_executed(self, symbol: str) -> None:
        """
        Mark an intent as executed (remove from pending).
        
        Args:
            symbol: Ticker symbol
        """
        if symbol in self.pending_intents:
            intent = self.pending_intents.pop(symbol)
            logger.info(
                f"EXIT INTENT EXECUTED: {symbol} | "
                f"Type: {intent.exit_type} | "
                f"Decided: {intent.decision_date}"
            )
            self._save_to_disk()
        else:
            logger.warning(f"No pending intent to mark executed: {symbol}")
    
    def clear_all(self) -> None:
        """Clear all pending intents (use with caution)."""
        count = len(self.pending_intents)
        self.pending_intents.clear()
        logger.warning(f"Cleared {count} pending exit intents")
        self._save_to_disk()
    
    # ========================================================================
    # Persistence
    # ========================================================================
    
    def _save_to_disk(self) -> None:
        """Save pending intents to disk."""
        try:
            data = {
                symbol: intent.to_dict()
                for symbol, intent in self.pending_intents.items()
            }
            
            with open(self.intent_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Exit intents saved: {len(data)} pending")
        except Exception as e:
            logger.error(f"Failed to save exit intents: {e}")
    
    def _load_from_disk(self) -> None:
        """Load pending intents from disk."""
        if not self.intent_file.exists():
            logger.info("No existing exit intent file - starting fresh")
            return
        
        try:
            with open(self.intent_file, 'r') as f:
                data = json.load(f)
            
            for symbol, intent_data in data.items():
                try:
                    intent = ExitIntent.from_dict(intent_data)
                    self.pending_intents[symbol] = intent
                except Exception as e:
                    logger.error(f"Failed to load intent for {symbol}: {e}")
            
            logger.info(f"Loaded {len(self.pending_intents)} pending exit intents from disk")
        
        except Exception as e:
            logger.error(f"Failed to load exit intents: {e}")
