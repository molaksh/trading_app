"""
Runtime trade permission gate for live safety.

Provides explicit NO-TRADE states with structured logging.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from config.scope import get_scope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlockState:
    state: str
    reason: str
    timestamp: str


class TradePermission:
    """
    Trade permission gate with explicit block states.

    Any active block vetoes trading.
    """

    def __init__(self) -> None:
        self._blocks: Dict[str, BlockState] = {}

    def set_block(self, state: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        existing = self._blocks.get(state)
        if existing and existing.reason == reason:
            return
        self._blocks[state] = BlockState(state=state, reason=reason, timestamp=now)
        logger.error(f"TRADING_BLOCKED_{state} | reason={reason} | ts={now}")
        if _BLOCK_HOOK is not None:
            _BLOCK_HOOK(state, reason, "block")

    def clear_block(self, state: str, reason: str) -> None:
        if state not in self._blocks:
            return
        now = datetime.now(timezone.utc).isoformat()
        del self._blocks[state]
        logger.error(f"TRADING_UNBLOCKED_{state} | reason={reason} | ts={now}")
        if _BLOCK_HOOK is not None:
            _BLOCK_HOOK(state, reason, "unblock")

    def trade_allowed(self) -> bool:
        return len(self._blocks) == 0

    def get_primary_block(self) -> Optional[BlockState]:
        if not self._blocks:
            return None
        state_key = sorted(self._blocks.keys())[0]
        return self._blocks[state_key]

    def get_blocks(self) -> Dict[str, BlockState]:
        return dict(self._blocks)

    def snapshot(self) -> Dict[str, str]:
        scope = get_scope()
        primary = self.get_primary_block()
        last_change = primary.timestamp if primary else "NONE"
        return {
            "ENV": scope.env.upper(),
            "BROKER": scope.broker.upper(),
            "TRADING_ALLOWED": "YES" if self.trade_allowed() else "NO",
            "BLOCK_STATE": primary.state if primary else "NONE",
            "BLOCK_REASON": primary.reason if primary else "NONE",
            "LAST_BLOCK_CHANGE": last_change,
        }


_TRADE_PERMISSION: Optional[TradePermission] = None
_BLOCK_HOOK = None


def set_trade_permission_hook(hook) -> None:
    global _BLOCK_HOOK
    _BLOCK_HOOK = hook


def get_trade_permission() -> TradePermission:
    global _TRADE_PERMISSION
    if _TRADE_PERMISSION is None:
        _TRADE_PERMISSION = TradePermission()
    return _TRADE_PERMISSION
