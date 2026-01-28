"""
Base Strategy Interface - Core abstraction for all trading strategies.

ALL strategies emit TRADE INTENT, never place orders directly.
Core engine translates intent → risk checks → execution.

PHILOSOPHY:
- Strategies decide WHAT to trade and WHY
- Engine decides HOW and WHEN (with risk/guard approval)
- Brokers handle WHERE (order routing)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum

from risk.scaling_policy import StrategyScalingPolicy

# Avoid circular import
def _get_strategy_metadata():
    """Import here to avoid circular dependency."""
    from strategies.registry import StrategyMetadata
    return StrategyMetadata


class TradeDirection(Enum):
    """Universal trade direction."""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"  # For spreads, covered calls, etc.


class IntentType(Enum):
    """Type of trade intent."""
    ENTRY = "entry"      # Open new position
    EXIT = "exit"        # Close existing position
    ADJUST = "adjust"    # Modify existing position (options: roll, add leg)


class IntentUrgency(Enum):
    """How quickly intent should be acted upon."""
    IMMEDIATE = "immediate"  # Execute ASAP (risk exits, emergency)
    EOD = "eod"             # End of day execution
    NEXT_OPEN = "next_open"  # Next market open
    DISCRETIONARY = "discretionary"  # Anytime within session


@dataclass
class TradeIntent:
    """
    Universal trade intent emitted by strategies.
    
    Strategy emits intent → Engine validates → Guard checks → Risk approves → Broker executes
    
    This is the ONLY way strategies communicate trade decisions.
    """
    strategy_name: str           # e.g., "swing_equity", "cash_secured_put"
    instrument_type: str         # e.g., "equity", "option", "crypto"
    symbol: str                  # Ticker or contract identifier
    direction: TradeDirection    # LONG, SHORT, NEUTRAL
    intent_type: IntentType      # ENTRY, EXIT, ADJUST
    urgency: IntentUrgency       # When to execute
    
    # Quantitative
    quantity: Optional[int] = None          # Shares/contracts (None = let risk manager decide)
    price_limit: Optional[float] = None     # Max entry / Min exit price
    confidence: Optional[float] = None      # Strategy confidence (0-1 or 1-5)
    
    # Metadata
    reason: str = ""                        # Human-readable justification
    features: Dict[str, Any] = None         # Strategy-specific features
    risk_metadata: Dict[str, Any] = None    # For risk manager context
    
    # Timestamps
    generated_at: datetime = None           # When intent was created
    valid_until: Optional[datetime] = None  # Intent expiration
    
    def __post_init__(self):
        """Set defaults."""
        if self.generated_at is None:
            self.generated_at = datetime.now()
        if self.features is None:
            self.features = {}
        if self.risk_metadata is None:
            self.risk_metadata = {}


class Strategy(ABC):
    """
    Base interface for all trading strategies.
    
    RESPONSIBILITIES:
    - Analyze market data
    - Generate trade intents
    - Explain decisions
    
    NOT RESPONSIBLE FOR:
    - Order placement
    - Risk checks
    - Position sizing (unless strategy-specific)
    - PDT compliance
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize strategy.
        
        Args:
            name: Unique strategy identifier
            config: Strategy-specific configuration
        """
        self.name = name
        self.config = config
        self.enabled = config.get("enabled", True)
        
        # Strategy declares its multi-entry policy
        # If not provided, defaults to single-entry (no scaling)
        self._scaling_policy = self._init_scaling_policy()
    
    def _init_scaling_policy(self) -> StrategyScalingPolicy:
        """
        Initialize scaling policy from config.
        
        Override in subclass to customize. Default: no scaling.
        
        Returns:
            StrategyScalingPolicy (defaults to single-entry if not configured)
        """
        scaling_config = self.config.get("scaling_policy", {})
        
        if not scaling_config.get("allows_multiple_entries", False):
            # Default: single-entry only
            return StrategyScalingPolicy(allows_multiple_entries=False)
        
        # Multi-entry configured
        policy = StrategyScalingPolicy(
            allows_multiple_entries=True,
            max_entries_per_symbol=scaling_config.get("max_entries_per_symbol", 3),
            max_total_position_pct=scaling_config.get("max_total_position_pct", 5.0),
            scaling_type=scaling_config.get("scaling_type", "pyramid"),
            min_bars_between_entries=scaling_config.get("min_bars_between_entries", 5),
            min_time_between_entries_seconds=scaling_config.get("min_time_between_entries_seconds", 300),
            min_signal_strength_for_add=scaling_config.get("min_signal_strength_for_add", 3.0),
            max_atr_drawdown_multiple=scaling_config.get("max_atr_drawdown_multiple", 2.0),
            require_no_lower_low=scaling_config.get("require_no_lower_low", True),
            require_volatility_above_median=scaling_config.get("require_volatility_above_median", True),
        )
        
        # Validate policy
        is_valid, error_msg = policy.validate()
        if not is_valid:
            raise ValueError(f"Invalid scaling policy for {self.name}: {error_msg}")
        
        return policy
    
    @property
    def scaling_policy(self) -> StrategyScalingPolicy:
        """Get this strategy's scaling policy."""
        return self._scaling_policy
    
    @abstractmethod
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate entry intents based on market analysis.
        
        Args:
            market_data: Current market state (prices, volume, etc.)
            portfolio_state: Current positions, buying power, etc.
        
        Returns:
            List of TradeIntent objects (can be empty)
        """
        pass
    
    @abstractmethod
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Generate exit intents for existing positions.
        
        Args:
            positions: List of open positions managed by this strategy
            market_data: Current market state
        
        Returns:
            List of TradeIntent objects (can be empty)
        """
        pass
    
    @abstractmethod
    def get_metadata(self) -> "StrategyMetadata":
        """
        Get strategy metadata for scope filtering and isolation.
        
        Returns:
            StrategyMetadata instance
        
        Must be implemented by all strategies to declare:
        - supported_markets (["us"], ["india"], etc.)
        - supported_modes (["swing"], ["daytrade"], etc.)
        - instrument_type ("equity", "option", "crypto", etc.)
        """
        StrategyMetadata = _get_strategy_metadata()
        return StrategyMetadata(
            name=self.name,
            version="1.0",
            supported_markets=["us"],  # Override in subclass
            supported_modes=["swing"],  # Override in subclass
            instrument_type="equity",  # Override in subclass
        )
    
    def get_strategy_type(self) -> str:
        """Return strategy type identifier (e.g., 'swing', 'options', 'intraday')."""
        pass
    
    @abstractmethod
    def get_supported_instruments(self) -> List[str]:
        """Return list of supported instrument types."""
        pass
    
    def should_run(self, market_state: Dict[str, Any]) -> bool:
        """
        Determine if strategy should run given current market state.
        
        Default: runs if enabled and market is open.
        Override for custom logic (e.g., only run after hours).
        
        Args:
            market_state: Market status (open, close, etc.)
        
        Returns:
            True if strategy should generate intents
        """
        if not self.enabled:
            return False
        
        return market_state.get("is_open", False)
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)
    
    def update_config(self, key: str, value: Any) -> None:
        """Update configuration value."""
        self.config[key] = value
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', enabled={self.enabled})"
