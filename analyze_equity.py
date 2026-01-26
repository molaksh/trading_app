import json
from collections import defaultdict

# Read the trades file
trades_file = "logs/trades_2026-01-26.jsonl"
filled_orders = {}

with open(trades_file, 'r') as f:
    for line in f:
        event = json.loads(line.strip())
        
        if event.get("event") == "order_filled":
            symbol = event["symbol"]
            quantity = event["quantity"]
            fill_price = event["fill_price"]
            fill_cost = quantity * fill_price
            
            if symbol not in filled_orders:
                filled_orders[symbol] = []
            
            filled_orders[symbol].append({
                "quantity": quantity,
                "price": fill_price,
                "cost": fill_cost
            })

# Calculate current positions (all BUY, no sells)
positions = {}
total_invested = 0

for symbol, fills in filled_orders.items():
    total_qty = 0
    total_cost = 0
    for fill in fills:
        total_qty += fill["quantity"]
        total_cost += fill["cost"]
    
    if total_qty > 0:
        avg_price = total_cost / total_qty
        positions[symbol] = {
            "quantity": total_qty,
            "entry_price": avg_price,
            "entry_cost": total_cost
        }
        total_invested += total_cost

print("=" * 80)
print("TRADING EQUITY ANALYSIS - 2026-01-26")
print("=" * 80)
print(f"\n{'Symbol':<10} {'Qty':>10} {'Avg Price':>12} {'Entry Cost':>15}")
print("-" * 80)

for symbol in sorted(positions.keys()):
    pos = positions[symbol]
    print(f"{symbol:<10} {pos['quantity']:>10.2f} ${pos['entry_price']:>11.2f} ${pos['entry_cost']:>14.2f}")

print("-" * 80)
print(f"{'TOTAL INVESTED':.<50} ${total_invested:>14.2f}")
print("=" * 80)

# Count the trades
buy_count = len(filled_orders)
total_shares = sum(pos["quantity"] for pos in positions.values())

print(f"\nTrade Summary:")
print(f"  Symbols Traded: {buy_count}")
print(f"  Total Shares: {total_shares:.2f}")
print(f"  Total Capital Deployed: ${total_invested:,.2f}")
print(f"  Average Position Size: ${total_invested / buy_count:,.2f}")
print("\n" + "=" * 80)
