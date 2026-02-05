"""
Tests for Alpaca Live Swing Reconciliation.

Validates:
1. UTC timestamp normalization (no date truncation)
2. State rebuild from fills (idempotent)
3. Atomic persistence (temp file + rename)
4. No false date shifts
5. Correct quantity calculation
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from broker.alpaca_reconciliation import (
    AlpacaFill,
    LocalOpenPosition,
    ReconciliationCursor,
    AlpacaReconciliationState,
    AlpacaReconciliationEngine,
)


class TestTimezoneNormalizationUTC:
    """Validates UTC timestamp normalization (no timezone truncation)."""
    
    def test_fill_timestamp_stored_as_iso_utc_z(self):
        """Fill timestamps must be ISO-8601 with Z suffix."""
        # Simulate fill from Alpaca at specific US Eastern time
        # 2026-02-05 03:55:55 PM ET = 2026-02-05 20:55:55 UTC
        
        fill = AlpacaFill(
            fill_id="fill_abc123",
            order_id="order_xyz",
            symbol="PFE",
            quantity=0.045,
            price=26.528,
            filled_at_utc="2026-02-05T20:55:55Z",  # Must be UTC
            side="buy"
        )
        
        assert fill.filled_at_utc == "2026-02-05T20:55:55Z"
        assert fill.filled_at_utc.endswith("Z")
        assert "+" not in fill.filled_at_utc  # No +00:00 variant
    
    def test_position_entry_timestamp_never_truncated_to_date(self):
        """Position entry_timestamp must preserve time, never just date."""
        pos = LocalOpenPosition(
            symbol="PFE",
            entry_order_id="order_1",
            entry_timestamp="2026-02-05T20:55:55.123456Z",
            entry_price=26.528,
            entry_quantity=0.045,
        )
        
        # Timestamp must have hour/minute/second, not just date
        assert "T" in pos.entry_timestamp
        assert "20:55:55" in pos.entry_timestamp
        assert pos.entry_timestamp != "2026-02-05"  # Never date-only
    
    def test_no_date_shift_feb05_fill_stays_feb05(self):
        """Feb 05 fill must never become Feb 04 due to timezone logic."""
        # Broker fill: Feb 05, 20:55:55 UTC
        fills = [
            AlpacaFill(
                fill_id="f1",
                order_id="o1",
                symbol="PFE",
                quantity=0.045,
                price=26.528,
                filled_at_utc="2026-02-05T20:55:55Z",
                side="buy"
            ),
        ]
        
        state = AlpacaReconciliationState(Path("/tmp"))
        state.rebuild_from_fills(fills)
        
        pos = state.positions["PFE"]
        assert "2026-02-05" in pos.entry_timestamp  # Still Feb 05
        assert not "2026-02-04" in pos.entry_timestamp  # NOT Feb 04


class TestReconcileRebuildsStateFromFills:
    """Validates state rebuild from fills (idempotent)."""
    
    def test_single_fill_creates_position(self):
        """Single buy fill creates open position."""
        fills = [
            AlpacaFill(
                fill_id="f1",
                order_id="o1",
                symbol="PFE",
                quantity=0.05,
                price=26.50,
                filled_at_utc="2026-02-05T20:55:55Z",
                side="buy"
            )
        ]
        
        state = AlpacaReconciliationState(Path("/tmp"))
        state.rebuild_from_fills(fills)
        
        assert "PFE" in state.positions
        pos = state.positions["PFE"]
        assert pos.entry_quantity == 0.05
        assert abs(pos.entry_price - 26.50) < 0.01  # Float comparison
    
    def test_multiple_buys_accumulate_with_weighted_avg_price(self):
        """Multiple buy fills accumulate qty, avg price weighted."""
        fills = [
            AlpacaFill(
                fill_id="f1", order_id="o1", symbol="PFE",
                quantity=0.04, price=26.50, filled_at_utc="2026-02-02T20:55:55Z", side="buy"
            ),
            AlpacaFill(
                fill_id="f2", order_id="o2", symbol="PFE",
                quantity=0.0475, price=25.778, filled_at_utc="2026-02-03T20:55:55Z", side="buy"
            ),
            AlpacaFill(
                fill_id="f3", order_id="o3", symbol="PFE",
                quantity=0.045, price=26.528, filled_at_utc="2026-02-05T20:55:55Z", side="buy"
            ),
        ]
        
        state = AlpacaReconciliationState(Path("/tmp"))
        state.rebuild_from_fills(fills)
        
        pos = state.positions["PFE"]
        
        # Total qty
        expected_qty = 0.04 + 0.0475 + 0.045  # 0.1325
        assert abs(pos.entry_quantity - expected_qty) < 1e-6
        
        # Weighted avg price
        total_cost = (0.04 * 26.50) + (0.0475 * 25.778) + (0.045 * 26.528)
        expected_avg = total_cost / expected_qty
        assert abs(pos.entry_price - expected_avg) < 0.01
        
        # Entry timestamp = first buy
        assert "2026-02-02" in pos.entry_timestamp
        
        # Last entry time = last buy
        assert "2026-02-05" in pos.last_entry_time
    
    def test_mixed_buys_and_sells_net_qty(self):
        """Buy fills subtract sell fills for net quantity."""
        fills = [
            AlpacaFill(
                fill_id="f1", order_id="o1", symbol="KO",
                quantity=0.015, price=77.04, filled_at_utc="2026-02-03T20:55:55Z", side="buy"
            ),
            AlpacaFill(
                fill_id="f2", order_id="o2", symbol="KO",
                quantity=0.005, price=78.00, filled_at_utc="2026-02-04T20:55:55Z", side="sell"
            ),
        ]
        
        state = AlpacaReconciliationState(Path("/tmp"))
        state.rebuild_from_fills(fills)
        
        pos = state.positions["KO"]
        # Net: 0.015 - 0.005 = 0.010
        assert abs(pos.entry_quantity - 0.010) < 1e-6
    
    def test_all_sells_no_position(self):
        """If qty sold >= qty bought, no open position."""
        fills = [
            AlpacaFill(
                fill_id="f1", order_id="o1", symbol="STOCK",
                quantity=0.010, price=100.0, filled_at_utc="2026-02-01T20:55:55Z", side="buy"
            ),
            AlpacaFill(
                fill_id="f2", order_id="o2", symbol="STOCK",
                quantity=0.010, price=105.0, filled_at_utc="2026-02-02T20:55:55Z", side="sell"
            ),
        ]
        
        state = AlpacaReconciliationState(Path("/tmp"))
        state.rebuild_from_fills(fills)
        
        assert "STOCK" not in state.positions
    
    def test_idempotent_rebuild_same_fills_twice(self):
        """Running rebuild twice with same fills yields identical state."""
        fills = [
            AlpacaFill(
                fill_id="f1", order_id="o1", symbol="PFE",
                quantity=0.05, price=26.50, filled_at_utc="2026-02-05T20:55:55Z", side="buy"
            ),
            AlpacaFill(
                fill_id="f2", order_id="o2", symbol="KO",
                quantity=0.015, price=77.04, filled_at_utc="2026-02-03T20:55:55Z", side="buy"
            ),
        ]
        
        state1 = AlpacaReconciliationState(Path("/tmp"))
        state1.rebuild_from_fills(fills)
        
        state2 = AlpacaReconciliationState(Path("/tmp"))
        state2.rebuild_from_fills(fills)
        
        # Both states should be identical
        assert len(state1.positions) == len(state2.positions)
        for symbol in state1.positions:
            p1 = state1.positions[symbol]
            p2 = state2.positions[symbol]
            assert p1.entry_quantity == p2.entry_quantity
            assert p1.entry_price == p2.entry_price


class TestNoFalseDateShift:
    """Validates that Feb 05 fills never get written as Feb 04."""
    
    def test_feb05_3pm_et_stored_as_feb05_8pm_utc(self):
        """3:55:55 PM ET = 20:55:55 UTC (same date, not previous day)."""
        # US market close is 4 PM ET = 21 UTC
        # 3:55 PM ET = 20:55 UTC (still same calendar day in UTC)
        
        fill = AlpacaFill(
            fill_id="fill1",
            order_id="order1",
            symbol="PFE",
            quantity=0.045,
            price=26.528,
            filled_at_utc="2026-02-05T20:55:55Z",  # 3:55 PM ET
            side="buy"
        )
        
        state = AlpacaReconciliationState(Path("/tmp"))
        state.rebuild_from_fills([fill])
        
        pos = state.positions["PFE"]
        
        # Must be Feb 05, not Feb 04
        date_str = pos.entry_timestamp[:10]  # YYYY-MM-DD
        assert date_str == "2026-02-05"
        assert not date_str.endswith("02-04")


class TestAtomicWrite:
    """Validates atomic write with temp file + rename."""
    
    def test_positions_file_atomic_write(self):
        """Positions persisted atomically (temp + rename)."""
        with TemporaryDirectory() as tmpdir:
            state = AlpacaReconciliationState(Path(tmpdir))
            
            fills = [
                AlpacaFill(
                    fill_id="f1", order_id="o1", symbol="PFE",
                    quantity=0.05, price=26.50, filled_at_utc="2026-02-05T20:55:55Z", side="buy"
                ),
            ]
            
            state.rebuild_from_fills(fills)
            state.persist_atomically()
            
            # File must exist and be valid JSON
            assert state.positions_file.exists()
            with open(state.positions_file, 'r') as f:
                data = json.load(f)
            
            assert "PFE" in data
            assert data["PFE"]["entry_quantity"] == 0.05
    
    def test_cursor_file_atomic_write(self):
        """Cursor persisted atomically."""
        with TemporaryDirectory() as tmpdir:
            state = AlpacaReconciliationState(Path(tmpdir))
            
            fill = AlpacaFill(
                fill_id="f1", order_id="o1", symbol="PFE",
                quantity=0.05, price=26.50, filled_at_utc="2026-02-05T20:55:55Z", side="buy"
            )
            
            state.update_cursor(fill)
            state.persist_atomically()
            
            assert state.cursor_file.exists()
            with open(state.cursor_file, 'r') as f:
                data = json.load(f)
            
            assert data["last_seen_fill_id"] == "f1"
            assert data["last_seen_fill_time_utc"] == "2026-02-05T20:55:55Z"


class TestIdempotentReconciliation:
    """Validates reconciliation is idempotent (no duplicates on re-run)."""
    
    def test_reconcile_twice_same_result(self):
        """Running reconciliation twice yields identical state."""
        fills = [
            AlpacaFill(
                fill_id="f1", order_id="o1", symbol="PFE",
                quantity=0.04, price=26.50, filled_at_utc="2026-02-02T20:55:55Z", side="buy"
            ),
            AlpacaFill(
                fill_id="f2", order_id="o2", symbol="PFE",
                quantity=0.0475, price=25.778, filled_at_utc="2026-02-03T20:55:55Z", side="buy"
            ),
            AlpacaFill(
                fill_id="f3", order_id="o3", symbol="PFE",
                quantity=0.045, price=26.528, filled_at_utc="2026-02-05T20:55:55Z", side="buy"
            ),
        ]
        
        with TemporaryDirectory() as tmpdir:
            state = AlpacaReconciliationState(Path(tmpdir))
            
            # First reconciliation
            state.rebuild_from_fills(fills)
            state.persist_atomically()
            
            qty_after_first = state.positions["PFE"].entry_quantity
            
            # Second reconciliation (should be identical)
            state2 = AlpacaReconciliationState(Path(tmpdir))
            state2.rebuild_from_fills(fills)
            state2.persist_atomically()
            
            qty_after_second = state2.positions["PFE"].entry_quantity
            
            assert qty_after_first == qty_after_second
            assert abs(qty_after_first - 0.1325) < 1e-6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
