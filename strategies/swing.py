# ============================================================================
# BACKWARD COMPATIBILITY SHIM
# ============================================================================
# This file exists for backward compatibility with old import paths.
# 
# NEW CANONICAL LOCATION:
# - core/strategies/equity/swing/  (single source of truth)
#
# This module re-exports from the canonical core location.
# Old code importing from strategies.swing continues to work.
#
# ============================================================================

# Import from core strategies (canonical location)
from core.strategies.equity.swing import SwingEquityStrategy
from core.strategies.equity.swing import BaseSwingStrategy, SwingStrategyMetadata

__all__ = [
    "SwingEquityStrategy",
    "BaseSwingStrategy",
    "SwingStrategyMetadata",
]
