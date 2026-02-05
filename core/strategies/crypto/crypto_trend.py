"""
Crypto trend trading strategy.
"""

from typing import Dict, Any, List
from strategies.base import Strategy, TradeIntent


class CryptoTrendStrategy(Strategy):
    """Trend-following strategy for crypto markets."""
    
    def __init__(self):
        """Initialize crypto trend strategy."""
        config = {
            "enabled": True,
            "fast_ma": 10,
            "slow_ma": 20,
        }
        super().__init__("crypto_trend", config)
        self.description = "Trend-following crypto strategy"
        
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> List[TradeIntent]:
        """Generate entry intents based on moving average crossover."""
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
            name="crypto_trend",
            version="1.0",
            supported_markets=["global"],
            supported_modes=["crypto"],
            instrument_type="crypto",
        )
    
    def get_supported_instruments(self) -> List[str]:
        """Return list of supported instrument types."""
        return ["crypto"]


