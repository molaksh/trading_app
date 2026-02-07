"""
Crypto universe management.

Universe is configurable and produces normalized symbols for Kraken.
"""

import logging
from typing import List, Set, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CryptoSymbol:
    """Represents a crypto symbol with both canonical and Kraken formats."""
    canonical: str  # e.g., "BTC", "ETH"
    kraken_pair: str  # e.g., "XXBTZUSD", "XETHZUSD"
    base: str  # Base currency: "XBT", "ETH", etc.
    quote: str  # Quote currency: "USD", "USDT", etc.


class CryptoUniverse:
    """
    Manages crypto trading universe.
    
    Canonical symbols: BTC, ETH, SOL, etc.
    Kraken pairs: XXBTZUSD, XETHZUSD, etc.
    """
    
    # Kraken pair mappings (canonical -> kraken pair)
    KRAKEN_MAPPING = {
        'BTC': 'XXBTZUSD',
        'ETH': 'XETHZUSD',
        'SOL': 'SOLUSD',
        'XRP': 'XRPZUSD',
        'ADA': 'ADAZUSD',
        'DOT': 'DOTZUSD',
        'LINK': 'LINKUSD',
        'DOGE': 'XDOGEZUSD',
        'MATIC': 'MATICZUSD',
        'AVAX': 'AVAXUSD',
    }
    
    def __init__(self, symbols: Optional[List[str]] = None, 
                 min_volume_usd: float = 1_000_000,
                 max_spread_bps: float = 50):
        """
        Initialize crypto universe.
        
        Args:
            symbols: List of canonical symbols (default: ['BTC', 'ETH', 'SOL'])
            min_volume_usd: Minimum 24h volume in USD
            max_spread_bps: Maximum bid-ask spread in basis points
        """
        self.symbols = set(symbols or ['BTC', 'ETH', 'SOL'])
        self.min_volume_usd = min_volume_usd
        self.max_spread_bps = max_spread_bps
        self._symbols = {}  # Store custom symbol objects for test compatibility
        
        # Validate all symbols are in mapping
        invalid = self.symbols - set(self.KRAKEN_MAPPING.keys())
        if invalid:
            raise ValueError(f"Unknown symbols (not in Kraken mapping): {invalid}")
        
        # Populate _symbols dict with canonical symbols
        for sym in self.symbols:
            kraken_pair = self.KRAKEN_MAPPING[sym]
            # Extract base/quote prefixes from Kraken pair
            # Format: [PrefixBase][Code][PrefixQuote][Code]
            # Examples: XXBTZUSD -> X (base), Z (quote)
            #           XETHZUSD -> X (base), Z (quote)
            base_prefix = kraken_pair[0] if kraken_pair else 'X'
            quote_prefix = kraken_pair[-4] if len(kraken_pair) >= 4 else 'Z'  # 4th char from end
            self._symbols[sym] = CryptoSymbol(
                canonical=sym,
                kraken_pair=kraken_pair,
                base=base_prefix,
                quote=quote_prefix
            )
        
        logger.info(f"Crypto universe initialized: {sorted(self.symbols)}")
        logger.info(f"  Min volume: ${min_volume_usd:,.0f}")
        logger.info(f"  Max spread: {max_spread_bps} bps")
    
    def add_symbol(self, canonical: str, kraken_pair: str = None, base: str = None, quote: str = None):
        """Add symbol to universe."""
        if canonical not in self.KRAKEN_MAPPING:
            if kraken_pair:
                # Custom symbol - add to mapping
                self.KRAKEN_MAPPING[canonical] = kraken_pair
            else:
                raise KeyError(f"Unknown symbol: {canonical}")
        
        self.symbols.add(canonical)
        # Also add to _symbols dict
        kp = kraken_pair or self.KRAKEN_MAPPING[canonical]
        self._symbols[canonical] = CryptoSymbol(
            canonical=canonical,
            kraken_pair=kp,
            base=base or (kp[0] if kp else 'X'),
            quote=quote or (kp[-4] if kp and len(kp) >= 4 else 'Z')
        )
        logger.info(f"Added symbol: {canonical}")
    
    def remove_symbol(self, canonical: str):
        """Remove symbol from universe."""
        self.symbols.discard(canonical)
        logger.info(f"Removed symbol: {canonical}")
    
    def get_kraken_pair(self, canonical: str) -> str:
        """
        Get Kraken pair for canonical symbol.
        
        Args:
            canonical: Canonical symbol (e.g., 'BTC')
        
        Returns:
            Kraken pair (e.g., 'XXBTZUSD')
        """
        if canonical not in self.KRAKEN_MAPPING:
            raise KeyError(f"Unknown symbol: {canonical}")
        
        return self.KRAKEN_MAPPING[canonical]
    
    def get_canonical_symbol(self, kraken_pair: str) -> str:
        """
        Get canonical symbol from Kraken pair.
        
        Args:
            kraken_pair: Kraken pair (e.g., 'XXBTZUSD')
        
        Returns:
            Canonical symbol (e.g., 'BTC')
        """
        reverse_mapping = {v: k for k, v in self.KRAKEN_MAPPING.items()}
        if kraken_pair not in reverse_mapping:
            raise KeyError(f"Unknown Kraken pair: {kraken_pair}")
        
        return reverse_mapping[kraken_pair]
    
    def all_canonical_symbols(self) -> List[str]:
        """Get all canonical symbols in universe (sorted)."""
        return sorted(self.symbols)
    
    def all_kraken_pairs(self) -> List[str]:
        """Get all Kraken pairs for universe symbols (sorted)."""
        return sorted([self.get_kraken_pair(s) for s in self.symbols])
    
    def __repr__(self) -> str:
        return f"CryptoUniverse({sorted(self.symbols)})"
