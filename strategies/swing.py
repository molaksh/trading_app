# ============================================================================
# BACKWARD COMPATIBILITY SHIM
# ============================================================================
# This file exists for backward compatibility.
# 
# The swing strategies have been reorganized into a hierarchical structure:
# - strategies/us/equity/swing/     (US swing strategies)
# - strategies/india/equity/swing/  (India swing strategies)
#
# This file imports from the US location for backward compatibility.
# New code should import from the market-specific path directly.
#
# ============================================================================

# Import from US equity swing (the default)
from strategies.us.equity.swing.swing import SwingEquityStrategy
from strategies.us.equity.swing.swing_base import BaseSwingStrategy, SwingStrategyMetadata

__all__ = [
    "SwingEquityStrategy",
    "BaseSwingStrategy",
    "SwingStrategyMetadata",
]
