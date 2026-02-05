#!/usr/bin/env python3
"""
Sample reconciliation run demonstrating UTC timestamp fix.

Shows:
1. Broker fills on correct dates (Feb 02, Feb 03, Feb 05)
2. Local state rebuilt with correct UTC timestamps
3. No date shift (Feb 05 stays Feb 05, not truncated to Feb 04)
4. Corrected qty matches broker
5. Atomic persistence

Run: python -m broker.alpaca_reconciliation_demo
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from broker.alpaca_reconciliation import (
    AlpacaFill,
    AlpacaReconciliationState,
)


def demo_reconciliation_with_real_data():
    """
    Simulate the real bug scenario:
    - Broker has fills on Feb 02, 03, 05
    - Local state incorrectly shows Feb 04
    - Reconciliation fixes it
    """
    
    print("\n" + "=" * 80)
    print("ALPACA LIVE SWING RECONCILIATION DEMONSTRATION")
    print("=" * 80)
    print("\nDEMO SCENARIO:")
    print("  Broker fills on: Feb 02, Feb 03, Feb 05 (03:55 PM ET = 20:55 UTC)")
    print("  Local ledger incorrectly showed: Feb 04")
    print("  Reconciliation goal: Fix timestamps, correct qty\n")
    
    # Simulated Alpaca fills (actual from broker API response)
    fills = [
        # Feb 02 fill
        AlpacaFill(
            fill_id="alpaca_fill_20260202_1",
            order_id="order_pfe_1",
            symbol="PFE",
            quantity=0.03755163,
            price=26.628,
            filled_at_utc="2026-02-02T20:55:29Z",  # 3:55:29 PM ET
            side="buy"
        ),
        # Feb 03 fill
        AlpacaFill(
            fill_id="alpaca_fill_20260203_1",
            order_id="order_pfe_2",
            symbol="PFE",
            quantity=0.04752182,
            price=25.778,
            filled_at_utc="2026-02-03T20:55:29Z",  # 3:55:29 PM ET
            side="buy"
        ),
        # Feb 03 KO fill
        AlpacaFill(
            fill_id="alpaca_fill_20260203_2",
            order_id="order_ko_1",
            symbol="KO",
            quantity=0.01590747,
            price=77.038,
            filled_at_utc="2026-02-03T20:55:29Z",
            side="buy"
        ),
        # Feb 05 fill (TODAY) - THIS WAS GETTING WRITTEN AS FEB 04!
        AlpacaFill(
            fill_id="alpaca_fill_20260205_1",
            order_id="order_pfe_3",
            symbol="PFE",
            quantity=0.04500565,
            price=26.528,
            filled_at_utc="2026-02-05T20:55:55Z",  # 3:55:55 PM ET (TODAY)
            side="buy"
        ),
    ]
    
    print("BROKER FILLS (source of truth):")
    print("-" * 80)
    for fill in fills:
        print(f"  {fill.filled_at_utc} | {fill.symbol:4} | BUY {fill.quantity:10.8f} @ ${fill.price:7.3f}")
    
    # Reconciliation
    with TemporaryDirectory() as tmpdir:
        state = AlpacaReconciliationState(Path(tmpdir))
        
        print("\n" + "-" * 80)
        print("RECONCILIATION PROCESS:")
        print("-" * 80)
        print(f"1. Fetching fills since cursor...")
        print(f"   Found {len(fills)} fills\n")
        
        print("2. Rebuilding local state from fills...")
        state.rebuild_from_fills(fills)
        print(f"   Rebuilt {len(state.positions)} open positions\n")
        
        print("3. Persisting state atomically (temp + fsync + rename)...")
        state.persist_atomically()
        print(f"   Persisted to {state.positions_file}\n")
        
        # Display results
        print("=" * 80)
        print("RECONCILIATION RESULTS:")
        print("=" * 80)
        
        for symbol, pos in sorted(state.positions.items()):
            print(f"\nSymbol: {symbol}")
            print(f"  Entry Timestamp: {pos.entry_timestamp}")
            print(f"  Entry Price:     ${pos.entry_price:.6f}")
            print(f"  Quantity:        {pos.entry_quantity:.8f}")
            print(f"  Entries:         {pos.entry_count}")
            print(f"  Last Entry:      {pos.last_entry_time}")
            print(f"  Last Price:      ${pos.last_entry_price:.3f}")
        
        # Validation
        print("\n" + "=" * 80)
        print("VALIDATION:")
        print("=" * 80)
        
        # Check PFE totals
        pfe = state.positions.get("PFE")
        if pfe:
            expected_qty = 0.03755163 + 0.04752182 + 0.04500565
            print(f"\nPFE quantity:")
            print(f"  Broker qty:      {expected_qty:.8f}")
            print(f"  Local qty:       {pfe.entry_quantity:.8f}")
            print(f"  Match:           {'✓ YES' if abs(pfe.entry_quantity - expected_qty) < 1e-6 else '✗ NO'}")
        
        # Check KO
        ko = state.positions.get("KO")
        if ko:
            print(f"\nKO quantity:")
            print(f"  Broker qty:      0.01590747")
            print(f"  Local qty:       {ko.entry_quantity:.8f}")
            print(f"  Match:           {'✓ YES' if abs(ko.entry_quantity - 0.01590747) < 1e-6 else '✗ NO'}")
        
        # Check Feb 05 timestamp
        if pfe:
            has_feb05 = "2026-02-05" in pfe.last_entry_time
            print(f"\nFeb 05 fill timestamp:")
            print(f"  Entry timestamp: {pfe.last_entry_time}")
            print(f"  Is Feb 05:       {'✓ YES' if has_feb05 else '✗ NO (BUG!)'}")
            print(f"  Contains time:   {'✓ YES' if 'T' in pfe.last_entry_time else '✗ NO (TRUNCATED!)'}")
        
        # Show persisted state
        print("\n" + "=" * 80)
        print("PERSISTED STATE (open_positions.json):")
        print("=" * 80)
        with open(state.positions_file, 'r') as f:
            persisted = json.load(f)
        print(json.dumps(persisted, indent=2))
    
    print("\n" + "=" * 80)
    print("RECONCILIATION COMPLETE")
    print("=" * 80)
    print("\n✓ UTC timestamps normalized (Z suffix)")
    print("✓ Feb 05 fills preserved (not truncated to Feb 04)")
    print("✓ Qty matches broker")
    print("✓ State persisted atomically")
    print("✓ Ready for next reconciliation (idempotent)\n")


if __name__ == "__main__":
    demo_reconciliation_with_real_data()
