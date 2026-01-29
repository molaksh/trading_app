"""
NSE Swing Trading Universe.

Curated list of high-quality NSE stocks suitable for swing trading:
- High liquidity
- Large & mid-cap
- Clean price action
- NIFTY 50 + select NIFTY Next 50

Universe Criteria:
- Minimum avg daily volume: 50 lakh shares
- Market cap: > ₹10,000 crore
- Clean corporate governance
- Avoid illiquid small caps
"""

# NSE Swing Trading Universe
# Format: List of NSE symbols (without .NS suffix)

NSE_SWING_UNIVERSE = [
    # NIFTY 50 Blue Chips
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "HINDUNILVR",
    "ITC",
    "SBIN",
    "BHARTIARTL",
    "KOTAKBANK",
    "LT",
    "AXISBANK",
    "BAJFINANCE",
    "ASIANPAINT",
    "MARUTI",
    "HCLTECH",
    "SUNPHARMA",
    "TITAN",
    "ULTRACEMCO",
    "NESTLEIND",
    "WIPRO",
    "ADANIENT",
    "ADANIPORTS",
    "NTPC",
    "POWERGRID",
    "ONGC",
    "JSWSTEEL",
    "TATASTEEL",
    "INDUSINDBK",
    "TECHM",
    "TATAMOTORS",
    "BAJAJFINSV",
    "COALINDIA",
    "GRASIM",
    "CIPLA",
    "DRREDDY",
    "DIVISLAB",
    "EICHERMOT",
    "HEROMOTOCO",
    "M&M",
    "BRITANNIA",
    "APOLLOHOSP",
    "HINDALCO",
    "BPCL",
    "UPL",
    "TATACONSUM",
    "SBILIFE",
    
    # Select NIFTY Next 50 (high liquidity)
    "ADANIGREEN",
    "ADANIPOWER",
    "ATGL",  # Adani Total Gas
    "BANDHANBNK",
    "BERGEPAINT",
    "BOSCHLTD",
    "COLPAL",
    "DABUR",
    "DLF",
    "GAIL",
    "GODREJCP",
    "HDFCLIFE",
    "HAVELLS",
    "ICICIPRULI",
    "INDIGO",
    "JINDALSTEL",
    "MARICO",
    "MCDOWELL-N",
    "MOTHERSON",
    "NAUKRI",
    "NMDC",
    "PAGEIND",
    "PIDILITIND",
    "PNB",
    "RECLTD",
    "SHREECEM",
    "SIEMENS",
    "SRF",
    "TORNTPHARM",
    "TRENT",
    "VEDL",
    "ZOMATO",
]


def get_nse_swing_universe() -> list:
    """
    Get the NSE swing trading universe.
    
    Returns:
        List of NSE symbols suitable for swing trading
    """
    return NSE_SWING_UNIVERSE.copy()


def validate_universe() -> None:
    """
    Validate universe is not empty and has reasonable size.
    
    Raises:
        ValueError: If universe is empty or invalid
    """
    if not NSE_SWING_UNIVERSE:
        raise ValueError("NSE swing universe is empty")
    
    if len(NSE_SWING_UNIVERSE) < 30:
        raise ValueError(
            f"NSE swing universe too small: {len(NSE_SWING_UNIVERSE)} stocks. "
            "Expected at least 30 for diversification."
        )
    
    # Check for duplicates
    if len(NSE_SWING_UNIVERSE) != len(set(NSE_SWING_UNIVERSE)):
        duplicates = [
            sym for sym in NSE_SWING_UNIVERSE
            if NSE_SWING_UNIVERSE.count(sym) > 1
        ]
        raise ValueError(f"Duplicate symbols in universe: {duplicates}")


# Universe metadata
UNIVERSE_METADATA = {
    "name": "NSE Swing Trading Universe",
    "market": "india",
    "exchange": "NSE",
    "mode": "swing",
    "instrument_type": "equity",
    "count": len(NSE_SWING_UNIVERSE),
    "criteria": {
        "min_daily_volume": "50 lakh shares",
        "min_market_cap": "₹10,000 crore",
        "quality": "NIFTY 50 + select NIFTY Next 50",
    },
    "last_updated": "2026-01-28",
}


if __name__ == "__main__":
    """Validate universe on import."""
    validate_universe()
    print(f"NSE Swing Universe: {len(NSE_SWING_UNIVERSE)} stocks")
    print(f"Symbols: {', '.join(NSE_SWING_UNIVERSE[:10])}...")
