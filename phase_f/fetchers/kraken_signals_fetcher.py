"""
Kraken Market Signals Fetcher - Real-time market microstructure analysis

Fetches public market data from Kraken to complement narrative analysis:
- Ticker: 24h volume, bid/ask spread
- Order Book: Support/resistance walls, market depth
- Recent Trades: Trade distribution, aggressor direction
- OHLCV: Price action & volatility

All data is PUBLIC (no authentication required).
READ-ONLY - never places orders or modifies state.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import urllib.request
import json

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketSignal:
    """Immutable market signal from Kraken"""
    timestamp_utc: str
    symbol: str
    signal_type: str  # "volume", "spread", "depth", "volatility"
    value: float
    context: str  # Human-readable interpretation


class KrakenSignalsFetcher:
    """
    Fetch real-time market signals from Kraken public API.
    
    No authentication needed - uses public endpoints only.
    All data immutable and append-only.
    """
    
    BASE_URL = "https://api.kraken.com/0/public"
    
    def __init__(self):
        """Initialize fetcher with no credentials needed"""
        self.base_url = self.BASE_URL
        logger.info("KrakenSignalsFetcher initialized (public API, no auth)")
    
    def _kraken_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make public API request to Kraken"""
        try:
            url = f"{self.base_url}{endpoint}"
            if params:
                param_str = "&".join([f"{k}={v}" for k, v in params.items()])
                url = f"{url}?{param_str}"
            
            req = urllib.request.Request(url, headers={"User-Agent": "phase-f-market-correspondent"})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                
                if data.get("error") and len(data.get("error", [])) > 0:
                    logger.warning(f"Kraken API error: {data['error']}")
                    return None
                
                return data.get("result")
        except Exception as e:
            logger.error(f"Kraken request failed: {e}")
            return None
    
    def fetch_ticker(self, symbols: List[str]) -> Optional[Dict[str, Any]]:
        """
        Fetch ticker data (24h volume, bid/ask spread).
        
        Returns: {
            'symbol': {
                'volume_24h': float,
                'bid_ask_spread': float,
                'last_price': float,
                'signal': str
            }
        }
        """
        if not symbols:
            return None
        
        # Map canonical symbols to Kraken format (e.g., BTC -> XBTUSDT)
        kraken_pairs = self._map_to_kraken_pairs(symbols)
        
        try:
            result = self._kraken_request("/Ticker", {"pair": ",".join(kraken_pairs)})
            if not result:
                return None
            
            signals = {}
            for kraken_symbol, data in result.items():
                symbol = self._map_from_kraken_pair(kraken_symbol)
                if not symbol:
                    continue
                
                # Extract 24h volume and spreads
                volume_24h = float(data.get("v", [0])[1]) if data.get("v") else 0
                last_price = float(data.get("c", [0])[0]) if data.get("c") else 0
                bid = float(data.get("b", [0])[0]) if data.get("b") else 0
                ask = float(data.get("a", [0])[0]) if data.get("a") else 0
                
                spread = ((ask - bid) / last_price * 100) if last_price > 0 else 0
                
                signals[symbol] = {
                    "volume_24h": volume_24h,
                    "bid_ask_spread_pct": spread,
                    "last_price": last_price,
                    "signal": self._interpret_ticker(volume_24h, spread)
                }
            
            logger.info(f"Ticker data fetched for {len(signals)} symbols")
            return signals
        
        except Exception as e:
            logger.error(f"Failed to fetch ticker: {e}")
            return None
    
    def fetch_order_book(self, symbol: str, depth: int = 20) -> Optional[Dict[str, Any]]:
        """
        Fetch order book depth to detect support/resistance and conviction.
        
        Returns: {
            'bids': [(price, volume), ...],
            'asks': [(price, volume), ...],
            'imbalance_ratio': float,  # bid volume / ask volume
            'signal': str
        }
        """
        kraken_pair = self._symbol_to_kraken_pair(symbol)
        if not kraken_pair:
            return None
        
        try:
            result = self._kraken_request(f"/Depth", {"pair": kraken_pair, "count": depth})
            if not result or kraken_pair not in result:
                return None
            
            depth_data = result[kraken_pair]
            bids = [[float(p), float(v)] for p, v in depth_data.get("bids", [])]
            asks = [[float(p), float(v)] for p, v in depth_data.get("asks", [])]
            
            # Calculate imbalance
            bid_vol = sum(v for _, v in bids)
            ask_vol = sum(v for _, v in asks)
            imbalance = bid_vol / ask_vol if ask_vol > 0 else 0
            
            return {
                "bids": bids,
                "asks": asks,
                "bid_volume": bid_vol,
                "ask_volume": ask_vol,
                "imbalance_ratio": imbalance,
                "signal": self._interpret_imbalance(imbalance)
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch order book: {e}")
            return None
    
    def fetch_recent_trades(self, symbol: str, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch recent trades to detect buying/selling pressure.
        
        Returns: [
            {
                'price': float,
                'volume': float,
                'direction': 'buy'|'sell',
                'timestamp': str
            }, ...
        ]
        """
        kraken_pair = self._symbol_to_kraken_pair(symbol)
        if not kraken_pair:
            return None
        
        try:
            result = self._kraken_request(f"/Trades", {"pair": kraken_pair})
            if not result or kraken_pair not in result:
                return None
            
            trades = []
            for trade_data in result[kraken_pair][:limit]:
                price, volume, timestamp, direction, _, _ = trade_data
                trades.append({
                    "price": float(price),
                    "volume": float(volume),
                    "direction": "buy" if direction == "b" else "sell",
                    "timestamp": datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
                })
            
            logger.info(f"Fetched {len(trades)} recent trades for {symbol}")
            return trades
        
        except Exception as e:
            logger.error(f"Failed to fetch recent trades: {e}")
            return None
    
    def get_market_signals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Comprehensive market signal snapshot for epistemic analysis.
        
        Returns: {
            'symbol': str,
            'timestamp': str,
            'ticker': {...},
            'order_book': {...},
            'trades': [...],
            'overall_signal': str
        }
        """
        try:
            ticker = self.fetch_ticker([symbol])
            order_book = self.fetch_order_book(symbol)
            trades = self.fetch_recent_trades(symbol)
            
            if not ticker or symbol not in ticker:
                logger.warning(f"Could not fetch complete signals for {symbol}")
                return None
            
            signals = {
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ticker": ticker[symbol],
                "order_book": order_book or {},
                "trades": trades or [],
                "overall_signal": self._synthesize_signal(ticker[symbol], order_book, trades)
            }
            
            return signals
        
        except Exception as e:
            logger.error(f"Failed to get market signals: {e}")
            return None
    
    # Helper methods
    
    @staticmethod
    def _symbol_to_kraken_pair(symbol: str) -> Optional[str]:
        """Map canonical symbol to Kraken pair"""
        mapping = {
            "BTC": "XBTUSD",
            "ETH": "ETHUSD",
            "ADA": "ADAUSD",
            "SOL": "SOLUSD",
            "XRP": "XRPUSD",
        }
        return mapping.get(symbol.upper())

    @staticmethod
    def _map_to_kraken_pairs(symbols: List[str]) -> List[str]:
        """Map list of canonical symbols to Kraken pairs"""
        kraken_pairs = []
        for symbol in symbols:
            pair = KrakenSignalsFetcher._symbol_to_kraken_pair(symbol)
            if pair:
                kraken_pairs.append(pair)
        return kraken_pairs

    @staticmethod
    def _map_from_kraken_pair(kraken_pair: str) -> Optional[str]:
        """Map Kraken pair back to canonical symbol

        NOTE: Kraken API returns pairs with prefixes like XXBTZUSD (not XBTUSD)
        Handle both formats for compatibility
        """
        # Exact mappings
        mapping = {
            "XBTUSD": "BTC",
            "XXBTZUSD": "BTC",  # Kraken API format
            "ETHUSD": "ETH",
            "XETHUSD": "ETH",   # Alternative format
            "ADAUSD": "ADA",
            "XADAUSD": "ADA",
            "SOLUSD": "SOL",
            "XSOLUSD": "SOL",
            "XRPUSD": "XRP",
            "XXRPUSD": "XRP",   # Kraken API format
        }
        return mapping.get(kraken_pair)
    
    @staticmethod
    def _interpret_ticker(volume_24h: float, spread_pct: float) -> str:
        """Interpret ticker signals"""
        if volume_24h < 100000:
            return "LOW_LIQUIDITY: Volume below 100k USD"
        elif spread_pct > 0.1:
            return "WIDE_SPREAD: Bid-ask > 0.1%, liquidity stressed"
        elif volume_24h > 1000000:
            return "HIGH_VOLUME: Strong trading activity"
        else:
            return "NORMAL_VOLUME: Typical market conditions"
    
    @staticmethod
    def _interpret_imbalance(imbalance: float) -> str:
        """Interpret order book imbalance"""
        if imbalance > 1.5:
            return "BULLISH_IMBALANCE: More bids than asks (2:1 ratio)"
        elif imbalance < 0.67:
            return "BEARISH_IMBALANCE: More asks than bids (1:2 ratio)"
        else:
            return "NEUTRAL_IMBALANCE: Balanced order book"
    
    @staticmethod
    def _synthesize_signal(ticker: Dict, order_book: Optional[Dict], trades: Optional[List]) -> str:
        """Synthesize overall market signal"""
        signal_parts = []
        
        if ticker.get("signal"):
            signal_parts.append(ticker["signal"])
        
        if order_book and order_book.get("signal"):
            signal_parts.append(order_book["signal"])
        
        if trades and len(trades) > 0:
            buy_count = sum(1 for t in trades if t["direction"] == "buy")
            sell_count = len(trades) - buy_count
            if buy_count > sell_count * 1.5:
                signal_parts.append("BUY_PRESSURE: More buy trades")
            elif sell_count > buy_count * 1.5:
                signal_parts.append("SELL_PRESSURE: More sell trades")
        
        return " | ".join(signal_parts) if signal_parts else "UNKNOWN_SIGNAL"


def get_kraken_signals_fetcher() -> KrakenSignalsFetcher:
    """Convenience function"""
    return KrakenSignalsFetcher()
