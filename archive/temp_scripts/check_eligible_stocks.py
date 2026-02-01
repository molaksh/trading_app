import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("APCA_LIVE_API_KEY_ID")
api_secret = os.environ.get("APCA_LIVE_API_SECRET_KEY")

symbols = [
    'SPY', 'QQQ', 'IWM',
    'AAPL', 'MSFT', 'GOOGL', 'NVDA', 'TSLA',
    'JPM', 'BAC', 'WMT', 'JNJ', 'KO', 'PG', 'MA', 'V',
    'BRK.B', 'GS', 'C', 'AXP',
    'UNH', 'PFE', 'ABBV', 'MRK',
    'XOM', 'CVX', 'CAT', 'BA',
    'META', 'NFLX', 'CMCSA',
    'AMZN', 'MCD', 'SBUX', 'NKE',
    'AMD', 'INTC', 'QCOM', 'NXPI',
    'ADBE', 'CRM', 'ORCL', 'IBM',
]

headers = {
    'APCA-API-KEY-ID': api_key,
    'APCA-API-SECRET-KEY': api_secret
}

# Approximate prices (from general market knowledge as of early 2026)
# This is for illustration - in production use live market data
prices = {
    'SPY': 570,
    'QQQ': 480,
    'IWM': 220,
    'AAPL': 245,
    'MSFT': 420,
    'GOOGL': 185,
    'NVDA': 880,
    'TSLA': 310,
    'JPM': 220,
    'BAC': 38,
    'WMT': 95,
    'JNJ': 165,
    'KO': 52,
    'PG': 172,
    'MA': 525,
    'V': 320,
    'BRK.B': 420,
    'GS': 95,
    'C': 68,
    'AXP': 275,
    'UNH': 525,
    'PFE': 28,
    'ABBV': 285,
    'MRK': 105,
    'XOM': 120,
    'CVX': 165,
    'CAT': 315,
    'BA': 210,
    'META': 580,
    'NFLX': 285,
    'CMCSA': 42,
    'AMZN': 220,
    'MCD': 305,
    'SBUX': 105,
    'NKE': 85,
    'AMD': 210,
    'INTC': 35,
    'QCOM': 195,
    'NXPI': 275,
    'ADBE': 610,
    'CRM': 320,
    'ORCL': 155,
    'IBM': 215,
}

eligible = {k: v for k, v in prices.items() if v <= 100}
ineligible = {k: v for k, v in prices.items() if v > 100}

print(f"Total symbols: {len(symbols)}")
print(f"Eligible (price <= 100): {len(eligible)}")
print("=" * 50)
for sym in sorted(eligible, key=lambda x: eligible[x]):
    print(f"{sym:8s} ${eligible[sym]:8.2f}")

print(f"\nINELIGIBLE (price > 100): {len(ineligible)}")
print("=" * 50)
for sym in sorted(ineligible, key=lambda x: ineligible[x]):
    print(f"{sym:8s} ${ineligible[sym]:8.2f}")
