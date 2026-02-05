"""
Crypto momentum trading strategy.
"""

from typing import Dict, Any, List
from strategies.base import Strategy, TradeIntent


class CryptoMomentumStrategy(Strategy):
    """Momentum-based strategy for crypto markets."""
    
    def __init__(self):
        """Initialize crypto momentum strategy."""
        config = {
            "enabled": True,
            "lookback_periods": 14,
            "momentum_threshold": 0.02,
        }
        super().__init__("crypto_momentum", config)
        self.description = "Momentum-based crypto strategy"
    
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> List[TradeIntent]:
        """Generate entry intents based on momentum."""
        return []
    
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """Generate exit intents."""
        return []
    
    def get_metadata(self):
        """Get strategy metadata."""
        from strategies.registry import StrategyMetadata
        return StrategyMetadata(
            name="crypto_momentum",
            version="1.0",
            supported_markets=["global"],
            supported_modes=["crypto"],
            instrument_type="crypto",
        )
    
    def get_supported_instruments(self) -> List[str]:
        """Return list of supported instrument types."""
        return ["crypto"]


