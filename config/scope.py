"""
Scope definition and management for Phase 0.

A SCOPE is a first-class concept that isolates configuration, strategies,
brokers, and ML artifacts by environment, broker, mode, and market.

Format: SCOPE := <ENV>_<BROKER>_<MODE>_<MARKET>
Examples:
  - Paper_alpaca_swing_us
  - Live_ibkr_day_trade_us
  - Paper_zerodha_options_india
  - Live_crypto_crypto_us

SCOPE is immutable per runtime and used for:
  - Selecting broker adapter
  - Filtering strategies
  - Namespacing all storage (logs, models, state)
  - Configuring risk limits
  - Versioning ML artifacts
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class Environment(Enum):
    """Trading environment: simulated or real."""
    PAPER = "paper"      # Paper trading (simulated)
    LIVE = "live"        # Live trading (real money)


class Broker(Enum):
    """Supported broker implementations."""
    ALPACA = "alpaca"           # Alpaca (US, swing/daytrade)
    IBKR = "ibkr"               # Interactive Brokers (US/intl, multi-mode)
    ZERODHA = "zerodha"         # Zerodha (India)
    NSE_SIMULATOR = "nse_simulator"  # NSE simulated broker (India paper trading)
    CRYPTO_EXCHANGE = "crypto"  # Generic crypto exchange


class Mode(Enum):
    """Trading mode (strategy type)."""
    SWING = "swing"           # Swing trading (2-20 days)
    DAYTRADE = "daytrade"     # Intraday trading (minutes-hours)
    OPTIONS = "options"       # Options strategies
    CRYPTO = "crypto"         # Cryptocurrency trading
    INVEST = "invest"         # Long-term investing


class Market(Enum):
    """Market/geographic region."""
    US = "us"                 # US markets
    INDIA = "india"           # Indian markets
    GLOBAL = "global"         # Global/crypto


# Allowed combinations (for validation)
ALLOWED_SCOPES = [
    # Paper trading - US
    ("paper", "alpaca", "swing", "us"),
    ("paper", "alpaca", "daytrade", "us"),
    ("paper", "ibkr", "swing", "us"),
    ("paper", "ibkr", "daytrade", "us"),
    
    # Paper trading - India
    ("paper", "zerodha", "options", "india"),
    ("paper", "zerodha", "swing", "india"),
    ("paper", "nse_simulator", "swing", "india"),  # NEW: NSE simulator
    
    # Paper trading - Global/Crypto
    ("paper", "crypto", "crypto", "global"),
    
    # Live trading
    ("live", "alpaca", "swing", "us"),
    ("live", "ibkr", "daytrade", "us"),
    ("live", "ibkr", "day_trade", "us"),  # Handle both formats
    ("live", "zerodha", "options", "india"),
    ("live", "crypto", "crypto", "global"),
]


@dataclass(frozen=True)
class Scope:
    """
    Immutable scope definition.
    
    Contains all configuration dimensions needed to select:
    - Broker adapter
    - Risk limits
    - Strategy set
    - ML artifacts
    - Storage paths
    """
    env: str           # "paper" or "live"
    broker: str        # "alpaca", "ibkr", "zerodha", "crypto"
    mode: str          # "swing", "daytrade", "options", "crypto"
    market: str        # "us", "india", "global"
    
    def __post_init__(self):
        """Validate scope on creation."""
        self._validate()
    
    def _validate(self) -> None:
        """Validate scope is in allowed combinations."""
        key = (self.env.lower(), self.broker.lower(), self.mode.lower(), self.market.lower())
        
        # Normalize for comparison
        valid_keys = [(e, b, md, mk) for e, b, md, mk in ALLOWED_SCOPES]
        
        if key not in valid_keys:
            valid_examples = ", ".join([
                f"{e}_{b}_{md}_{mk}" 
                for e, b, md, mk in valid_keys[:5]
            ])
            raise ValueError(
                f"Invalid scope: {self}. "
                f"Allowed combinations: {valid_examples} ..."
            )
    
    def __str__(self) -> str:
        """Return canonical SCOPE string."""
        return f"{self.env}_{self.broker}_{self.mode}_{self.market}".lower()
    
    def __repr__(self) -> str:
        return f"Scope({str(self)})"
    
    @classmethod
    def from_string(cls, scope_str: str) -> "Scope":
        """
        Parse scope from string.
        
        Args:
            scope_str: "Paper_alpaca_swing_us" or "paper_alpaca_swing_us"
        
        Returns:
            Scope instance
        
        Raises:
            ValueError: If format invalid
        """
        parts = scope_str.lower().split("_")
        if len(parts) != 4:
            raise ValueError(
                f"Invalid scope format: {scope_str}. "
                f"Expected ENV_BROKER_MODE_MARKET (e.g., paper_alpaca_swing_us)"
            )
        
        env, broker, mode, market = parts
        return cls(env=env, broker=broker, mode=mode, market=market)
    
    @classmethod
    def from_env(cls) -> "Scope":
        """
        Load scope from environment variable.
        
        Reads SCOPE env var or constructs from:
        - ENV (paper/live)
        - BROKER (alpaca/ibkr/zerodha/crypto)
        - MODE (swing/daytrade/options/crypto)
        - MARKET (us/india/global)
        
        Returns:
            Scope instance
        
        Raises:
            ValueError: If environment vars invalid or missing
        """
        scope_str = os.getenv("SCOPE")
        
        if scope_str:
            logger.info(f"Loading Scope from SCOPE env var: {scope_str}")
            return cls.from_string(scope_str)
        
        # Fallback: construct from individual vars
        env = os.getenv("ENV", "paper").lower()
        broker = os.getenv("BROKER", "alpaca").lower()
        mode = os.getenv("MODE", "swing").lower()
        market = os.getenv("MARKET", "us").lower()
        
        scope_str = f"{env}_{broker}_{mode}_{market}"
        logger.info(
            f"Loading Scope from env vars: "
            f"ENV={env}, BROKER={broker}, MODE={mode}, MARKET={market}"
        )
        
        return cls(env=env, broker=broker, mode=mode, market=market)


def get_scope() -> Scope:
    """
    Get the global scope instance.
    
    WARNING: This is set once at startup. Do NOT create multiple scopes.
    Use this singleton for all scope-aware decisions.
    """
    if not hasattr(get_scope, "_instance"):
        get_scope._instance = Scope.from_env()
    return get_scope._instance


def set_scope(scope: Scope) -> None:
    """Override scope (testing only)."""
    get_scope._instance = scope
