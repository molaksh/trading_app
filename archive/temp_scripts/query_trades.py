#!/usr/bin/env python3
"""
Trade Ledger Query Tool

Query completed trades and export to various formats.

Examples:
    # Show all trades
    python query_trades.py --all

    # Show trades for specific symbol
    python query_trades.py --symbol AAPL

    # Show only profitable trades
    python query_trades.py --min-pnl 0

    # Show emergency exits only
    python query_trades.py --exit-type EMERGENCY_EXIT

    # Export to CSV
    python query_trades.py --export-csv trades.csv

    # Show summary stats
    python query_trades.py --stats
"""

import argparse
from pathlib import Path
from datetime import datetime
from broker.trade_ledger import TradeLedger
import json


def format_trade(trade):
    """Format trade for display."""
    return (
        f"[{trade.trade_id[:8]}] {trade.symbol} | "
        f"Entry: ${trade.entry_price:.2f} @ {trade.entry_timestamp[:10]} | "
        f"Exit: ${trade.exit_price:.2f} @ {trade.exit_timestamp[:10]} | "
        f"Held {trade.holding_days} days | "
        f"{trade.exit_type} ({trade.exit_reason}) | "
        f"PnL: {trade.net_pnl_pct:+.2f}% (${trade.net_pnl:+.2f})"
    )


def print_summary_stats(ledger: TradeLedger):
    """Print summary statistics."""
    stats = ledger.get_summary_stats()
    
    print("\n" + "=" * 80)
    print("TRADE LEDGER SUMMARY")
    print("=" * 80)
    print(f"Total Trades:       {stats['total_trades']}")
    print(f"Winners:            {stats['winners']} ({stats['win_rate_pct']:.1f}%)")
    print(f"Losers:             {stats['losers']}")
    print(f"Avg Net P&L:        ${stats['avg_net_pnl']:.2f} ({stats['avg_net_pnl_pct']:+.2f}%)")
    print(f"Total Net P&L:      ${stats['total_net_pnl']:+.2f}")
    print(f"Avg Holding Days:   {stats['avg_holding_days']:.1f}")
    print(f"\nExit Breakdown:")
    print(f"  Swing Exits:      {stats['swing_exits']}")
    print(f"  Emergency Exits:  {stats['emergency_exits']}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Query and analyze trade ledger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    # Query filters
    parser.add_argument("--all", action="store_true", help="Show all trades")
    parser.add_argument("--symbol", help="Filter by symbol")
    parser.add_argument("--start-date", help="Filter by start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="Filter by end date (YYYY-MM-DD)")
    parser.add_argument("--exit-type", choices=["SWING_EXIT", "EMERGENCY_EXIT"], help="Filter by exit type")
    parser.add_argument("--min-pnl", type=float, help="Minimum P&L percentage")
    parser.add_argument("--max-pnl", type=float, help="Maximum P&L percentage")
    
    # Output options
    parser.add_argument("--stats", action="store_true", help="Show summary statistics")
    parser.add_argument("--export-csv", metavar="FILE", help="Export to CSV file")
    parser.add_argument("--export-json", metavar="FILE", help="Export to JSON file")
    parser.add_argument("--ledger-file", default="logs/trade_ledger.json", help="Path to ledger file")
    
    # Display options
    parser.add_argument("--limit", type=int, help="Limit number of trades shown")
    parser.add_argument("--sort", choices=["date", "pnl", "holding_days"], default="date", help="Sort trades by")
    
    args = parser.parse_args()
    
    # Load ledger
    ledger_path = Path(args.ledger_file)
    if not ledger_path.exists():
        print(f"❌ Ledger file not found: {ledger_path}")
        print("No trades have been completed yet.")
        return
    
    ledger = TradeLedger(ledger_file=ledger_path)
    
    if len(ledger.trades) == 0:
        print("No trades in ledger.")
        return
    
    # Show stats if requested
    if args.stats:
        print_summary_stats(ledger)
        if not args.all and not args.symbol:
            return
    
    # Query trades
    trades = ledger.get_trades(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        exit_type=args.exit_type,
        min_pnl_pct=args.min_pnl,
        max_pnl_pct=args.max_pnl,
    )
    
    if len(trades) == 0:
        print("No trades match the filters.")
        return
    
    # Sort trades
    if args.sort == "date":
        trades = sorted(trades, key=lambda t: t.exit_timestamp, reverse=True)
    elif args.sort == "pnl":
        trades = sorted(trades, key=lambda t: t.net_pnl_pct, reverse=True)
    elif args.sort == "holding_days":
        trades = sorted(trades, key=lambda t: t.holding_days, reverse=True)
    
    # Limit trades
    if args.limit:
        trades = trades[:args.limit]
    
    # Display trades
    if args.all or args.symbol or any([args.start_date, args.end_date, args.exit_type, args.min_pnl, args.max_pnl]):
        print(f"\nFound {len(trades)} trades:\n")
        for trade in trades:
            print(format_trade(trade))
        print()
    
    # Export to CSV
    if args.export_csv:
        csv_path = Path(args.export_csv)
        ledger.export_to_csv(csv_path)
        print(f"✓ Exported {len(ledger.trades)} trades to {csv_path}")
    
    # Export to JSON
    if args.export_json:
        json_path = Path(args.export_json)
        ledger.export_to_json(json_path)
        print(f"✓ Exported {len(ledger.trades)} trades to {json_path}")


if __name__ == "__main__":
    main()
