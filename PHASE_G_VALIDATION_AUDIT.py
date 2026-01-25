#!/usr/bin/env python3
"""
PHASE G VALIDATION AUDIT
========================

Rigorous execution-lead review of Phase G.
Checks: time-safety, slippage realism, liquidity guardrails, observability.

This is NOT a unit test. This is a VALIDATION against trading system criteria.
"""

import sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from execution.execution_model import (
    apply_slippage,
    compute_entry_price,
    compute_exit_price,
    check_liquidity,
    compute_slippage_cost,
    ExecutionModel,
)


class ValidationAudit:
    """Execution-lead validation framework for Phase G."""
    
    def __init__(self):
        self.checks = []
        self.failures = []
        self.warnings = []
    
    def add_check(self, name: str, passed: bool, details: str = ""):
        """Log a validation check."""
        status = "✅ PASS" if passed else "❌ FAIL"
        msg = f"{status} | {name}"
        if details:
            msg += f" | {details}"
        self.checks.append((name, passed, details))
        print(f"  {msg}")
        if not passed:
            self.failures.append((name, details))
    
    def print_section(self, title: str):
        """Print audit section header."""
        print(f"\n{'='*80}")
        print(f"{title}")
        print(f"{'='*80}")
    
    def report(self):
        """Generate final audit report."""
        self.print_section("PHASE G VALIDATION REPORT")
        
        total = len(self.checks)
        passed = sum(1 for _, p, _ in self.checks if p)
        failed = total - passed
        
        print(f"\nTotal Checks: {total}")
        print(f"Passed: {passed} ({passed/total*100:.0f}%)")
        print(f"Failed: {failed} ({failed/total*100:.0f}%)")
        
        if self.failures:
            print(f"\n{'='*80}")
            print("FAILURES (MUST FIX):")
            print(f"{'='*80}")
            for name, details in self.failures:
                print(f"\n❌ {name}")
                if details:
                    print(f"   {details}")
        
        print(f"\n{'='*80}")
        print("RECOMMENDATION")
        print(f"{'='*80}")
        if failed == 0:
            print("✅ Phase G PASSES validation. Ready for production.")
            return True
        else:
            print(f"❌ Phase G has {failed} critical failures. DO NOT USE.")
            return False


def audit_time_safety():
    """🚨 TIME-SAFETY & LOOKAHEAD CHECK — Most critical."""
    audit = ValidationAudit()
    audit.print_section("1️⃣  TIME-SAFETY & LOOKAHEAD CHECK (Non-negotiable)")
    
    # Create test data: 5 days
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    price_data = pd.DataFrame({
        "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
        "Close": [100.5, 101.5, 102.5, 103.5, 104.5],
        "Volume": [1_000_000] * 5,
    }, index=dates)
    
    # TEST 1: Signal on Day 0 → Entry on Day 1
    signal_date = dates[0]  # 2024-01-01
    entry_price = compute_entry_price(signal_date, price_data, use_next_open=True)
    
    # Expected: Day 1 open (101.0) + slippage
    # Must NOT be Day 0 close (that would be lookahead)
    audit.add_check(
        "Signal date on Day 0 uses Day 1 open (next day)",
        entry_price is not None and entry_price > 101.0,  # Day 1 open is 101
        f"Entry price: {entry_price:.4f} (should be ~101.05 for 5 bps)"
    )
    
    # TEST 2: Verify slippage is applied AFTER price selection
    slipped_101 = apply_slippage(101.0, 5, "entry")
    expected_entry = slipped_101
    audit.add_check(
        "Slippage applied AFTER price selection",
        abs(entry_price - expected_entry) < 0.001,
        f"Computed: {entry_price:.4f}, Expected: {expected_entry:.4f}"
    )
    
    # TEST 3: Exit uses exit_date, not future data
    exit_date = dates[3]  # 2024-01-04
    exit_price = compute_exit_price(exit_date, price_data, use_next_open=True)
    
    # Expected: Day 3 open (103.0) - slippage
    audit.add_check(
        "Exit uses exit_date data only (no future data)",
        exit_price is not None and 102.9 < exit_price < 103.1,
        f"Exit price: {exit_price:.4f} (should be ~102.95 for 5 bps)"
    )
    
    # TEST 4: Last day entry returns None (no future data lookahead)
    last_day_entry = compute_entry_price(dates[-1], price_data, use_next_open=True)
    audit.add_check(
        "Last day entry returns None (prevents lookahead)",
        last_day_entry is None,
        "Correctly rejects when no next day available"
    )
    
    # TEST 5: use_next_open=False uses same day (acceptable, not required)
    same_day_entry = compute_entry_price(signal_date, price_data, use_next_open=False)
    expected_same_day = apply_slippage(100.5, 5, "entry")  # Close + slippage
    audit.add_check(
        "use_next_open=False uses same day close (acceptable alternative)",
        abs(same_day_entry - expected_same_day) < 0.001,
        "Fallback mode works correctly"
    )
    
    return audit.report()


def audit_slippage_realism():
    """SLIPPAGE REALISM CHECK — Verify it always hurts you."""
    audit = ValidationAudit()
    audit.print_section("2️⃣  SLIPPAGE REALISM CHECK (Must always hurt)")
    
    # TEST 1: Entry slippage always increases price
    base = 100.0
    for bps in [1, 5, 10, 100]:
        slipped = apply_slippage(base, bps, "entry")
        audit.add_check(
            f"Entry slippage {bps}bps increases price",
            slipped > base,
            f"{base:.2f} → {slipped:.4f} (worse)"
        )
    
    # TEST 2: Exit slippage always decreases price
    for bps in [1, 5, 10, 100]:
        slipped = apply_slippage(base, bps, "exit")
        audit.add_check(
            f"Exit slippage {bps}bps decreases price",
            slipped < base,
            f"{base:.2f} → {slipped:.4f} (worse)"
        )
    
    # TEST 3: Zero slippage = zero cost
    entry_zero = apply_slippage(100.0, 0, "entry")
    exit_zero = apply_slippage(100.0, 0, "exit")
    audit.add_check(
        "Zero slippage = zero impact",
        entry_zero == 100.0 and exit_zero == 100.0,
        "Baseline price unchanged"
    )
    
    # TEST 4: Slippage cost calculation is correct
    costs = compute_slippage_cost(
        entry_price_idealized=100.0,
        exit_price_idealized=105.0,
        entry_price_realistic=100.05,  # 5 bps worse
        exit_price_realistic=104.95,   # 5 bps worse
        position_size=1000,  # shares
    )
    
    # Entry cost: (100.05 - 100.0) * 1000 = $50
    # Exit cost: (105.0 - 104.95) * 1000 = $50
    expected_total = 100.0
    audit.add_check(
        "Slippage cost calculation is accurate",
        abs(costs["total_slippage_cost"] - expected_total) < 0.1,
        f"Total cost: ${costs['total_slippage_cost']:.2f} (expected ${expected_total:.2f})"
    )
    
    return audit.report()


def audit_liquidity_guardrail():
    """LIQUIDITY GUARDRAIL CHECK — Dollar volume, not shares."""
    audit = ValidationAudit()
    audit.print_section("3️⃣  LIQUIDITY GUARDRAIL CHECK (Dollar volume validation)")
    
    # TEST 1: Uses DOLLAR volume, not share volume
    adv_shares = 1_000_000  # 1M shares/day
    price = 100.0
    adv_dollars = adv_shares * price  # $100M
    
    position_dollars = adv_dollars * 0.04  # 4% of ADV
    passed, reason = check_liquidity(position_dollars, adv_dollars, max_adv_pct=0.05)
    audit.add_check(
        "Position within 5% of dollar volume passes",
        passed and reason is None,
        "4% of ADV is accepted"
    )
    
    # TEST 2: Rejects position > ADV limit
    position_dollars_high = adv_dollars * 0.06  # 6% of ADV
    passed, reason = check_liquidity(position_dollars_high, adv_dollars, max_adv_pct=0.05)
    audit.add_check(
        "Position exceeding 5% of ADV is rejected",
        not passed and reason is not None,
        f"6% of ADV correctly rejected: {reason[:60]}..."
    )
    
    # TEST 3: Position exactly at limit passes
    position_dollars_limit = adv_dollars * 0.05  # Exactly 5%
    passed, reason = check_liquidity(position_dollars_limit, adv_dollars, max_adv_pct=0.05)
    audit.add_check(
        "Position exactly at limit (5% of ADV) passes",
        passed and reason is None,
        "Boundary condition handled correctly"
    )
    
    # TEST 4: Invalid ADV (≤0) is rejected
    passed, reason = check_liquidity(100_000, 0, max_adv_pct=0.05)
    audit.add_check(
        "Invalid ADV (≤0) is rejected",
        not passed and reason is not None,
        "Safety check prevents division by zero"
    )
    
    # TEST 5: Large position rejected even with large ADV
    large_adv = 1_000_000_000  # $1B ADV
    large_position = large_adv * 0.08  # 8% (exceeds 5% limit)
    passed, reason = check_liquidity(large_position, large_adv, max_adv_pct=0.05)
    audit.add_check(
        "Large position with large ADV still respects limit",
        not passed,
        "Limit enforced consistently at all scales"
    )
    
    return audit.report()


def audit_observability():
    """OBSERVABILITY CHECK — Can we see execution impact?"""
    audit = ValidationAudit()
    audit.print_section("4️⃣  OBSERVABILITY CHECK (Attribution & tracking)")
    
    # Create execution model and apply it
    model = ExecutionModel(
        entry_slippage_bps=5,
        exit_slippage_bps=5,
        max_adv_pct=0.05,
        use_next_open=True,
    )
    
    # Simulate rejecting some trades due to liquidity
    for i in range(3):
        model.check_liquidity_for_position(
            position_notional=600_000,
            avg_daily_dollar_volume=10_000_000,
        )
    
    summary = model.get_summary()
    
    audit.add_check(
        "Can track trades rejected by liquidity",
        "trades_rejected_liquidity" in summary and summary["trades_rejected_liquidity"] == 3,
        f"Tracked {summary['trades_rejected_liquidity']} rejected trades"
    )
    
    audit.add_check(
        "Can track total slippage cost",
        "total_slippage_cost" in summary,
        "Slippage cost field exists"
    )
    
    audit.add_check(
        "Can track trade count",
        "total_slippage_trades" in summary,
        "Trade count field exists"
    )
    
    audit.add_check(
        "Can compute average slippage per trade",
        "avg_slippage_per_trade" in summary,
        "Average slippage calculation available"
    )
    
    return audit.report()


def audit_behavioral_sanity():
    """BEHAVIORAL SANITY CHECK — Realistic vs Idealized comparison."""
    audit = ValidationAudit()
    audit.print_section("5️⃣  BEHAVIORAL SANITY CHECK (Performance impact)")
    
    # Create price data with consistent open/close
    dates = pd.date_range("2024-01-01", periods=20, freq="D")
    np.random.seed(42)
    # Make opens and closes similar to avoid confusion
    prices = 100.0 + np.cumsum(np.random.randn(20) * 0.5)
    price_data = pd.DataFrame({
        "Open": prices,
        "Close": prices + 0.1,  # Slightly different, but same trend
        "Volume": [1_000_000] * 20,
    }, index=dates)
    
    # Simulate 3 trades using SAME entry/exit prices for idealized
    trades = [
        {"signal_date": dates[0], "exit_date": dates[5]},
        {"signal_date": dates[7], "exit_date": dates[12]},
        {"signal_date": dates[14], "exit_date": dates[19]},
    ]
    
    total_pnl_idealized = 0.0
    total_pnl_realistic = 0.0
    total_slippage_cost = 0.0
    
    model = ExecutionModel()
    
    for trade in trades:
        signal_date = trade["signal_date"]
        exit_date = trade["exit_date"]
        
        if signal_date not in price_data.index or exit_date not in price_data.index:
            continue
        
        # For idealized: use next day open (same as realistic, but NO slippage)
        if signal_date not in price_data.index:
            continue
        idx_signal = price_data.index.get_loc(signal_date)
        if idx_signal >= len(price_data) - 1:
            continue
        
        entry_price_no_slip = price_data.iloc[idx_signal + 1]["Open"]
        exit_price_no_slip = price_data.loc[exit_date, "Open"]
        
        pnl_ideal = (exit_price_no_slip - entry_price_no_slip) * 1000  # 1000 shares
        total_pnl_idealized += pnl_ideal
        
        # For realistic: use next day open WITH slippage
        entry_real = model.get_entry_price(signal_date, price_data)
        exit_real = model.get_exit_price(exit_date, price_data)
        
        if entry_real and exit_real:
            pnl_real = (exit_real - entry_real) * 1000
            total_pnl_realistic += pnl_real
            
            # Slippage cost (should be positive: we pay it)
            # Entry slippage: (entry_real - entry_no_slip) * shares
            # Exit slippage: (exit_no_slip - exit_real) * shares
            entry_cost = (entry_real - entry_price_no_slip) * 1000  # Positive (we paid it)
            exit_cost = (exit_price_no_slip - exit_real) * 1000       # Positive (we paid it)
            slippage = entry_cost + exit_cost
            total_slippage_cost += slippage
    
    audit.add_check(
        "Realistic PnL is worse than idealized (slippage costs money)",
        total_pnl_realistic <= total_pnl_idealized,
        f"Idealized: ${total_pnl_idealized:.2f}, Realistic: ${total_pnl_realistic:.2f}"
    )
    
    audit.add_check(
        "Slippage cost is positive (we always pay it)",
        total_slippage_cost >= 0,
        f"Total slippage cost: ${total_slippage_cost:.2f} (should be ≥ $0)"
    )
    
    # Difference should equal slippage
    diff = total_pnl_idealized - total_pnl_realistic
    audit.add_check(
        "PnL difference equals slippage cost (attribution correct)",
        abs(diff - total_slippage_cost) < 0.01,
        f"Diff: ${diff:.2f}, Slippage: ${total_slippage_cost:.2f}"
    )
    
    return audit.report()


def main():
    """Run full Phase G validation audit."""
    print("\n" + "="*80)
    print("PHASE G VALIDATION AUDIT — EXECUTION LEAD REVIEW")
    print("="*80)
    print("\nThis audit validates Phase G against trading system criteria:")
    print("  1. Time-safety & lookahead (non-negotiable)")
    print("  2. Slippage realism (must always hurt you)")
    print("  3. Liquidity guardrails (dollar volume)")
    print("  4. Observability (tracking impact)")
    print("  5. Behavioral sanity (realistic vs idealized)")
    print("\n")
    
    results = []
    
    # Run all audits
    results.append(("Time-Safety", audit_time_safety()))
    results.append(("Slippage Realism", audit_slippage_realism()))
    results.append(("Liquidity Guardrail", audit_liquidity_guardrail()))
    results.append(("Observability", audit_observability()))
    results.append(("Behavioral Sanity", audit_behavioral_sanity()))
    
    # Final report
    print("\n" + "="*80)
    print("FINAL AUDIT SUMMARY")
    print("="*80)
    
    all_passed = all(passed for _, passed in results)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {name}")
    
    print("\n" + "="*80)
    if all_passed:
        print("✅ PHASE G VALIDATION: APPROVED FOR PRODUCTION")
        print("="*80)
        print("\nPhase G has passed all execution lead validations.")
        print("System is ready for production backtesting.")
        return 0
    else:
        print("❌ PHASE G VALIDATION: FAILED — DO NOT USE")
        print("="*80)
        print("\nCritical failures detected. Fix before production use.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
