"""
SwingEquityStrategy - Orchestrator/Container for swing trading philosophies.

ARCHITECTURAL ROLE:
This is NOT a trading philosophy. It's a STRATEGY CONTAINER that:

1. Discovers and loads all individual SwingStrategy implementations
2. Delegates signal generation to each philosophy
3. Collects entry and exit intents from all strategies
4. Attaches metadata to each intent (strategy_id, philosophy, risks, caveats)
5. Passes intents downstream unchanged (ML → Risk → Guards)

PHILOSOPHY INDEPENDENCE:
- Trend Pullback Strategy: Shallow pullbacks in confirmed uptrends
- Momentum Breakout Strategy: Strength continuation with volume confirmation
- Mean Reversion Strategy: Snapbacks within valid trends
- Volatility Squeeze Strategy: Expansion after compression
- Event-Driven Strategy: Post-event mean reversion

Each strategy is MARKET-AGNOSTIC:
- No US/India-specific assumptions
- No hardcoded market hours
- Market-specific rules applied via MarketHoursPolicy
"""

import logging
from typing import List, Dict, Any

from strategies.base import (
    Strategy,
    TradeIntent,
)

logger = logging.getLogger(__name__)


class SwingEquityStrategy(Strategy):
    """
    Swing trading container/orchestrator.
    
    RESPONSIBILITY:
    - Load all swing strategy philosophies
    - Delegate signal generation to each
    - Aggregate intents with philosophy metadata
    - NO TRADING LOGIC (logic lives in individual strategies)
    
    CONFIGURATION:
    - enabled_strategies: List of philosophy names to run
    - strategy_configs: Per-strategy parameter overrides
    - position_limits: Global position limits
    """
    
    def __init__(self, name: str = "swing_equity", config: Dict[str, Any] = None):
        """
        Initialize swing strategy container.
        
        Config keys:
        - enabled_strategies: List of strategy names (default: all)
        - max_positions: Global position limit (default: 10)
        - enabled: Whether container is active (default: True)
        """
        default_config = {
            "enabled": True,
            "max_positions": 10,
            "enabled_strategies": [
                "trend_pullback",
                "momentum_breakout",
                "mean_reversion",
                "volatility_squeeze",
                "event_driven",
            ],
            # Per-strategy overrides (optional)
            "strategy_configs": {},
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(name, default_config)
        
        # Load all swing strategies
        self.strategies = self._load_strategies()
        
        logger.info(f"SwingEquityStrategy container initialized: {self.name}")
        logger.info(f"  Strategies loaded: {len(self.strategies)}")
        for strat in self.strategies:
            logger.info(f"    - {strat.name}: {strat.get_swing_metadata().strategy_name}")
    
    def _load_strategies(self) -> List:
        """
        Discover and load all swing strategy implementations.
        
        Returns:
            List of instantiated strategy objects
        """
        strategies = []
        enabled_names = self.config.get("enabled_strategies", [])
        per_strategy_configs = self.config.get("strategy_configs", {})
        
        # Import all strategy implementations
        from strategies.us.equity.swing.swing_trend_pullback import SwingTrendPullbackStrategy
        from strategies.us.equity.swing.swing_momentum_breakout import SwingMomentumBreakoutStrategy
        from strategies.us.equity.swing.swing_mean_reversion import SwingMeanReversionStrategy
        from strategies.us.equity.swing.swing_volatility_squeeze import SwingVolatilitySqueezeStrategy
        from strategies.us.equity.swing.swing_event_driven import SwingEventDrivenStrategy
        
        strategy_classes = [
            ("trend_pullback", SwingTrendPullbackStrategy),
            ("momentum_breakout", SwingMomentumBreakoutStrategy),
            ("mean_reversion", SwingMeanReversionStrategy),
            ("volatility_squeeze", SwingVolatilitySqueezeStrategy),
            ("event_driven", SwingEventDrivenStrategy),
        ]
        
        for strategy_id, strategy_class in strategy_classes:
            if strategy_id not in enabled_names:
                logger.info(f"Strategy disabled: {strategy_id}")
                continue
            
            # Use per-strategy config if provided, else default
            strat_config = per_strategy_configs.get(strategy_id, {})
            
            try:
                strategy = strategy_class(config=strat_config)
                strategies.append(strategy)
                logger.info(f"Loaded strategy: {strategy.name}")
            except Exception as e:
                logger.error(f"Failed to load strategy {strategy_id}: {e}")
        
        return strategies
    
    def generate_entry_intents(
        self,
        market_data: Dict[str, Any],
        portfolio_state: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Aggregate entry intents from all strategies.
        
        PROCESS:
        1. Call generate_entry_intents() on each strategy
        2. Collect all intents
        3. Attach strategy metadata to each intent
        4. Respect global position limits
        5. Return aggregated list unchanged
        
        Args:
            market_data: Market data for all strategies
            portfolio_state: Current portfolio state
        
        Returns:
            List of TradeIntent from all active strategies
        """
        all_intents = []
        
        for strategy in self.strategies:
            try:
                intents = strategy.generate_entry_intents(market_data, portfolio_state)
                
                # Attach philosophy metadata to each intent
                for intent in intents:
                    # Preserve original intent attributes
                    # Add philosophy metadata
                    if not intent.risk_metadata:
                        intent.risk_metadata = {}
                    
                    metadata = strategy.get_swing_metadata()
                    intent.risk_metadata.update({
                        "strategy_id": metadata.strategy_id,
                        "strategy_philosophy": metadata.philosophy,
                        "strategy_edge": metadata.edge,
                        "strategy_risks": metadata.risks,
                        "strategy_caveats": metadata.caveats,
                        "strategy_version": metadata.version,
                    })
                    
                    all_intents.append(intent)
                    logger.info(
                        f"Intent from {strategy.name}: {intent.symbol} "
                        f"(philosophy: {metadata.strategy_name})"
                    )
            
            except Exception as e:
                logger.error(f"Error generating intents from {strategy.name}: {e}")
                continue
        
        # Respect global position limits
        current_positions = portfolio_state.get("positions", [])
        max_positions = self.config["max_positions"]
        available_slots = max_positions - len(current_positions)
        
        if len(all_intents) > available_slots:
            logger.info(
                f"Capping intents: {len(all_intents)} → {available_slots} "
                f"(positions: {len(current_positions)}/{max_positions})"
            )
            all_intents = all_intents[:available_slots]
        
        logger.info(f"Total entry intents: {len(all_intents)} from {len(self.strategies)} strategies")
        return all_intents
    
    def generate_exit_intents(
        self,
        positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> List[TradeIntent]:
        """
        Aggregate exit intents from all strategies.
        
        PROCESS:
        1. For each position, determine which strategy entered it
        2. Call that strategy's generate_exit_intents()
        3. Collect all exit signals
        4. Attach strategy metadata to each
        5. Return unchanged
        
        Args:
            positions: Positions to check for exits
            market_data: Current market data
        
        Returns:
            List of exit intents from all strategies
        """
        all_intents = []
        
        # Group positions by strategy
        positions_by_strategy = self._group_positions_by_strategy(positions)
        
        for strategy in self.strategies:
            strat_positions = positions_by_strategy.get(strategy.name, [])
            
            if not strat_positions:
                logger.debug(f"No positions for strategy {strategy.name}")
                continue
            
            try:
                intents = strategy.generate_exit_intents(strat_positions, market_data)
                
                # Attach strategy metadata
                for intent in intents:
                    if not intent.risk_metadata:
                        intent.risk_metadata = {}
                    
                    metadata = strategy.get_swing_metadata()
                    intent.risk_metadata.update({
                        "strategy_id": metadata.strategy_id,
                        "strategy_philosophy": metadata.philosophy,
                        "strategy_version": metadata.version,
                    })
                    
                    all_intents.append(intent)
                    logger.info(f"Exit intent from {strategy.name}: {intent.symbol}")
            
            except Exception as e:
                logger.error(f"Error generating exits from {strategy.name}: {e}")
                continue
        
        logger.info(f"Total exit intents: {len(all_intents)} from {len(self.strategies)} strategies")
        return all_intents
    
    def _group_positions_by_strategy(self, positions: List[Dict[str, Any]]) -> Dict[str, List]:
        """
        Group positions by the strategy that entered them.
        
        Uses risk_metadata.strategy_type to identify originating strategy.
        Defaults to first strategy if unknown.
        
        Args:
            positions: List of positions
        
        Returns:
            Dict mapping strategy name → list of positions
        """
        grouped = {strat.name: [] for strat in self.strategies}
        
        for position in positions:
            strategy_type = (
                position.get("risk_metadata", {}).get("strategy_type", "swing")
            )
            
            # Find matching strategy
            matched = False
            for strategy in self.strategies:
                if strategy.name.replace("_", "") in strategy_type.lower():
                    grouped[strategy.name].append(position)
                    matched = True
                    break
            
            if not matched:
                # Default to first strategy if no match
                if self.strategies:
                    grouped[self.strategies[0].name].append(position)
                    logger.debug(
                        f"Position {position.get('symbol')} has unknown strategy, "
                        f"defaulting to {self.strategies[0].name}"
                    )
        
        return grouped
    
    def get_metadata(self):
        """
        Declare scope metadata for strategy container.
        
        Returns:
            StrategyMetadata
        """
        from strategies.registry import StrategyMetadata
        return StrategyMetadata(
            name="swing_equity",
            version="2.0",  # Updated to reflect container pattern
            supported_markets=["us", "india"],  # All strategies are market-agnostic
            supported_modes=["swing"],
            instrument_type="equity",
        )
    
    def get_strategy_type(self) -> str:
        """Strategy type identifier."""
        return "swing"
    
    def get_supported_instruments(self) -> List[str]:
        """Supported instrument types."""
        return ["equity"]
    
    def should_run(self, market_state: Dict[str, Any]) -> bool:
        """
        Swing container runs when any strategy is enabled.
        Individual strategies handle their own timing.
        """
        return self.enabled and len(self.strategies) > 0
    
    def get_active_strategies(self) -> List[str]:
        """Return list of active strategy names."""
        return [s.name for s in self.strategies]
    
    def get_strategy_philosophies(self) -> List[Dict[str, Any]]:
        """
        Return metadata for all active strategies.
        
        Useful for logging, monitoring, and explaining to users.
        
        Returns:
            List of dicts with strategy metadata
        """
        philosophies = []
        for strategy in self.strategies:
            metadata = strategy.get_swing_metadata()
            philosophies.append({
                "id": metadata.strategy_id,
                "name": metadata.strategy_name,
                "philosophy": metadata.philosophy,
                "edge": metadata.edge,
                "risks": metadata.risks,
                "caveats": metadata.caveats,
                "supported_markets": metadata.supported_markets,
                "version": metadata.version,
            })
        return philosophies
