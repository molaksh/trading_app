#!/usr/bin/env python3
"""
Trade Ledger Demo

Demonstrates the complete trade ledger functionality:
1. Creating trades from fills
2. Adding to ledger
3. Querying trades
4. Exporting to CSV/JSON
5. Summary statistics
"""

from broker.trade_ledger import TradeLedger, create_trade_from_fills, Trade
from datetime import datetime, timedelta
from pathlib import Path


def demo_basic_usage():
    """Demo basic ledger operations."""
    print("\n" + "=" * 80)
    print("DEMO: Basic Trade Ledger Usage")
    print("=" * 80)
    
    # Create ledger (use temp file)
    ledger = TradeLedger(ledger_file=Path("logs/demo_trade_ledger.json"))
    
    # Create some sample trades
    print("\n1. Creating sample trades...")
    
    # Trade 1: Profitable swing exit
    trade1 = create_trade_from_fills(
        symbol="AAPL",
        entry_order_id="entry_001",
        entry_fill_timestamp="2026-01-10T09:30:00",
        entry_fill_price=180.00,
        entry_fill_quantity=50,
        exit_order_id="exit_001",
        exit_fill_timestamp="2026-01-15T16:00:00",
        exit_fill_price=189.00,
        exit_fill_quantity=50,
        exit_type="SWING_EXIT",
        exit_reason="Profit target reached (10%)",
        confidence=4.5,
        risk_amount=90.00,
        fees=0.0,
    )
    ledger.add_trade(trade1)
    
    # Trade 2: Small loss swing exit
    trade2 = create_trade_from_fills(
        symbol="GOOGL",
        entry_order_id="entry_002",
        entry_fill_timestamp="2026-01-12T10:00:00",
        entry_fill_price=150.00,
        entry_fill_quantity=30,
        exit_order_id="exit_002",
        exit_fill_timestamp="2026-01-20T15:30:00",
        exit_fill_price=147.00,
        exit_fill_quantity=30,
        exit_type="SWING_EXIT",
        exit_reason="Max holding period (20 days)",
        confidence=3.0,
        risk_amount=45.00,
        fees=0.0,
    )
    ledger.add_trade(trade2)
    
    # Trade 3: Emergency exit (loss)
    trade3 = create_trade_from_fills(
        symbol="NVDA",
        entry_order_id="entry_003",
        entry_fill_timestamp="2026-01-18T14:00:00",
        entry_fill_price=800.00,
        entry_fill_quantity=10,
        exit_order_id="exit_003",
        exit_fill_timestamp="2026-01-19T11:30:00",
        exit_fill_price=776.00,
        exit_fill_quantity=10,
        exit_type="EMERGENCY_EXIT",
        exit_reason="Position loss exceeds 3% of portfolio",
        confidence=4.0,
        risk_amount=80.00,
        fees=0.0,
    )
    ledger.add_trade(trade3)
    
    # Trade 4: Another profitable swing exit
    trade4 = create_trade_from_fills(
        symbol="MSFT",
        entry_order_id="entry_004",
        entry_fill_timestamp="2026-01-16T09:45:00",
        entry_fill_price=420.00,
        entry_fill_quantity=20,
        exit_order_id="exit_004",
        exit_fill_timestamp="2026-01-22T16:00:00",
        exit_fill_price=431.00,
        exit_fill_quantity=20,
        exit_type="SWING_EXIT",
        exit_reason="Profit target reached (10%)",
        confidence=5.0,
        risk_amount=84.00,
        fees=0.0,
    )
    ledger.add_trade(trade4)
    
    print(f"✓ Added {len(ledger.trades)} trades to ledger\n")
    
    return ledger


def demo_queries(ledger: TradeLedger):
    """Demo various query operations."""
    print("=" * 80)
    print("DEMO: Querying Trades")
    print("=" * 80 + "\n")
    
    # Query all trades
    print("2. All trades:")
    all_trades = ledger.get_trades()
    for trade in all_trades:
        print(f"  {trade.symbol}: {trade.net_pnl_pct:+.2f}% ({trade.exit_type})")
    
    # Query by symbol
    print("\n3. Trades for AAPL:")
    aapl_trades = ledger.get_trades(symbol="AAPL")
    for trade in aapl_trades:
        print(f"  Entry: ${trade.entry_price:.2f} → Exit: ${trade.exit_price:.2f} | PnL: {trade.net_pnl_pct:+.2f}%")
    
    # Query emergency exits
    print("\n4. Emergency exits only:")
    emergency_trades = ledger.get_trades(exit_type="EMERGENCY_EXIT")
    for trade in emergency_trades:
        print(f"  {trade.symbol}: {trade.exit_reason} | Loss: {trade.net_pnl_pct:.2f}%")
    
    # Query profitable trades
    print("\n5. Profitable trades (>0%):")
    winners = ledger.get_trades(min_pnl_pct=0.0)
    for trade in winners:
        print(f"  {trade.symbol}: {trade.net_pnl_pct:+.2f}% | Held {trade.holding_days} days")
    
    # Query by date range
    print("\n6. Trades exited after 2026-01-18:")
    recent_trades = ledger.get_trades(start_date="2026-01-18T00:00:00")
    for trade in recent_trades:
        print(f"  {trade.symbol}: Exited {trade.exit_timestamp[:10]} | {trade.net_pnl_pct:+.2f}%")
    
    print()


def demo_statistics(ledger: TradeLedger):
    """Demo summary statistics."""
    print("=" * 80)
    print("DEMO: Summary Statistics")
    print("=" * 80 + "\n")
    
    stats = ledger.get_summary_stats()
    
    print("7. Performance summary:")
    print(f"  Total trades:       {stats['total_trades']}")
    print(f"  Winners:            {stats['winners']} ({stats['win_rate_pct']:.1f}%)")
    print(f"  Losers:             {stats['losers']}")
    print(f"  Average P&L:        {stats['avg_net_pnl_pct']:+.2f}%")
    print(f"  Total P&L:          ${stats['total_net_pnl']:+.2f}")
    print(f"  Avg holding days:   {stats['avg_holding_days']:.1f}")
    print(f"\n  Swing exits:        {stats['swing_exits']}")
    print(f"  Emergency exits:    {stats['emergency_exits']}")
    print()


def demo_export(ledger: TradeLedger):
    """Demo export functionality."""
    print("=" * 80)
    print("DEMO: Export Capabilities")
    print("=" * 80 + "\n")
    
    # Export to CSV
    csv_path = Path("logs/demo_trades.csv")
    ledger.export_to_csv(csv_path)
    print(f"8. ✓ Exported to CSV: {csv_path}")
    
    # Export to JSON
    json_path = Path("logs/demo_trades.json")
    ledger.export_to_json(json_path)
    print(f"9. ✓ Exported to JSON: {json_path}")
    
    print()


def demo_trade_details(ledger: TradeLedger):
    """Demo detailed trade inspection."""
    print("=" * 80)
    print("DEMO: Detailed Trade Information")
    print("=" * 80 + "\n")
    
    print("10. Full trade details (first trade):")
    if ledger.trades:
        trade = ledger.trades[0]
        print(f"\n  Trade ID:         {trade.trade_id}")
        print(f"  Symbol:           {trade.symbol}")
        print(f"\n  ENTRY:")
        print(f"    Order ID:       {trade.entry_order_id}")
        print(f"    Timestamp:      {trade.entry_timestamp}")
        print(f"    Price:          ${trade.entry_price:.2f}")
        print(f"    Quantity:       {trade.entry_quantity}")
        print(f"    Position Size:  ${trade.position_size:.2f}")
        print(f"\n  EXIT:")
        print(f"    Order ID:       {trade.exit_order_id}")
        print(f"    Timestamp:      {trade.exit_timestamp}")
        print(f"    Price:          ${trade.exit_price:.2f}")
        print(f"    Quantity:       {trade.exit_quantity}")
        print(f"    Type:           {trade.exit_type}")
        print(f"    Reason:         {trade.exit_reason}")
        print(f"\n  PERFORMANCE:")
        print(f"    Holding Days:   {trade.holding_days}")
        print(f"    Gross P&L:      ${trade.gross_pnl:+.2f} ({trade.gross_pnl_pct:+.2f}%)")
        print(f"    Fees:           ${trade.fees:.2f}")
        print(f"    Net P&L:        ${trade.net_pnl:+.2f} ({trade.net_pnl_pct:+.2f}%)")
        print(f"\n  RISK CONTEXT:")
        print(f"    Confidence:     {trade.confidence}/5.0")
        print(f"    Risk Amount:    ${trade.risk_amount:.2f}")
    
    print()


def demo_persistence(ledger: TradeLedger):
    """Demo ledger persistence and reload."""
    print("=" * 80)
    print("DEMO: Persistence & Reload")
    print("=" * 80 + "\n")
    
    # Show current ledger
    print(f"11. Current ledger: {len(ledger.trades)} trades")
    
    # Create new ledger instance (should load from disk)
    ledger2 = TradeLedger(ledger_file=Path("logs/demo_trade_ledger.json"))
    print(f"12. Reloaded ledger: {len(ledger2.trades)} trades")
    
    if len(ledger.trades) == len(ledger2.trades):
        print("✓ Persistence working correctly!")
    else:
        print("✗ Persistence issue detected")
    
    print()


def main():
    """Run all demos."""
    print("\n" + "╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "TRADE LEDGER SYSTEM DEMONSTRATION" + " " * 25 + "║")
    print("╚" + "=" * 78 + "╝")
    
    # Run demos
    ledger = demo_basic_usage()
    demo_queries(ledger)
    demo_statistics(ledger)
    demo_export(ledger)
    demo_trade_details(ledger)
    demo_persistence(ledger)
    
    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print("\nCheck these files:")
    print("  • logs/demo_trade_ledger.json  (ledger persistence)")
    print("  • logs/demo_trades.csv         (CSV export)")
    print("  • logs/demo_trades.json        (JSON export)")
    print("\nTo query trades, use: python query_trades.py --help")
    print()


if __name__ == "__main__":
    main()
