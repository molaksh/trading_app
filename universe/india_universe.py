"""
NSE (India) stock universe definition.

Defines liquid, tradeable NSE stocks without circuit limits.
Market: National Stock Exchange of India
Hours: 09:15-15:30 IST (Monday-Friday)
"""

# ============================================================================
# NIFTY 50: Top 50 Indian large-cap stocks by market cap
# ============================================================================
NIFTY_50 = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HDFC", "ITC", "KOTAK", "WIPRO", "AXISBANK",
    "MARUTI", "SUNPHARMA", "BAJAJFINSV", "BAJAJ-AUTO", "LT",
    "ASIANPAINT", "BHARTIARTL", "NESTLEIND", "SBILIFE", "POWERGRID",
    "JSWSTEEL", "TATASTEEL", "ULTRACEMCO", "TORNTPHARM", "ADANIPORTS",
    "DMART", "SBIN", "HCLTECH", "NTPC", "ADANIENT",
    "ONGC", "GRASIM", "BAJAJHLDNG", "TITAN", "HEROMOTOCORP",
    "TECHM", "DRREDDY", "LUPIN", "DIVISLAB", "MAHLOG",
    "SHREECEM", "APOLLOHOSP", "CIPLA", "AAPL", "INDIGO",
    "M&M", "EICHERMOT", "TATACOMM", "IOC", "BANKBARODA",
]

# ============================================================================
# NIFTY NEXT 50: Stocks 51-100 (optional for expansion)
# ============================================================================
NIFTY_NEXT_50 = [
    "HINDUNILVR", "SIEMENSIND", "BIOCON", "COLPAL", "BOSCHLTD",
    "PAGEIND", "CHOLAFIN", "SBICARD", "MMTLT", "MOTILALOFS",
    "GODREJPROP", "ESCORTS", "HAVELLS", "NTPC", "SRTRANSFIN",
    "MUTHOOTFIN", "JINDALSTEL", "CANBK", "ICRA", "KPITTECH",
    "LINDEINDIA", "IRFC", "FDC", "INDHOTEL", "ASHOKLEYLAND",
    "CONCOR", "POLYCAB", "MAXHEALTH", "JSWENERGY", "BANKBARODA",
    "SETULOGIN", "SUVENSUA", "VIP", "TIMKEN", "UNIPARTS",
    "PHRX", "SOBHA", "AUROPHARMA", "GILLETTE", "CUMMINSIND",
    "CREDITACC", "IRCTC", "CARGOTEC", "ECLERX", "ALBK",
    "RAMCOCEM", "NOCIL", "OLECTRA", "ATISECTO", "GLAND",
]

# ============================================================================
# FULL UNIVERSE CONFIGURATION
# ============================================================================
# Default: NIFTY 50 (most liquid, most stable)
DEFAULT_UNIVERSE = NIFTY_50

# Extended: NIFTY 50 + NEXT 50 (for research, optional)
EXTENDED_UNIVERSE = NIFTY_50 + NIFTY_NEXT_50

# ============================================================================
# UNIVERSE SELECTION (configurable)
# ============================================================================
USE_EXTENDED_UNIVERSE = False    # Set to True to include NIFTY NEXT 50

SYMBOLS = EXTENDED_UNIVERSE if USE_EXTENDED_UNIVERSE else DEFAULT_UNIVERSE

# ============================================================================
# EXCLUDED STOCKS (manual overrides)
# ============================================================================
# Add symbols here if they're illiquid, delisted, or have circuit limits
EXCLUDED = []

# Apply exclusions
SYMBOLS = [s for s in SYMBOLS if s not in EXCLUDED]

# ============================================================================
# UNIVERSE METADATA
# ============================================================================
UNIVERSE_NAME = "NSE-NIFTY50" if not USE_EXTENDED_UNIVERSE else "NSE-NIFTY100"
UNIVERSE_SIZE = len(SYMBOLS)
MARKET = "NSE"
COUNTRY = "INDIA"
CURRENCY = "INR"

# ============================================================================
# TRADING HOURS (IST - Indian Standard Time)
# ============================================================================
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
MARKET_TIMEZONE = "IST"

# ============================================================================
# HOLIDAYS (sample - add comprehensive list as needed)
# ============================================================================
NSE_HOLIDAYS_2026 = [
    "2026-01-26",  # Republic Day
    "2026-03-25",  # Holi
    "2026-04-02",  # Good Friday
    "2026-04-14",  # Ambedkar Jayanti
    "2026-05-01",  # May Day
    "2026-08-15",  # Independence Day
    "2026-08-31",  # Janmashtami
    "2026-10-02",  # Gandhi Jayanti
    "2026-10-25",  # Diwali (Lakshmi Puja)
    "2026-10-26",  # Diwali (Balipratipada)
    "2026-11-01",  # Diwali (Govardhan Puja)
    "2026-12-25",  # Christmas
]

# ============================================================================
# LIQUIDITY REQUIREMENTS
# ============================================================================
# Stocks must meet these criteria to be included
MIN_ADV = 100_000_000           # Min avg daily volume (100M rupees)
MIN_PRICE = 50                   # Min stock price (INR)
MAX_SPREAD_BPS = 50              # Max bid-ask spread (50 bps)

# ============================================================================
# AUDIT AND LOGGING
# ============================================================================
print(f"[INDIA] Universe loaded: {UNIVERSE_NAME}")
print(f"[INDIA] Total stocks: {UNIVERSE_SIZE}")
print(f"[INDIA] Trading hours: {MARKET_OPEN}-{MARKET_CLOSE} {MARKET_TIMEZONE}")
