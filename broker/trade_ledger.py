"""
Trade Ledger System

Tracks complete trade lifecycles (BUY → SELL) with full accounting.
Separate from event logging - this is the single source of truth for realized P&L.

A TRADE = Entry Fill → Exit Fill (complete lifecycle)
EVENTS are logged separately (signals, orders, fills)

Design:
- Append-only ledger
- Queryable by symbol, date, exit type, profitability
- Exportable to CSV/JSON
- Survives restarts via persistence
- Phase 0: Uses ScopePathResolver for scope-isolated ledger paths

All ledger files stored under PERSISTENCE_ROOT/<scope>/ledger/
"""

import json
import logging
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import csv

from config.scope import get_scope
from config.scope_paths import get_scope_path

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """
    Complete trade record (BUY → SELL).
    
    This represents one full trade lifecycle with all metadata needed for accounting,
    performance analysis, and exit classification.
    """
    # Identity
    trade_id: str
    symbol: str
    
    # Entry (BUY)
    entry_order_id: str
    entry_timestamp: str  # ISO format
    entry_price: float
    entry_quantity: float
    
    # Exit (SELL)
    exit_order_id: str
    exit_timestamp: str  # ISO format
    exit_price: float
    exit_quantity: float
    
    # Classification
    exit_type: str  # "SWING_EXIT" | "EMERGENCY_EXIT"
    exit_reason: str  # Human-readable reason
    
    # Performance Metrics
    holding_days: int
    gross_pnl: float  # Exit value - Entry value
    gross_pnl_pct: float  # (Exit - Entry) / Entry * 100
    fees: float  # Total fees (entry + exit)
    net_pnl: float  # Gross PnL - Fees
    net_pnl_pct: float  # Net PnL / Entry value * 100
    
    # Risk Context (at entry)
    confidence: Optional[float] = None
    risk_amount: Optional[float] = None
    position_size: Optional[float] = None  # Entry value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_summary(self) -> Dict[str, Any]:
        """Condensed summary for display."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "entry_price": round(self.entry_price, 2),
            "exit_price": round(self.exit_price, 2),
            "holding_days": self.holding_days,
            "exit_type": self.exit_type,
            "exit_reason": self.exit_reason,
            "gross_pnl": round(self.gross_pnl, 2),
            "gross_pnl_pct": round(self.gross_pnl_pct, 2),
            "net_pnl": round(self.net_pnl, 2),
            "net_pnl_pct": round(self.net_pnl_pct, 2)
        }
    
    @staticmethod
    def calculate_metrics(
        entry_price: float,
        entry_quantity: float,
        entry_timestamp: str,
        exit_price: float,
        exit_quantity: float,
        exit_timestamp: str,
        fees: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calculate performance metrics.
        
        Returns dict with: holding_days, gross_pnl, gross_pnl_pct, net_pnl, net_pnl_pct
        """
        entry_value = entry_price * entry_quantity
        exit_value = exit_price * exit_quantity
        
        gross_pnl = exit_value - entry_value
        gross_pnl_pct = (gross_pnl / entry_value) * 100 if entry_value > 0 else 0.0
        
        net_pnl = gross_pnl - fees
        net_pnl_pct = (net_pnl / entry_value) * 100 if entry_value > 0 else 0.0
        
        # Calculate holding period
        entry_dt = datetime.fromisoformat(entry_timestamp)
        exit_dt = datetime.fromisoformat(exit_timestamp)
        holding_days = (exit_dt - entry_dt).days
        
        return {
            "holding_days": holding_days,
            "gross_pnl": gross_pnl,
            "gross_pnl_pct": gross_pnl_pct,
            "net_pnl": net_pnl,
            "net_pnl_pct": net_pnl_pct
        }


class TradeLedger:
    """
    Append-only ledger of completed trades.
    
    Responsibilities:
    - Store completed trades (entry + exit fills confirmed)
    - Query trades by various criteria
    - Export to CSV/JSON
    - Persist to disk and reload on restart
    
    NOT responsible for:
    - Tracking pending entries (executor handles that)
    - Event logging (execution_logger handles that)
    - Strategy decisions
    """
    
    def __init__(self, ledger_file: Optional[Path] = None):
        """
        Initialize trade ledger.
        
        Args:
            ledger_file: Path to persist ledger (JSON). If None, uses ScopePathResolver.
        """
        self.trades: List[Trade] = []
        
        if ledger_file is None:
            # Phase 0: Use scope-aware path resolver
            scope = get_scope()
            ledger_dir = get_scope_path(scope, "ledger")
            ledger_file = ledger_dir / "trades.jsonl"
        
        self.ledger_file = Path(ledger_file)
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing trades
        self._load_from_disk()
        
        scope = get_scope()
        logger.info("=" * 80)
        logger.info(f"TRADE LEDGER INITIALIZED (SCOPE: {scope})")
        logger.info(f"  Ledger file: {self.ledger_file}")
        logger.info(f"  Existing trades: {len(self.trades)}")
        logger.info("=" * 80)
    
    def add_trade(self, trade: Trade) -> None:
        """
        Add completed trade to ledger.
        
        This is append-only - trades are never modified after creation.
        Automatically persists to disk.
        
        Args:
            trade: Complete trade object
        """
        self.trades.append(trade)
        logger.info(
            f"Trade logged: {trade.symbol} | "
            f"{trade.exit_type} | "
            f"PnL: {trade.net_pnl_pct:+.2f}% | "
            f"Held {trade.holding_days} days | "
            f"Reason: {trade.exit_reason}"
        )
        
        # Persist immediately
        self._save_to_disk()
    
    def get_all_trades(self) -> List[Trade]:
        """
        Get all trades in the ledger.
        
        Returns:
            List of all Trade objects
        """
        return self.trades.copy()
    
    def get_trades_for_symbol(self, symbol: str) -> List[Trade]:
        """
        Get all trades for a specific symbol.
        
        Args:
            symbol: Ticker symbol
        
        Returns:
            List of trades for that symbol
        """
        return [t for t in self.trades if t.symbol == symbol]
    
    def get_trades(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        exit_type: Optional[str] = None,
        min_pnl_pct: Optional[float] = None,
        max_pnl_pct: Optional[float] = None
    ) -> List[Trade]:
        """
        Query trades with filters.
        
        Args:
            symbol: Filter by symbol (exact match)
            start_date: Filter by exit_timestamp >= start_date (ISO format)
            end_date: Filter by exit_timestamp <= end_date (ISO format)
            exit_type: Filter by exit type ("SWING_EXIT" | "EMERGENCY_EXIT")
            min_pnl_pct: Filter by net_pnl_pct >= min_pnl_pct
            max_pnl_pct: Filter by net_pnl_pct <= max_pnl_pct
        
        Returns:
            List of trades matching all filters
        """
        filtered = self.trades
        
        if symbol:
            filtered = [t for t in filtered if t.symbol == symbol]
        
        if start_date:
            filtered = [t for t in filtered if t.exit_timestamp >= start_date]
        
        if end_date:
            filtered = [t for t in filtered if t.exit_timestamp <= end_date]
        
        if exit_type:
            filtered = [t for t in filtered if t.exit_type == exit_type]
        
        if min_pnl_pct is not None:
            filtered = [t for t in filtered if t.net_pnl_pct >= min_pnl_pct]
        
        if max_pnl_pct is not None:
            filtered = [t for t in filtered if t.net_pnl_pct <= max_pnl_pct]
        
        return filtered
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """
        Calculate summary statistics across all trades.
        
        Returns:
            Dict with total trades, winners, losers, win rate, avg PnL, etc.
        """
        if not self.trades:
            return {
                "total_trades": 0,
                "winners": 0,
                "losers": 0,
                "win_rate_pct": 0.0,
                "avg_net_pnl": 0.0,
                "avg_net_pnl_pct": 0.0,
                "total_net_pnl": 0.0,
                "avg_holding_days": 0.0,
                "swing_exits": 0,
                "emergency_exits": 0
            }
        
        winners = [t for t in self.trades if t.net_pnl > 0]
        losers = [t for t in self.trades if t.net_pnl <= 0]
        swing_exits = [t for t in self.trades if t.exit_type == "SWING_EXIT"]
        emergency_exits = [t for t in self.trades if t.exit_type == "EMERGENCY_EXIT"]
        
        total_net_pnl = sum(t.net_pnl for t in self.trades)
        avg_net_pnl = total_net_pnl / len(self.trades)
        avg_net_pnl_pct = sum(t.net_pnl_pct for t in self.trades) / len(self.trades)
        avg_holding_days = sum(t.holding_days for t in self.trades) / len(self.trades)
        
        return {
            "total_trades": len(self.trades),
            "winners": len(winners),
            "losers": len(losers),
            "win_rate_pct": (len(winners) / len(self.trades)) * 100,
            "avg_net_pnl": avg_net_pnl,
            "avg_net_pnl_pct": avg_net_pnl_pct,
            "total_net_pnl": total_net_pnl,
            "avg_holding_days": avg_holding_days,
            "swing_exits": len(swing_exits),
            "emergency_exits": len(emergency_exits)
        }
    
    def export_to_csv(self, filepath: Path) -> None:
        """
        Export all trades to CSV.
        
        Args:
            filepath: Path to CSV file
        """
        if not self.trades:
            logger.warning("No trades to export")
            return
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', newline='') as f:
            # Get field names from first trade
            fieldnames = list(self.trades[0].to_dict().keys())
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            writer.writeheader()
            for trade in self.trades:
                writer.writerow(trade.to_dict())
        
        logger.info(f"Exported {len(self.trades)} trades to {filepath}")
    
    def export_to_json(self, filepath: Path, pretty: bool = True) -> None:
        """
        Export all trades to JSON.
        
        Args:
            filepath: Path to JSON file
            pretty: If True, format with indentation
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        trades_dict = [trade.to_dict() for trade in self.trades]
        
        with open(filepath, 'w') as f:
            if pretty:
                json.dump(trades_dict, f, indent=2)
            else:
                json.dump(trades_dict, f)
        
        logger.info(f"Exported {len(self.trades)} trades to {filepath}")
    
    def _save_to_disk(self) -> None:
        """Persist ledger to disk (JSONL format)."""
        try:
            with open(self.ledger_file, 'w') as f:
                for trade in self.trades:
                    f.write(json.dumps(trade.to_dict()) + "\n")
        except Exception as e:
            # Logging failures must not block execution
            logger.error(f"Failed to save trade ledger: {e}")
    
    def _load_from_disk(self) -> None:
        """Load existing trades from disk (JSONL)."""
        if not self.ledger_file.exists():
            logger.info("No existing ledger file found (will create on first trade)")
            return
        
        try:
            with open(self.ledger_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    trade_dict = json.loads(line)
                    trade = Trade(**trade_dict)
                    self.trades.append(trade)
            
            logger.info(f"Loaded {len(self.trades)} trades from {self.ledger_file}")
        except Exception as e:
            logger.error(f"Failed to load trade ledger: {e}")
            # Continue with empty ledger rather than crash


def create_trade_from_fills(
    symbol: str,
    entry_order_id: str,
    entry_fill_timestamp: str,
    entry_fill_price: float,
    entry_fill_quantity: float,
    exit_order_id: str,
    exit_fill_timestamp: str,
    exit_fill_price: float,
    exit_fill_quantity: float,
    exit_type: str,
    exit_reason: str,
    confidence: Optional[float] = None,
    risk_amount: Optional[float] = None,
    fees: float = 0.0
) -> Trade:
    """
    Factory function to create Trade from entry and exit fills.
    
    Calculates all performance metrics automatically.
    
    Args:
        symbol: Ticker symbol
        entry_order_id: Entry order ID
        entry_fill_timestamp: Entry fill timestamp (ISO format)
        entry_fill_price: Entry fill price
        entry_fill_quantity: Entry fill quantity
        exit_order_id: Exit order ID
        exit_fill_timestamp: Exit fill timestamp (ISO format)
        exit_fill_price: Exit fill price
        exit_fill_quantity: Exit fill quantity
        exit_type: "SWING_EXIT" | "EMERGENCY_EXIT"
        exit_reason: Human-readable exit reason
        confidence: Signal confidence at entry (optional)
        risk_amount: Risk amount at entry (optional)
        fees: Total fees (entry + exit)
    
    Returns:
        Complete Trade object
    """
    # Calculate metrics
    metrics = Trade.calculate_metrics(
        entry_price=entry_fill_price,
        entry_quantity=entry_fill_quantity,
        entry_timestamp=entry_fill_timestamp,
        exit_price=exit_fill_price,
        exit_quantity=exit_fill_quantity,
        exit_timestamp=exit_fill_timestamp,
        fees=fees
    )
    
    # Calculate position size
    position_size = entry_fill_price * entry_fill_quantity
    
    return Trade(
        trade_id=str(uuid.uuid4()),
        symbol=symbol,
        entry_order_id=entry_order_id,
        entry_timestamp=entry_fill_timestamp,
        entry_price=entry_fill_price,
        entry_quantity=entry_fill_quantity,
        exit_order_id=exit_order_id,
        exit_timestamp=exit_fill_timestamp,
        exit_price=exit_fill_price,
        exit_quantity=exit_fill_quantity,
        exit_type=exit_type,
        exit_reason=exit_reason,
        holding_days=metrics["holding_days"],
        gross_pnl=metrics["gross_pnl"],
        gross_pnl_pct=metrics["gross_pnl_pct"],
        fees=fees,
        net_pnl=metrics["net_pnl"],
        net_pnl_pct=metrics["net_pnl_pct"],
        confidence=confidence,
        risk_amount=risk_amount,
        position_size=position_size
    )


# ============================================================================
# RECONCILIATION HELPERS (Production Hardening)
# ============================================================================

@dataclass
class OpenPosition:
    """
    Represents an open position from broker (for reconciliation).
    
    Used to backfill ledger from broker positions during startup.
    """
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    
    @classmethod
    def from_alpaca_position(cls, alpaca_pos):
        """Create from Alpaca API position object."""
        qty = float(alpaca_pos.qty)
        avg_price = float(alpaca_pos.avg_entry_price)
        current_price = float(alpaca_pos.current_price)
        
        cost_basis = avg_price * qty
        market_value = current_price * qty
        unrealized_pnl = market_value - cost_basis
        unrealized_pnl_pct = (unrealized_pnl / cost_basis) * 100 if cost_basis > 0 else 0.0
        
        return cls(
            symbol=alpaca_pos.symbol,
            quantity=qty,
            avg_entry_price=avg_price,
            current_price=current_price,
            market_value=market_value,
            cost_basis=cost_basis,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct
        )


class LedgerReconciliationHelper:
    """
    Helper for reconciling trade ledger with broker state.
    
    Used by AccountReconciler to ensure ledger matches broker positions.
    """
    
    @staticmethod
    def backfill_broker_position(
        ledger: 'TradeLedger',
        position: OpenPosition,
        entry_timestamp: Optional[str] = None
    ) -> None:
        """
        Create a ledger entry for an external broker position.
        
        This creates an "open trade" record to represent an existing position
        that was entered outside the system (manual trade, different system, etc.).
        
        IMPORTANT: This does NOT create a completed trade (no exit).
        Instead, it creates metadata that can be referenced when the position
        is eventually exited.
        
        Args:
            ledger: Trade ledger instance
            position: OpenPosition from broker
            entry_timestamp: When position was opened (if known), else uses current time
        """
        from datetime import datetime
        
        if entry_timestamp is None:
            entry_timestamp = datetime.now().isoformat()
        
        # Create a synthetic order ID for the external entry
        synthetic_order_id = f"EXTERNAL_{position.symbol}_{entry_timestamp}"
        
        # Log reconciliation action
        logger.info(
            f"LEDGER RECONCILIATION: Backfilling external position {position.symbol} "
            f"(qty={position.quantity}, avg={position.avg_entry_price:.2f})"
        )
        
        # Store metadata for later exit tracking
        # NOTE: This is a partial record - will be completed when position closes
        metadata = {
            "symbol": position.symbol,
            "entry_order_id": synthetic_order_id,
            "entry_timestamp": entry_timestamp,
            "entry_price": position.avg_entry_price,
            "entry_quantity": position.quantity,
            "source": "BROKER_RECONCILIATION",
            "reconciled_at": datetime.now().isoformat()
        }
        
        # Store in ledger's internal tracking (not a completed trade yet)
        if not hasattr(ledger, '_open_positions'):
            ledger._open_positions = {}
        
        ledger._open_positions[position.symbol] = metadata
        logger.info(f"✓ Position {position.symbol} tracked in ledger for future exit")
    
    @staticmethod
    def mark_position_closed(
        ledger: 'TradeLedger',
        symbol: str,
        reason: str = "Position not found on broker"
    ) -> None:
        """
        Mark a ledger position as closed if it no longer exists on broker.
        
        This handles cases where a position was exited outside the system
        (manual close, liquidation, etc.).
        
        Args:
            ledger: Trade ledger instance
            symbol: Symbol to mark as closed
            reason: Reason for closure
        """
        logger.warning(
            f"LEDGER RECONCILIATION: Position {symbol} in ledger but not on broker. "
            f"Reason: {reason}"
        )
        
        # Check if we have open position metadata
        if hasattr(ledger, '_open_positions') and symbol in ledger._open_positions:
            metadata = ledger._open_positions[symbol]
            
            # Create a completed trade with EXTERNAL_CLOSE exit type
            from datetime import datetime
            now = datetime.now().isoformat()
            
            # Use current market price as exit (best approximation)
            # In production, you'd fetch the last known price
            exit_price = metadata['entry_price']  # Pessimistic: assume breakeven
            
            trade = create_trade(
                symbol=symbol,
                entry_order_id=metadata['entry_order_id'],
                entry_fill_timestamp=metadata['entry_timestamp'],
                entry_fill_price=metadata['entry_price'],
                entry_fill_quantity=metadata['entry_quantity'],
                exit_order_id=f"EXTERNAL_CLOSE_{symbol}_{now}",
                exit_fill_timestamp=now,
                exit_fill_price=exit_price,
                exit_fill_quantity=metadata['entry_quantity'],
                exit_type="EXTERNAL_CLOSE",
                exit_reason=reason,
                confidence=None,
                risk_amount=None,
                fees=0.0
            )
            
            ledger.add_trade(trade)
            del ledger._open_positions[symbol]
            logger.info(f"✓ Created EXTERNAL_CLOSE trade for {symbol}")
        else:
            logger.warning(f"No open position metadata found for {symbol} - cannot backfill closure")

