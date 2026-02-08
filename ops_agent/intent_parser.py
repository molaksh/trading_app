"""
Deterministic intent parser for Telegram messages.

Small, bounded grammar for extracting user intent.
"""

import re
from typing import Tuple, Optional
from ops_agent.schemas import Intent


class IntentParser:
    """Parse Telegram messages into structured intents."""

    # Scope inference patterns
    SCOPE_PATTERNS = {
        r"live.*crypto|crypto.*live": "live_crypto",
        r"paper.*crypto|crypto.*paper": "paper_crypto",
        r"live.*us|us.*live|live.*alpaca": "live_us",
        r"paper.*us|us.*paper|paper.*alpaca": "paper_us",
        r"govern|proposal": "governance",
    }

    # Intent patterns (question -> intent_type)
    INTENT_PATTERNS = {
        r"why.*(?:no|not).*trade|why.*no.*signal": "EXPLAIN_NO_TRADES",
        r"fill|what.*filled|executed.*trade": "EXPLAIN_TRADES",
        r"what.*regime|what mode|current regime|regime\s*\?": "EXPLAIN_REGIME",
        r"block|what.*block": "EXPLAIN_BLOCKS",
        r"what.*happen.*today|today.*what|daily.*status": "EXPLAIN_TODAY",
        r"governance|proposal.*pending|wait.*approv": "EXPLAIN_GOVERNANCE",
        r"ai.*rank|what.*ai|top.*symbol|symbol.*rank": "EXPLAIN_AI_RANKING",
        r"job.*health|job.*status|stale|job.*running": "EXPLAIN_JOBS",
        r"error|exception|crash|problem|fail": "EXPLAIN_ERRORS",
        r"hold|position|what.*own|my.*stock|portfolio": "EXPLAIN_HOLDINGS",
        r"model|ml.*model|ml.*state|training": "EXPLAIN_ML",
        r"reconcili|rec.*state|rec.*health": "EXPLAIN_RECONCILIATION",
        r"health|system.*health|overall.*status": "EXPLAIN_HEALTH",
        r"status|how.*doing|current.*state": "STATUS",
        r"monitor.*|watch.*|alert.*|notif.*": "START_WATCH",
        r"stop.*monitor|stop.*watch|cancel.*alert": "STOP_WATCH",
    }

    # TTL patterns for watch duration
    TTL_PATTERNS = {
        r"(\d+)\s*hours?": lambda m: int(m.group(1)),
        r"(\d+)\s*days?": lambda m: int(m.group(1)) * 24,
        r"for.*?(\d+)\s*hours?": lambda m: int(m.group(1)),
        r"for.*?(\d+)\s*days?": lambda m: int(m.group(1)) * 24,
        r"until\s*tomorrow": lambda m: 24,
        r"for\s*a\s*day": lambda m: 24,
        r"for\s*a\s*week": lambda m: 24 * 7,
    }

    def parse(self, text: str) -> Intent:
        """
        Parse a Telegram message into an Intent.

        Returns:
            Intent with intent_type, scope, and confidence.
        """
        text_lower = text.lower().strip()

        # 1. Detect intent type
        intent_type = self._detect_intent_type(text_lower)
        if not intent_type:
            intent_type = "STATUS"  # Default: ask for status

        # 2. Detect scope
        scope = self._detect_scope(text_lower)

        # 3. Check if user wants info about all containers
        all_scopes = any(word in text_lower for word in ["all", "containers", "everything", "all containers"])

        # 4. Extract TTL for watches
        ttl_hours = None
        if intent_type == "START_WATCH":
            ttl_hours = self._extract_ttl(text_lower)
            if ttl_hours is None:
                ttl_hours = 24  # Default: 24 hours

        # 5. Detect watch condition
        condition = None
        if intent_type == "START_WATCH":
            condition = self._detect_watch_condition(text_lower)

        # Confidence: higher if multiple cues match
        confidence = self._calculate_confidence(text_lower, intent_type)

        return Intent(
            intent_type=intent_type,
            scope=scope,
            all_scopes=all_scopes,
            condition=condition,
            ttl_hours=ttl_hours,
            confidence=confidence,
        )

    def _detect_intent_type(self, text: str) -> Optional[str]:
        """Detect intent type from text."""
        for pattern, intent_type in self.INTENT_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                return intent_type
        return None

    def _detect_scope(self, text: str) -> Optional[str]:
        """Detect scope from text."""
        for pattern, scope in self.SCOPE_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                return scope
        return None  # Scope may be inferred later from context

    def _extract_ttl(self, text: str) -> Optional[int]:
        """Extract watch TTL (in hours) from text."""
        for pattern, extractor in self.TTL_PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return extractor(match)
        return None

    def _detect_watch_condition(self, text: str) -> str:
        """Detect what to watch for."""
        conditions = {
            r"regime\s*change": "regime_change",
            r"governance|proposal": "governance_pending",
            r"no.*trade|block": "no_trades",
            r"pnl|drawdown|loss": "pnl_threshold",
        }
        for pattern, condition in conditions.items():
            if re.search(pattern, text, re.IGNORECASE):
                return condition
        return "any_change"  # Default: notify on any state change

    def _calculate_confidence(self, text: str, intent_type: str) -> float:
        """Calculate confidence in parsing (0-1)."""
        confidence = 0.5  # Base confidence

        # Boost for clear keywords
        if any(word in text for word in ["why", "what", "how", "status"]):
            confidence += 0.2

        # Boost for explicit scope
        if any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in self.SCOPE_PATTERNS.keys()
        ):
            confidence += 0.15

        # Boost for explicit duration
        if any(
            re.search(pattern, text, re.IGNORECASE)
            for pattern in self.TTL_PATTERNS.keys()
        ):
            confidence += 0.15

        return min(0.95, confidence)  # Cap at 0.95


def parse_telegram_message(text: str) -> Intent:
    """Convenience function to parse a message."""
    parser = IntentParser()
    return parser.parse(text)
