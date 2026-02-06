"""
Test crypto universe management and symbol mappings.
"""

import pytest

from crypto.universe import CryptoUniverse, CryptoSymbol


class TestCryptoUniverse:
    """Test crypto symbol universe."""
    
    @pytest.fixture
    def universe(self):
        """Create crypto universe with default Kraken mappings."""
        return CryptoUniverse()
    
    def test_universe_initialization(self, universe):
        """Test universe initializes with default symbols."""
        # Should have at least the core symbols
        canonical = universe.all_canonical_symbols()
        
        assert 'BTC' in canonical
        assert 'ETH' in canonical
        assert 'SOL' in canonical
    
    def test_kraken_pair_mapping(self, universe):
        """Test canonical symbols map to Kraken pairs."""
        # BTC should map to XXBTZUSD
        kraken_pair = universe.get_kraken_pair('BTC')
        assert kraken_pair == 'XXBTZUSD'
        
        # ETH should map to XETHZUSD
        kraken_pair = universe.get_kraken_pair('ETH')
        assert kraken_pair == 'XETHZUSD'
        
        # SOL should map to SOLUSD
        kraken_pair = universe.get_kraken_pair('SOL')
        assert kraken_pair == 'SOLUSD'
    
    def test_canonical_from_kraken_pair(self, universe):
        """Test reverse lookup: Kraken pair to canonical."""
        canonical = universe.get_canonical_symbol('XXBTZUSD')
        assert canonical == 'BTC'
        
        canonical = universe.get_canonical_symbol('XETHZUSD')
        assert canonical == 'ETH'
        
        canonical = universe.get_canonical_symbol('SOLUSD')
        assert canonical == 'SOL'
    
    def test_all_kraken_pairs(self, universe):
        """Test getting all Kraken pairs."""
        pairs = universe.all_kraken_pairs()
        
        assert 'XXBTZUSD' in pairs
        assert 'XETHZUSD' in pairs
        assert 'SOLUSD' in pairs
        
        # Should be same length as canonical
        assert len(pairs) == len(universe.all_canonical_symbols())
    
    def test_add_custom_symbol(self, universe):
        """Test adding custom symbol to universe."""
        universe.add_symbol(
            canonical='NEW',
            kraken_pair='NEWZUSD',
            base='NEW',
            quote='USD',
        )
        
        assert 'NEW' in universe.all_canonical_symbols()
        assert universe.get_kraken_pair('NEW') == 'NEWZUSD'
        assert universe.get_canonical_symbol('NEWZUSD') == 'NEW'
    
    def test_remove_symbol(self, universe):
        """Test removing symbol from universe."""
        initial_count = len(universe.all_canonical_symbols())
        
        # Remove ETH
        universe.remove_symbol('ETH')
        
        assert 'ETH' not in universe.all_canonical_symbols()
        assert len(universe.all_canonical_symbols()) == initial_count - 1
    
    def test_symbol_metadata(self, universe):
        """Test accessing symbol metadata."""
        # Get BTC symbol object
        btc = universe._symbols.get('BTC')
        
        assert btc is not None
        assert btc.canonical == 'BTC'
        assert btc.kraken_pair == 'XXBTZUSD'
        assert btc.base == 'X'
        assert btc.quote == 'Z'
    
    def test_invalid_canonical_symbol(self, universe):
        """Test error on invalid canonical symbol."""
        with pytest.raises(KeyError):
            universe.get_kraken_pair('INVALID')
    
    def test_invalid_kraken_pair(self, universe):
        """Test error on invalid Kraken pair."""
        with pytest.raises(KeyError):
            universe.get_canonical_symbol('INVALIDUSD')
    
    def test_symbol_object_creation(self):
        """Test CryptoSymbol dataclass."""
        sym = CryptoSymbol(
            canonical='XRP',
            kraken_pair='XXRPZUSD',
            base='X',
            quote='Z',
        )
        
        assert sym.canonical == 'XRP'
        assert sym.kraken_pair == 'XXRPZUSD'
        assert sym.base == 'X'
        assert sym.quote == 'Z'
    
    def test_large_universe(self):
        """Test universe with many symbols."""
        universe = CryptoUniverse()
        
        # Add 20 custom symbols
        for i in range(20):
            universe.add_symbol(
                canonical=f'CRY{i}',
                kraken_pair=f'CRY{i}USD',
                base='CRY',
                quote='USD',
            )
        
        all_symbols = universe.all_canonical_symbols()
        
        # Should have original + 20 new
        assert len(all_symbols) >= 20
    
    def test_symbol_pairs_consistency(self, universe):
        """Test that all canonical symbols have Kraken pairs."""
        canonical_symbols = universe.all_canonical_symbols()
        kraken_pairs = universe.all_kraken_pairs()
        
        # Should be 1:1 mapping
        assert len(canonical_symbols) == len(kraken_pairs)
        
        # All canonical should map to pairs
        for sym in canonical_symbols:
            pair = universe.get_kraken_pair(sym)
            assert pair is not None
            
            # Reverse mapping should work
            assert universe.get_canonical_symbol(pair) == sym
