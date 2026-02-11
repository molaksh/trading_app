"""
Tests for Phase F Kraken Market Signals Fetcher

Tests real-time market data fetching (ticker, order book, trades)
without executing any trades or modifying state.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from phase_f.fetchers.kraken_signals_fetcher import KrakenSignalsFetcher, MarketSignal


class TestKrakenSignalsFetcher:
    """Test Kraken signals fetcher"""
    
    def test_fetcher_initializes(self):
        """Test fetcher initialization with no auth"""
        fetcher = KrakenSignalsFetcher()
        assert fetcher.base_url == "https://api.kraken.com/0/public"
    
    def test_symbol_to_kraken_pair_mapping(self):
        """Test canonical symbol to Kraken pair mapping"""
        assert KrakenSignalsFetcher._symbol_to_kraken_pair("BTC") == "XBTUSD"
        assert KrakenSignalsFetcher._symbol_to_kraken_pair("ETH") == "ETHUSD"
        assert KrakenSignalsFetcher._symbol_to_kraken_pair("ADA") == "ADAUSD"
        assert KrakenSignalsFetcher._symbol_to_kraken_pair("UNKNOWN") is None
    
    def test_kraken_pair_to_symbol_mapping(self):
        """Test Kraken pair back to canonical symbol"""
        assert KrakenSignalsFetcher._map_from_kraken_pair("XBTUSD") == "BTC"
        assert KrakenSignalsFetcher._map_from_kraken_pair("ETHUSD") == "ETH"
        assert KrakenSignalsFetcher._map_from_kraken_pair("UNKNOWN") is None
    
    @patch('phase_f.fetchers.kraken_signals_fetcher.urllib.request.urlopen')
    def test_fetch_ticker_success(self, mock_urlopen):
        """Test successful ticker fetch"""
        # Mock Kraken response
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"result": {"XBTUSD": {"v": [0, 1000000], "c": [45000, 45000], "b": [44999, 100], "a": [45001, 100]}}}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        fetcher = KrakenSignalsFetcher()
        result = fetcher.fetch_ticker(["BTC"])
        
        assert result is not None
        assert "BTC" in result
        assert result["BTC"]["volume_24h"] == 1000000
        assert result["BTC"]["last_price"] == 45000
    
    def test_interpret_ticker_low_liquidity(self):
        """Test low liquidity interpretation"""
        signal = KrakenSignalsFetcher._interpret_ticker(50000, 0.05)
        assert "LOW_LIQUIDITY" in signal
    
    def test_interpret_ticker_high_volume(self):
        """Test high volume interpretation"""
        signal = KrakenSignalsFetcher._interpret_ticker(2000000, 0.02)
        assert "HIGH_VOLUME" in signal
    
    def test_interpret_ticker_wide_spread(self):
        """Test wide spread interpretation"""
        signal = KrakenSignalsFetcher._interpret_ticker(500000, 0.2)
        assert "WIDE_SPREAD" in signal
    
    def test_interpret_imbalance_bullish(self):
        """Test bullish order book imbalance"""
        signal = KrakenSignalsFetcher._interpret_imbalance(2.0)
        assert "BULLISH" in signal
    
    def test_interpret_imbalance_bearish(self):
        """Test bearish order book imbalance"""
        signal = KrakenSignalsFetcher._interpret_imbalance(0.5)
        assert "BEARISH" in signal
    
    def test_interpret_imbalance_neutral(self):
        """Test neutral order book imbalance"""
        signal = KrakenSignalsFetcher._interpret_imbalance(1.0)
        assert "NEUTRAL" in signal
    
    @patch('phase_f.fetchers.kraken_signals_fetcher.urllib.request.urlopen')
    def test_fetch_order_book_success(self, mock_urlopen):
        """Test successful order book fetch"""
        mock_response = MagicMock()
        # Mock order book with bids > asks (bullish)
        mock_response.read.return_value = b'{"result": {"XBTUSD": {"bids": [[45000, 100], [44999, 50]], "asks": [[45001, 50], [45002, 30]]}}}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        fetcher = KrakenSignalsFetcher()
        result = fetcher.fetch_order_book("BTC")
        
        assert result is not None
        assert len(result["bids"]) == 2
        assert len(result["asks"]) == 2
        assert result["bid_volume"] == 150
        assert result["ask_volume"] == 80
        assert result["imbalance_ratio"] > 1.5  # Bullish
    
    @patch('phase_f.fetchers.kraken_signals_fetcher.urllib.request.urlopen')
    def test_fetch_recent_trades_success(self, mock_urlopen):
        """Test successful recent trades fetch"""
        mock_response = MagicMock()
        # Mock recent trades
        mock_response.read.return_value = b'{"result": {"XBTUSD": [[45000, 1.5, 1707000000, "b", "market", ""], [45001, 2.0, 1707000001, "s", "market", ""]]}}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response
        
        fetcher = KrakenSignalsFetcher()
        result = fetcher.fetch_recent_trades("BTC")
        
        assert result is not None
        assert len(result) == 2
        assert result[0]["direction"] == "buy"
        assert result[0]["price"] == 45000
        assert result[1]["direction"] == "sell"
    
    def test_get_market_signals_with_mock_data(self):
        """Test comprehensive market signal snapshot with mocked fetches"""
        fetcher = KrakenSignalsFetcher()

        # Mock individual fetches
        fetcher.fetch_ticker = Mock(return_value={"BTC": {"volume_24h": 1000000, "bid_ask_spread_pct": 0.02, "signal": "HIGH_VOLUME"}})
        fetcher.fetch_order_book = Mock(return_value={"bids": [[45000, 100]], "asks": [[45001, 50]], "imbalance_ratio": 2.0, "signal": "BULLISH_IMBALANCE"})
        fetcher.fetch_recent_trades = Mock(return_value=[{"price": 45000, "volume": 1.5, "direction": "buy"}])

        result = fetcher.get_market_signals("BTC")

        assert result is not None
        assert result["symbol"] == "BTC"
        assert "timestamp" in result
        assert "ticker" in result
        assert "order_book" in result
        assert "trades" in result
        assert "overall_signal" in result
    
    def test_read_only_no_execution(self):
        """Verify fetcher is READ-ONLY (no broker imports)"""
        import inspect
        source = inspect.getsource(KrakenSignalsFetcher)

        # Verify no broker-related imports or execution code
        assert "from broker" not in source
        assert "import broker" not in source
        assert "execute_trade" not in source
        assert "place_order" not in source
        assert "kraken_client" not in source
        assert "kraken_adapter" not in source


class TestMarketSignalSchema:
    """Test immutable market signal schema"""
    
    def test_market_signal_immutable(self):
        """Test MarketSignal is frozen"""
        signal = MarketSignal(
            timestamp_utc="2026-02-11T08:00:00Z",
            symbol="BTC",
            signal_type="volume",
            value=1000000.0,
            context="High volume detected"
        )
        
        # Verify immutable
        with pytest.raises(AttributeError):
            signal.value = 500000.0
    
    def test_market_signal_schema(self):
        """Test MarketSignal structure"""
        signal = MarketSignal(
            timestamp_utc="2026-02-11T08:00:00Z",
            symbol="BTC",
            signal_type="spread",
            value=0.05,
            context="Tight spread"
        )
        
        assert signal.symbol == "BTC"
        assert signal.signal_type == "spread"
        assert signal.value == 0.05


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
