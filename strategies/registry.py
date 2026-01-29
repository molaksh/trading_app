"""
Strategy registry and discovery for Phase 0.

Provides:
- Centralized strategy discovery
- Scope-aware filtering (load only strategies for current env/broker/mode/market)
- Metadata-based isolation
- Validation at startup

Each strategy must declare:
- supported_markets
- supported_modes
- instrument_type
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass

from config.scope import Scope, get_scope
from strategies.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class StrategyMetadata:
    """Metadata for strategy filtering and isolation."""
    name: str                          # e.g., "swing_equity"
    version: str                       # e.g., "1.0"
    supported_markets: List[str]       # e.g., ["us", "india"]
    supported_modes: List[str]         # e.g., ["swing", "daytrade"]
    instrument_type: str               # "equity", "option", "crypto"
    
    def supports_scope(self, scope: Scope) -> bool:
        """Check if strategy supports a given scope."""
        return (
            scope.market.lower() in [m.lower() for m in self.supported_markets]
            and scope.mode.lower() in [md.lower() for md in self.supported_modes]
        )


class StrategyRegistry:
    """
    Discover and filter strategies by scope.
    
    Ensures each scope loads ONLY relevant strategies.
    Adding a strategy to swing_us does not affect daytrade_us.
    """
    
    _registry: Dict[str, StrategyMetadata] = {}
    _initialized = False
    
    @classmethod
    def discover_strategies(cls) -> Dict[str, StrategyMetadata]:
        """
        Discover all available strategies.
        
        This scans for strategy classes and extracts metadata.
        Should be called once at startup.
        
        Returns:
            Dict of strategy_name -> StrategyMetadata
        """
        if cls._initialized:
            return cls._registry
        
        logger.info("Discovering strategies...")
        
        # Import all strategy modules from canonical core location
        from core.strategies.equity.swing import SwingEquityStrategy
        
        # Create instances and extract metadata
        strategies = {
            "swing_equity": SwingEquityStrategy(),
        }
        
        # Extract metadata
        for strategy_name, strategy in strategies.items():
            metadata = strategy.get_metadata()
            cls._registry[strategy_name] = metadata
            logger.info(
                f"  Discovered {strategy_name}: "
                f"markets={metadata.supported_markets}, "
                f"modes={metadata.supported_modes}"
            )
        
        cls._initialized = True
        return cls._registry
    
    @classmethod
    def get_strategies_for_scope(
        cls,
        scope: Scope = None
    ) -> Dict[str, StrategyMetadata]:
        """
        Get all strategies relevant to a scope.
        
        Filters by scope.market and scope.mode.
        
        Args:
            scope: Optional Scope; defaults to global scope
        
        Returns:
            Dict of strategy_name -> StrategyMetadata (filtered)
        """
        if scope is None:
            scope = get_scope()
        
        all_strategies = cls.discover_strategies()
        
        filtered = {
            name: metadata
            for name, metadata in all_strategies.items()
            if metadata.supports_scope(scope)
        }
        
        logger.info(
            f"Strategies for scope {scope}: "
            f"{list(filtered.keys())} "
            f"(filtered from {len(all_strategies)} total)"
        )
        
        return filtered
    
    @classmethod
    def instantiate_strategies_for_scope(
        cls,
        scope: Scope = None
    ) -> List[Strategy]:
        """
        Instantiate all strategies relevant to a scope.
        
        Args:
            scope: Optional Scope; defaults to global scope
        
        Returns:
            List of instantiated Strategy objects
        """
        if scope is None:
            scope = get_scope()
        
        strategies = cls.get_strategies_for_scope(scope)
        
        # Instantiate each
        instances = []
        for strategy_name in strategies:
            if strategy_name == "swing_equity":
                from core.strategies.equity.swing import SwingEquityStrategy
                instance = SwingEquityStrategy()
            else:
                logger.warning(f"Unknown strategy: {strategy_name}")
                continue
            
            instances.append(instance)
        
        logger.info(f"Instantiated {len(instances)} strategies for {scope}")
        
        return instances
    
    @classmethod
    def validate_scope_has_strategies(cls, scope: Scope) -> bool:
        """
        Validate that scope has at least one strategy.
        
        Useful for startup validation.
        
        Args:
            scope: Scope to validate
        
        Returns:
            True if at least one strategy available
        
        Raises:
            ValueError: If no strategies available for scope
        """
        strategies = cls.get_strategies_for_scope(scope)
        
        if not strategies:
            raise ValueError(
                f"No strategies available for scope {scope}. "
                f"This may indicate misconfigured scope or missing strategies."
            )
        
        return True


def get_strategies_for_scope(scope: Scope = None) -> Dict[str, StrategyMetadata]:
    """Convenience function to get filtered strategies."""
    return StrategyRegistry.get_strategies_for_scope(scope)


def instantiate_strategies_for_scope(scope: Scope = None) -> List[Strategy]:
    """Convenience function to instantiate strategies."""
    return StrategyRegistry.instantiate_strategies_for_scope(scope)
