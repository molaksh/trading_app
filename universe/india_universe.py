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
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HDFC.NS", "ITC.NS", "KOTAK.NS", "WIPRO.NS", "AXISBANK.NS",
    "MARUTI.NS", "SUNPHARMA.NS", "BAJAJFINSV.NS", "BAJAJ-AUTO.NS", "LT.NS",
    "ASIANPAINT.NS", "BHARTIARTL.NS", "NESTLEIND.NS", "SBILIFE.NS", "POWERGRID.NS",
    "JSWSTEEL.NS", "TATASTEEL.NS", "ULTRACEMCO.NS", "TORNTPHARM.NS", "ADANIPORTS.NS",
    "DMART.NS", "SBIN.NS", "HCLTECH.NS", "NTPC.NS", "ADANIENT.NS",
    "ONGC.NS", "GRASIM.NS", "BAJAJHLDNG.NS", "TITAN.NS", "HEROMOTOCORP.NS",
    "TECHM.NS", "DRREDDY.NS", "LUPIN.NS", "DIVISLAB.NS", "MAHLOG.NS",
    "SHREECEM.NS", "APOLLOHOSP.NS", "CIPLA.NS", "AAPL.NS", "INDIGO.NS",
    "M&M.NS", "EICHERMOT.NS", "TATACOMM.NS", "IOC.NS", "BANKBARODA.NS",
]

# ============================================================================
# NIFTY NEXT 50: Stocks 51-100 (optional for expansion)
# ============================================================================
NIFTY_NEXT_50 = [
    "HINDUNILVR.NS", "SIEMENSIND.NS", "BIOCON.NS", "COLPAL.NS", "BOSCHLTD.NS",
    "PAGEIND.NS", "CHOLAFIN.NS", "SBICARD.NS", "MMTLT.NS", "MOTILALOFS.NS",
    "GODREJPROP.NS", "ESCORTS.NS", "HAVELLS.NS", "NTPC.NS", "SRTRANSFIN.NS",
    "MUTHOOTFIN.NS", "JINDALSTEL.NS", "CANBK.NS", "ICRA.NS", "KPITTECH.NS",
    "LINDEINDIA.NS", "IRFC.NS", "FDC.NS", "INDHOTEL.NS", "ASHOKLEYLAND.NS",
    "CONCOR.NS", "POLYCAB.NS", "MAXHEALTH.NS", "JSWENERGY.NS", "BANKBARODA.NS",
    "SETULOGIN.NS", "SUVENSUA.NS", "VIP.NS", "TIMKEN.NS", "UNIPARTS.NS",
    "PHRX.NS", "SOBHA.NS", "AUROPHARMA.NS", "GILLETTE.NS", "CUMMINSIND.NS",
    "CREDITACC.NS", "IRCTC.NS", "CARGOTEC.NS", "ECLERX.NS", "ALBK.NS",
    "RAMCOCEM.NS", "NOCIL.NS", "OLECTRA.NS", "ATISECTO.NS", "GLAND.NS",
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
