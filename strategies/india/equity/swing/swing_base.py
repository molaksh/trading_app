"""
BaseSwingStrategy - Abstract contract for all swing trading philosophies.

ARCHITECTURAL PRINCIPLE:
- Swing is a TRADE MODE (holding period: 2-20 days)
- Strategies are TRADING PHILOSOPHIES (how to identify swing opportunities)
- This contract defines WHAT every swing strategy must implement
- Market-agnostic: US, India, future markets use same strategy classes

STRATEGY METADATA REQUIREMENTS:
Every swing strategy must declare:
1. Philosophy: Core trading idea (1-2 sentences)
2. Edge: Specific market condition that creates opportunity
3. Risks: Known failure modes
4. Caveats: When NOT to trust this strategy
5. Supported markets: Explicit list of markets (us, india, etc.)
6. Version: Semantic versioning for reproducibility

INTERFACE CONTRACT:
All swing strategies must implement:
- generate_entry_intents(): Signal swing entry opportunities
- generate_exit_intents(): Signal swing exit conditions
- get_metadata(): Return philosophy + risks + caveats
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from strategies.base import (
    Strategy,
    TradeIntent,
    TradeDirection,
    IntentType,
    IntentUrgency,
)


@dataclass
class SwingStrategyMetadata:
    """
    Metadata for a swing trading philosophy.
    
    This is NOT a strategy instance - it's the blueprint documenting:
    - What this strategy is
    - What it does well (edge)
    - What can break it (risks)
    - When to ignore its signals (caveats)
    """
    
    # Identity
    strategy_id: str  # Unique, stable identifier (e.g., "trend_pullback_v1")
    strategy_name: str  # Human-readable name (e.g., "Swing Trend Pullback")
    version: str  # Semantic versioning (e.g., "1.0.0")
    
    # Philosophy
    philosophy: str  # 1-2 sentence core idea (e.g., "Trade shallow pullbacks in strong uptrends")
    
    # Edge
    edge: str  # Specific market condition that creates opportunity
    
    # Risk Management
    risks: List[str]  # Known failure modes
    caveats: List[str]  # When NOT to trust this strategy
    
    # Scope
    supported_modes: List[str]  # Always ["swing"] for this base class
    supported_instruments: List[str]  # Always ["equity"] for swing
    supported_markets: List[str]  # ["us", "india"] etc. - explicit market support
    
    def __post_init__(self):
        """Validate metadata integrity."""
        assert "swing" in self.supported_modes, "All SwingStrategies must support mode='swing'"
        assert "equity" in self.supported_instruments, "All SwingStrategies must support equity instruments"
        assert len(self.supported_markets) > 0, "Must explicitly declare supported markets"
        assert len(self.risks) > 0, "Must document known risks"
        assert len(self.caveats) > 0, "Must document caveats"


class BaseSwingStrategy(Strategy, ABC):
    """
    Abstract base for all swing trading philosophies.
    
    RESPONSIBILITY:
    - Analyze market data according to a specific philosophy
    - Generate entry intents when conditions match philosophy
    - Generate exit intents when positions should close
    - Expose philosophy, risks, and caveats in metadata
    
    NOT RESPONSIBLE:
    - Position sizing (RiskManager decides)
    - Order routing (Broker handles)
    - Risk checks (TradeIntentGuard validates)
    - Portfolio state tracking (Engine maintains)
    
    MARKET AGNOSTICISM:
    - No hardcoded US/India assumptions
    - No market-specific hours/holidays in signal logic
    - Market-specific rules applied by MarketHoursPolicy, not here
    
    IMPLEMENTATION PATTERN:
    1. Create subclass (e.g., SwingTrendPullbackStrategy)
    2. Override generate_entry_intents() with philosophy logic
    3. Override generate_exit_intents() with exit philosophy
    4. Declare metadata() with risks/caveats/edge
    5. Register in strategies/registry.py
    """
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        """
        Initialize swing strategy.
        
        Args:
            name: Unique strategy name (e.g., "trend_pullback")
            config: Dict of strategy parameters (philosophy-specific)
        """
        default_config = {
            "enabled": True,
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(name, default_config)
    
    @abstractmethod
    def get_swing_metadata(self) -> SwingStrategyMetadata:
        """
        Declare strategy philosophy, edge, risks, and caveats.
        
        This is called at initialization to validate that the strategy
        explicitly declares what it does, when it works, when it fails.
        
        Returns:
            SwingStrategyMetadata with complete documentation
        """
        raise NotImplementedError
    
    @abstractmethod
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Analyze market data and generate entry signals.
        
        Philosophy-specific implementation:
        - Trend pullback: Shallow pullbacks in confirmed uptrends
        - Momentum breakout: Strength continuation moves
        - Mean reversion: Snapbacks within valid trends
        - Volatility squeeze: Expansion after compression
        - Event-driven: Post-event mean reversion
        
        Args:
            market_data: Dict with 'signals', 'prices', 'indicators'
            portfolio_state: Dict with 'positions', 'buying_power'
        
        Returns:
            List[TradeIntent] with direction=LONG, intent_type=ENTRY
            - Quantity: Optional (RiskManager decides if None)
            - Confidence: 0-5 scale or 0-1 scale (must be consistent)
            - Features: Dict of philosophy-specific features
            - Risk metadata: Hold period, max position size, etc.
        """
        raise NotImplementedError
    
    @abstractmethod
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Analyze positions and generate exit signals.
        
        Exit philosophy:
        - Max holding period (always enforced: 20 days)
        - Profit target (philosophy-specific, e.g., +10%)
        - Philosophy invalidation (conditions that break the edge)
        
        Args:
            positions: List of positions from portfolio_state
            market_data: Current market data with prices + indicators
        
        Returns:
            List[TradeIntent] with intent_type=EXIT
            - Urgency: IMMEDIATE (emergency), EOD, or NEXT_OPEN
            - Reason: Human-readable explanation
            - Features: Exit reasoning (days held, return %, etc.)
        """
        raise NotImplementedError
    
    def get_metadata(self):
        """
        Expose swing metadata for scope isolation.
        
        From base Strategy class - returns registration info.
        Distinct from get_swing_metadata() which returns philosophy info.
        
        Returns:
            StrategyMetadata with supported_modes, supported_markets
        """
        from strategies.registry import StrategyMetadata
        
        swing_meta = self.get_swing_metadata()
        
        return StrategyMetadata(
            name=self.name,
            version=swing_meta.version,
            supported_markets=swing_meta.supported_markets,
            supported_modes=swing_meta.supported_modes,
            instrument_type="equity",
        )
    
    def get_strategy_type(self) -> str:
        """Strategy type identifier (always 'swing' for this base)."""
        return "swing"
    
    def get_supported_instruments(self) -> List[str]:
        """Supported instrument types (always ['equity'] for swing)."""
        return ["equity"]
    
    def should_run(self, market_state: Dict[str, Any]) -> bool:
        """
        Swing strategies run:
        - Entry: Any time (generated after market close for next open)
        - Exit: During market hours or EOD
        
        Does not enforce market hours - that's done by MarketHoursPolicy.
        """
        return self.enabled
    
    def validate_philosophy(self) -> bool:
        """
        Pre-flight check that philosophy is valid.
        
        Called at initialization. Subclasses can override to add
        custom validation (e.g., verify required config keys).
        
        Returns:
            True if philosophy is sound, False otherwise
        """
        try:
            metadata = self.get_swing_metadata()
            # Metadata dataclass __post_init__ validates it
            return True
        except (AssertionError, ValueError) as e:
            raise ValueError(f"Invalid strategy philosophy: {e}")
