"""
Account reconciliation module for startup validation and sync.

Purpose:
- Synchronize local state with Alpaca on startup
- Validate account health, positions, orders, and risk limits
- Establish safe mode if any validation fails
- Prevent trades until all checks pass

Philosophy:
- Alpaca is the source of truth
- Startup reconciliation is mandatory and idempotent
- No auto-liquidation unless risk rules explicitly require it
- All mismatches are logged for audit trail
"""

import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from enum import Enum

from broker.adapter import BrokerAdapter, Position
from broker.trade_ledger import TradeLedger
from risk.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class StartupStatus(Enum):
    """Startup reconciliation outcome."""
    READY = "READY"                    # All checks pass, full trading enabled
    SAFE_MODE = "SAFE_MODE"            # Validation passed but warnings exist, exits only
    EXIT_ONLY = "EXIT_ONLY"            # Risk rules triggered, no new entries allowed
    FAILED = "FAILED"                  # Critical validation failure, no trading
    UNKNOWN = "UNKNOWN"                # Reconciliation not run


class PositionStatus(Enum):
    """Position reconciliation status."""
    KNOWN = "KNOWN"                    # Position in local ledger
    EXTERNAL = "EXTERNAL"              # Alpaca only (not in ledger)
    KEEP = "KEEP"                      # Will keep position
    ELIGIBLE_FOR_EXIT = "ELIGIBLE_FOR_EXIT"  # Exit rules may apply
    FORCE_EXIT = "FORCE_EXIT"          # Risk rules require exit


class AccountReconciler:
    """
    Reconciles local app state with Alpaca account on startup.
    
    Ensures:
    1. Account health (equity, buying power, flags)
    2. Position consistency (local vs Alpaca)
    3. Order consistency (no orphaned/stale orders)
    4. Risk limits are respected
    5. Ledger is consistent with live positions
    """
    
    def __init__(
        self,
        broker: BrokerAdapter,
        trade_ledger: TradeLedger,
        risk_manager: RiskManager,
    ):
        """
        Initialize reconciler.
        
        Args:
            broker: BrokerAdapter (Alpaca)
            trade_ledger: Local trade ledger
            risk_manager: Risk manager instance
        """
        self.broker = broker
        self.trade_ledger = trade_ledger
        self.risk_manager = risk_manager
        
        # Reconciliation state
        self.startup_status = StartupStatus.UNKNOWN
        self.safe_mode = False
        self.validation_warnings = []
        self.validation_errors = []
        
        # External symbol tracking (not in ledger but in Alpaca)
        self.external_symbols = set()  # Symbols only in Alpaca, block duplicate buys
        
        # Snapshots from Alpaca
        self.account_snapshot = None
        self.alpaca_positions = []
        self.alpaca_orders = []
        
        # Validation results
        self.position_validation = {}
        self.buying_power_validation = {}
        self.order_validation = {}
        self.ledger_validation = {}
    
    def reconcile_on_startup(self) -> Dict:
        """
        Execute full startup reconciliation.
        
        Returns:
            {
                "status": StartupStatus,
                "safe_mode": bool,
                "warnings": [str],
                "errors": [str]
            }
        """
        self._log_section("STARTUP RECONCILIATION BEGINNING")
        
        try:
            # STEP 1: Fetch account snapshot
            self._fetch_account_snapshot()
            
            # STEP 2: Fetch open positions from Alpaca
            self._fetch_alpaca_positions()
            
            # STEP 3: Fetch open orders from Alpaca
            self._fetch_alpaca_orders()
            
            # STEP 4: Validate positions
            self._validate_positions()
            
            # STEP 5: Validate buying power and risk
            self._validate_buying_power_and_risk()
            
            # STEP 6: Validate orders
            self._validate_orders()
            
            # STEP 7: Validate ledger consistency
            self._validate_ledger_consistency()
            
            # STEP 8: Determine final startup status
            self._determine_startup_status()
            
            self._log_final_status()
            
        except Exception as e:
            logger.error(f"RECONCILIATION FAILED: {type(e).__name__}: {e}")
            self.validation_errors.append(f"Reconciliation exception: {e}")
            self.startup_status = StartupStatus.FAILED
            self.safe_mode = True
        
        return {
            "status": self.startup_status.value,
            "safe_mode": self.safe_mode,
            "warnings": self.validation_warnings,
            "errors": self.validation_errors,
        }
    
    # ========================================================================
    # STEP 1: Fetch Account Snapshot
    # ========================================================================
    
    def _fetch_account_snapshot(self) -> None:
        """Fetch account status from Alpaca."""
        logger.info("Fetching account snapshot...")
        
        try:
            # Handle mock mode (no client)
            if not self.broker.client:
                logger.warning("Mock mode: using default account snapshot")
                self.account_snapshot = {
                    "status": "ACTIVE",
                    "equity": 100000.0,
                    "cash": 100000.0,
                    "buying_power": 100000.0,
                    "multiplier": 1.0,
                    "trading_blocked": False,
                    "account_blocked": False,
                    "pattern_day_trader": False,
                    "day_trade_count": 0,
                }
                return
            
            account = self.broker.client.get_account()
            
            # Build snapshot from available attributes
            self.account_snapshot = {
                "status": str(account.status),
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "multiplier": float(account.multiplier),
                "trading_blocked": bool(account.trading_blocked),
                "account_blocked": bool(account.account_blocked),
                "pattern_day_trader": bool(getattr(account, "pattern_day_trader", False)),
                "day_trade_count": int(getattr(account, "daytrade_buying_power_check", 0)),
            }
            
            self._log_account_snapshot()
            
        except Exception as e:
            msg = f"Failed to fetch account: {e}"
            logger.error(msg)
            self.validation_errors.append(msg)
            raise
    
    def _log_account_snapshot(self) -> None:
        """Log account snapshot details."""
        s = self.account_snapshot
        
        logger.info("=" * 80)
        logger.info("ACCOUNT SNAPSHOT")
        logger.info("=" * 80)
        logger.info(f"Status: {s['status']}")
        logger.info(f"Equity: ${s['equity']:,.2f}")
        logger.info(f"Cash: ${s['cash']:,.2f}")
        logger.info(f"Buying Power: ${s['buying_power']:,.2f}")
        logger.info(f"Multiplier: {s['multiplier']}x")
        if s.get('day_trade_count', 0) > 0:
            logger.info(f"Day Trades Used: {s['day_trade_count']}")
        logger.info(f"Pattern Day Trader: {s['pattern_day_trader']}")
        logger.info(f"Trading Blocked: {s['trading_blocked']}")
        logger.info(f"Account Blocked: {s['account_blocked']}")
        logger.info("=" * 80)
    
    # ========================================================================
    # STEP 2: Fetch Alpaca Positions
    # ========================================================================
    
    def _fetch_alpaca_positions(self) -> None:
        """Fetch all open positions from Alpaca."""
        logger.info("Fetching open positions from Alpaca...")
        
        try:
            # Handle mock mode (no client)
            if not self.broker.client:
                logger.warning("Mock mode: using empty positions list")
                self.alpaca_positions = []
                return
            
            positions = self.broker.client.get_all_positions()
            self.alpaca_positions = positions or []
            
            logger.info(f"Found {len(self.alpaca_positions)} open position(s)")
            for pos in self.alpaca_positions:
                # Use available attributes (alpaca-py Position API)
                qty = float(pos.qty)
                avg_price = float(getattr(pos, "avg_fill_price", getattr(pos, "entered_avg_fill_price", 0)))
                pnl_pct = float(getattr(pos, "unrealized_plpc", 0)) * 100 if hasattr(pos, "unrealized_plpc") else 0
                logger.debug(
                    f"  {pos.symbol}: {qty} shares @ ${avg_price:.2f} "
                    f"(unrealized P&L: {pnl_pct:+.2f}%)"
                )
            
        except Exception as e:
            msg = f"Failed to fetch positions: {e}"
            logger.error(msg)
            self.validation_errors.append(msg)
            raise
    
    # ========================================================================
    # STEP 3: Fetch Alpaca Orders
    # ========================================================================
    
    def _fetch_alpaca_orders(self) -> None:
        """Fetch all open orders from Alpaca."""
        logger.info("Fetching open orders from Alpaca...")
        
        try:
            # Handle mock mode (no client)
            if not self.broker.client:
                logger.warning("Mock mode: using empty orders list")
                self.alpaca_orders = []
                return
            
            # Try different possible API methods for fetching orders
            orders = None
            
            # Try method 1: list_orders (newer alpaca-py)
            if hasattr(self.broker.client, 'list_orders'):
                orders = self.broker.client.list_orders(status="open")
            # Try method 2: get_orders (alternative)
            elif hasattr(self.broker.client, 'get_orders'):
                orders = self.broker.client.get_orders(status="open")
            else:
                logger.warning("Could not find order listing method in Alpaca client")
                orders = []
            
            self.alpaca_orders = orders or []
            
            logger.info(f"Found {len(self.alpaca_orders)} open order(s)")
            for order in self.alpaca_orders:
                logger.debug(
                    f"  {order.id}: {getattr(order, 'side', 'UNKNOWN').upper()} "
                    f"{order.qty} {order.symbol} (status: {order.status})"
                )
            
        except Exception as e:
            msg = f"Failed to fetch orders (non-critical): {e}"
            logger.warning(msg)
            # Don't fail startup for order fetch - continue with empty list
            self.alpaca_orders = []
    
    # ========================================================================
    # STEP 4: Validate Positions
    # ========================================================================
    
    def _validate_positions(self) -> None:
        """
        Validate each Alpaca position.
        
        For each position:
        - Check if it exists in local ledger
        - Determine if it should be kept or exited
        """
        logger.info("=" * 80)
        logger.info("POSITION VALIDATION")
        logger.info("=" * 80)
        
        self.position_validation = {}
        
        if not self.alpaca_positions:
            logger.info("No open positions to validate")
            return
        
        # Phase 0 Production: Import reconciliation settings
        from config.settings import RECONCILIATION_BACKFILL_ENABLED, RECONCILIATION_MARK_UNKNOWN_CLOSED
        from broker.trade_ledger import OpenPosition, LedgerReconciliationHelper
        
        for pos in self.alpaca_positions:
            symbol = pos.symbol
            qty = float(pos.qty)
            entry_price = float(getattr(pos, "avg_fill_price", getattr(pos, "entered_avg_fill_price", 0)))
            unrealized_pnl_pct = float(getattr(pos, "unrealized_plpc", 0)) * 100
            
            status_result = {
                "symbol": symbol,
                "qty": qty,
                "entry_price": entry_price,
                "unrealized_pnl_pct": unrealized_pnl_pct,
                "status": None,
            }
            
            # Check if position exists in local ledger (trades or open positions)
            ledger_trades = self.trade_ledger.get_trades_for_symbol(symbol)
            has_open_position = (hasattr(self.trade_ledger, '_open_positions') and 
                                symbol in self.trade_ledger._open_positions)
            position_known = bool(ledger_trades) or has_open_position
            
            if not position_known:
                status_result["status"] = PositionStatus.EXTERNAL.value
                msg = (
                    f"EXTERNAL POSITION: {symbol} ({qty} shares) "
                    f"found on Alpaca but not in local ledger"
                )
                logger.warning(msg)
                self.validation_warnings.append(msg)
                
                # PRODUCTION FIX: Backfill ledger from broker position
                if RECONCILIATION_BACKFILL_ENABLED:
                    logger.info(f"Backfilling ledger with broker position: {symbol}")
                    broker_position = OpenPosition.from_alpaca_position(pos)
                    LedgerReconciliationHelper.backfill_broker_position(
                        self.trade_ledger,
                        broker_position,
                        entry_timestamp=None  # Unknown entry time
                    )
            else:
                status_result["status"] = PositionStatus.KEEP.value
                logger.info(f"✓ Position known: {symbol} ({qty} shares)")
            
            self.position_validation[symbol] = status_result
        
        # PRODUCTION FIX: Check for ledger positions not on broker (closed externally)
        if RECONCILIATION_MARK_UNKNOWN_CLOSED and hasattr(self.trade_ledger, '_open_positions'):
            broker_symbols = {pos.symbol for pos in self.alpaca_positions}
            ledger_symbols = set(self.trade_ledger._open_positions.keys())
            
            orphaned_symbols = ledger_symbols - broker_symbols
            for symbol in orphaned_symbols:
                logger.warning(f"Position {symbol} in ledger but not on broker - marking as closed")
                LedgerReconciliationHelper.mark_position_closed(
                    self.trade_ledger,
                    symbol,
                    reason="Position not found on broker during reconciliation"
                )
        
        logger.info("=" * 80)
    
    # ========================================================================
    # STEP 5: Validate Buying Power & Risk
    # ========================================================================
    
    def _validate_buying_power_and_risk(self) -> None:
        """
        Validate account buying power, risk limits, and trading eligibility.
        """
        logger.info("=" * 80)
        logger.info("BUYING POWER & RISK VALIDATION")
        logger.info("=" * 80)
        
        s = self.account_snapshot
        
        # Check 1: Not trading blocked
        if s["trading_blocked"]:
            msg = "CRITICAL: Trading is blocked on this account"
            logger.error(msg)
            self.validation_errors.append(msg)
        
        # Check 2: Not account blocked
        if s["account_blocked"]:
            msg = "CRITICAL: Account is blocked"
            logger.error(msg)
            self.validation_errors.append(msg)
        
        # Check 3: Buying power positive
        if s["buying_power"] <= 0:
            msg = f"WARNING: Buying power is non-positive: ${s['buying_power']:,.2f}"
            logger.warning(msg)
            self.validation_warnings.append(msg)
        
        # Check 4: Minimum buying power (1% of equity)
        min_buying_power = s["equity"] * 0.01
        if s["buying_power"] < min_buying_power:
            msg = (
                f"WARNING: Buying power (${s['buying_power']:,.2f}) "
                f"< 1% of equity (${min_buying_power:,.2f})"
            )
            logger.warning(msg)
            self.validation_warnings.append(msg)
        
        # Check 5: Pattern day trader check
        if s["pattern_day_trader"]:
            logger.info("Account flagged as Pattern Day Trader (PDT)")
        
        # Check 6: Portfolio heat (if available)
        try:
            # Try to get portfolio heat from portfolio state
            from config.settings import MAX_PORTFOLIO_HEAT
            current_heat = sum(
                pos.get("market_value", 0) 
                for pos in self.risk_manager.portfolio.open_positions.values()
            )
            max_heat = s["equity"] * MAX_PORTFOLIO_HEAT
            heat_pct = (current_heat / s["equity"]) * 100 if s["equity"] > 0 else 0
        except Exception as e:
            logger.debug(f"Could not calculate portfolio heat: {e}")
            current_heat = 0
            max_heat = 0
            heat_pct = 0
        
        logger.info(f"Current portfolio heat: ${current_heat:,.2f} ({heat_pct:.2f}%)")
        logger.info(f"Max portfolio heat: ${max_heat:,.2f}")
        
        if current_heat > max_heat:
            msg = (
                f"WARNING: Portfolio heat (${current_heat:,.2f}) "
                f"exceeds max (${max_heat:,.2f})"
            )
            logger.warning(msg)
            self.validation_warnings.append(msg)
        
        # Store validation result
        self.buying_power_validation = {
            "buying_power": s["buying_power"],
            "trading_blocked": s["trading_blocked"],
            "account_blocked": s["account_blocked"],
            "portfolio_heat": current_heat,
            "max_heat": max_heat,
        }
        
        logger.info("=" * 80)
    
    # ========================================================================
    # STEP 6: Validate Orders
    # ========================================================================
    
    def _validate_orders(self) -> None:
        """
        Validate order consistency.
        
        Checks:
        - No duplicate orders for same symbol
        - No stale orders (older than threshold)
        - All orders accounted for
        """
        logger.info("=" * 80)
        logger.info("ORDER VALIDATION")
        logger.info("=" * 80)
        
        if not self.alpaca_orders:
            logger.info("No open orders to validate")
            logger.info("=" * 80)
            return
        
        symbol_counts = {}
        now = datetime.utcnow()
        
        for order in self.alpaca_orders:
            symbol = order.symbol
            order_id = order.id
            side = order.side.upper()
            qty = order.qty
            status = order.status
            submitted_at = order.submitted_at
            
            # Check for duplicate symbols (multiple orders for same symbol)
            if symbol not in symbol_counts:
                symbol_counts[symbol] = 0
            symbol_counts[symbol] += 1
            
            # Check order age
            age_seconds = (now - submitted_at).total_seconds() if submitted_at else 0
            age_minutes = age_seconds / 60
            
            if age_minutes > 60:
                msg = (
                    f"STALE ORDER: {symbol} {side} {qty} "
                    f"(age: {age_minutes:.0f} minutes, status: {status})"
                )
                logger.warning(msg)
                self.validation_warnings.append(msg)
            else:
                logger.info(f"✓ Open order: {symbol} {side} {qty} (status: {status})")
        
        # Check for duplicate symbols
        for symbol, count in symbol_counts.items():
            if count > 1:
                msg = f"WARNING: Multiple open orders for {symbol} ({count} orders)"
                logger.warning(msg)
                self.validation_warnings.append(msg)
        
        self.order_validation = {
            "open_orders_count": len(self.alpaca_orders),
            "symbols_with_multiple_orders": [s for s, c in symbol_counts.items() if c > 1],
        }
        
        logger.info("=" * 80)
    
    # ========================================================================
    # STEP 7: Validate Ledger Consistency
    # ========================================================================
    
    def _validate_ledger_consistency(self) -> None:
        """
        Validate that local ledger is consistent with Alpaca.
        
        Checks:
        - Open trades in ledger match Alpaca positions
        - No closed trades have open Alpaca positions
        """
        logger.info("=" * 80)
        logger.info("LEDGER CONSISTENCY VALIDATION")
        logger.info("=" * 80)
        
        all_trades = self.trade_ledger.get_all_trades()
        open_trades = [t for t in all_trades if t.get("status") == "open"]
        closed_trades = [t for t in all_trades if t.get("status") in ("closed", "exited")]
        
        alpaca_symbols = {pos.symbol for pos in self.alpaca_positions}
        ledger_symbols = {t.get("symbol") for t in open_trades}
        
        logger.info(f"Open trades in ledger: {len(open_trades)}")
        logger.info(f"Closed/exited trades in ledger: {len(closed_trades)}")
        logger.info(f"Open positions on Alpaca: {len(self.alpaca_positions)}")
        
        # Check for trades in ledger but not on Alpaca
        missing_from_alpaca = ledger_symbols - alpaca_symbols
        if missing_from_alpaca:
            msg = (
                f"WARNING: Ledger has open trades for {missing_from_alpaca} "
                f"but no open Alpaca positions (may have been exited elsewhere)"
            )
            logger.warning(msg)
            self.validation_warnings.append(msg)
        
        # Check for external positions (Alpaca but not in ledger)
        external_positions = alpaca_symbols - ledger_symbols
        if external_positions:
            msg = (
                f"Found {len(external_positions)} external position(s) in Alpaca "
                f"not tracked in ledger: {sorted(external_positions)}. "
                f"Will block duplicate BUY orders on these symbols only."
            )
            logger.warning(msg)
            # Track for symbol-level blocking, NOT global SAFE_MODE
            self.external_symbols.update(external_positions)
            logger.info(f"External symbols tracked: {self.external_symbols}")
        
        # Check for closed trades that somehow have open positions
        closed_with_positions = []
        for trade in closed_trades:
            if trade.get("symbol") in alpaca_symbols:
                closed_with_positions.append(trade.get("symbol"))
        
        if closed_with_positions:
            msg = (
                f"WARNING: Closed ledger trades have open Alpaca positions: "
                f"{closed_with_positions} (reconciliation mismatch)"
            )
            logger.warning(msg)
            self.validation_warnings.append(msg)
        
        self.ledger_validation = {
            "open_trades": len(open_trades),
            "closed_trades": len(closed_trades),
            "missing_from_alpaca": list(missing_from_alpaca),
            "external_symbols": list(self.external_symbols),
            "closed_with_positions": closed_with_positions,
        }
        
        logger.info("=" * 80)
    
    # ========================================================================
    # STEP 8: Determine Startup Status
    # ========================================================================
    
    def _determine_startup_status(self) -> None:
        """
        Determine final startup status based on all validations.
        
        Status hierarchy:
        - FAILED: Critical validation failures
        - EXIT_ONLY: Risk checks triggered (account blocked, trading blocked)
        - SAFE_MODE: Serious ledger mismatches (closed trades with open positions, etc.)
        - READY: All checks pass (external symbols tracked separately for symbol-level blocking)
        
        Note: External positions do NOT trigger SAFE_MODE. They're tracked in
        self.external_symbols and blocked at symbol level during trade execution.
        """
        # If any critical errors, fail
        if self.validation_errors:
            self.startup_status = StartupStatus.FAILED
            self.safe_mode = True
            return
        
        # If risk validation triggers, enter EXIT_ONLY mode
        s = self.account_snapshot
        if s["trading_blocked"] or s["account_blocked"]:
            self.startup_status = StartupStatus.EXIT_ONLY
            self.safe_mode = True
            return
        
        # Check for SERIOUS warnings that should trigger SAFE_MODE
        # (but NOT external positions - those are handled symbol-level)
        serious_warnings = []
        for warning in self.validation_warnings:
            # Skip external position warnings - handled via self.external_symbols
            if "external position" in warning.lower():
                continue
            # Other warnings are serious
            serious_warnings.append(warning)
        
        if serious_warnings:
            self.startup_status = StartupStatus.SAFE_MODE
            self.safe_mode = True
            logger.warning(f"Entering SAFE_MODE due to: {serious_warnings}")
            return
        
        # All clear (external symbols tracked separately)
        self.startup_status = StartupStatus.READY
        self.safe_mode = False
        if self.external_symbols:
            logger.info(
                f"Status: READY with {len(self.external_symbols)} external symbols tracked "
                f"(will block duplicate BUY orders only): {self.external_symbols}"
            )
    
    # ========================================================================
    # Logging Helpers
    # ========================================================================
    
    def _log_section(self, title: str) -> None:
        """Log a section header."""
        logger.info("")
        logger.info("=" * 100)
        logger.info(title)
        logger.info("=" * 100)
    
    def _log_final_status(self) -> None:
        """Log final startup status."""
        self._log_section("STARTUP RECONCILIATION COMPLETE")
        
        logger.info(f"Status: {self.startup_status.value}")
        logger.info(f"Safe Mode: {self.safe_mode}")
        logger.info(f"Warnings: {len(self.validation_warnings)}")
        logger.info(f"Errors: {len(self.validation_errors)}")
        
        if self.validation_warnings:
            logger.info("")
            logger.info("Warnings:")
            for warn in self.validation_warnings:
                logger.warning(f"  - {warn}")
        
        if self.validation_errors:
            logger.info("")
            logger.info("Errors:")
            for err in self.validation_errors:
                logger.error(f"  - {err}")
        
        logger.info("")
        if self.startup_status == StartupStatus.READY:
            logger.info("✓ All validations passed. Ready for full trading.")
        elif self.startup_status == StartupStatus.SAFE_MODE:
            logger.info("⚠️  Startup validation warnings. Entering SAFE_MODE.")
            logger.info("   Exits allowed, new entries blocked until issues resolved.")
        elif self.startup_status == StartupStatus.EXIT_ONLY:
            logger.info("🛑 Risk validation failed. Entering EXIT_ONLY mode.")
            logger.info("   Only position exits allowed, no new trades.")
        elif self.startup_status == StartupStatus.FAILED:
            logger.info("❌ CRITICAL: Startup validation failed. NO TRADING.")
            logger.info("   Inspect errors and restart after fixing issues.")
        
        logger.info("=" * 100)
