"""
Portfolio state tracking for risk management.

Maintains current state of:
- Account equity and available capital
- Open positions and per-symbol exposure
- Portfolio heat (total open risk)
- Daily and consecutive performance metrics
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd

logger = logging.getLogger(__name__)


class OpenPosition:
    """Represents a single open position."""
    
    def __init__(
        self,
        symbol: str,
        entry_date: pd.Timestamp,
        entry_price: float,
        position_size: float,
        risk_amount: float,
        confidence: int,
    ):
        """
        Initialize position.
        
        Args:
            symbol: Stock ticker
            entry_date: Date position opened
            entry_price: Entry price
            position_size: Number of shares
            risk_amount: Dollar amount at risk
            confidence: Confidence score when entered (1-5)
        """
        self.symbol = symbol
        self.entry_date = entry_date
        self.entry_price = entry_price
        self.position_size = position_size
        self.risk_amount = risk_amount
        self.confidence = confidence
        self.unrealized_pnl = 0.0
        self.current_price = entry_price
    
    def update_price(self, current_price: float) -> None:
        """Update unrealized P&L based on current price."""
        self.current_price = current_price
        self.unrealized_pnl = (current_price - self.entry_price) * self.position_size
    
    def get_current_value(self) -> float:
        """Get current position value at market price."""
        return self.current_price * self.position_size
    
    def __repr__(self) -> str:
        return (
            f"Position({self.symbol}, {self.entry_date.date()}, "
            f"size={self.position_size:.0f}, conf={self.confidence})"
        )


class PortfolioState:
    """
    Tracks portfolio state for risk management.
    
    Maintains:
    - Account equity
    - Open positions
    - Portfolio heat
    - Daily P&L
    - Consecutive losses
    """
    
    def __init__(self, initial_equity: float):
        """
        Initialize portfolio state.
        
        Args:
            initial_equity: Starting account equity
        """
        self.initial_equity = initial_equity
        self.current_equity = initial_equity
        self.available_capital = initial_equity
        
        # Open positions: symbol -> list of OpenPosition
        self.open_positions: Dict[str, List[OpenPosition]] = {}
        
        # Daily tracking
        self.daily_start_date: Optional[pd.Timestamp] = None
        self.daily_start_equity: float = initial_equity
        self.daily_pnl: float = 0.0
        self.daily_trades_opened: int = 0
        self.daily_trades_closed: int = 0
        
        # Consecutive loss tracking
        self.consecutive_losses: int = 0
        self.last_trade_return: float = 0.0
        
        # History tracking
        self.equity_history: List[Tuple[pd.Timestamp, float]] = [(pd.Timestamp.now(), initial_equity)]
        self.trades_closed: List[Dict] = []

        # Cash reserve set by LiquidityManager after selling positions
        self.cash_reserve = None
        
        logger.info(f"Portfolio initialized with equity: ${initial_equity:,.2f}")

    def sync_account_balances(
        self,
        equity: float,
        cash: float,
        buying_power: float,
        cash_only: bool,
    ) -> None:
        """
        Sync portfolio balances from broker snapshot.

        Args:
            equity: Account equity from broker
            cash: Account cash from broker
            buying_power: Account buying power from broker
            cash_only: If True, use cash as trading equity (no margin)
        """
        new_equity = cash if cash_only else equity
        if new_equity <= 0:
            logger.warning(
                "Broker equity/cash is non-positive. "
                f"equity={equity:.2f} cash={cash:.2f} buying_power={buying_power:.2f}"
            )
        self.current_equity = max(0.0, new_equity)
        self.available_capital = self.current_equity
        if self.daily_start_date is None:
            self.daily_start_equity = self.current_equity
        logger.info(
            "Portfolio synced from broker: equity=$%.2f cash=$%.2f buying_power=$%.2f cash_only=%s"
            % (equity, cash, buying_power, cash_only)
        )
    
    def open_trade(
        self,
        symbol: str,
        entry_date: pd.Timestamp,
        entry_price: float,
        position_size: float,
        risk_amount: float,
        confidence: int,
    ) -> None:
        """
        Record a new open position.
        
        Args:
            symbol: Stock ticker
            entry_date: Date position opened
            entry_price: Entry price
            position_size: Number of shares
            risk_amount: Dollar amount at risk
            confidence: Confidence score (1-5)
        """
        if symbol not in self.open_positions:
            self.open_positions[symbol] = []
        
        position = OpenPosition(
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            position_size=position_size,
            risk_amount=risk_amount,
            confidence=confidence,
        )
        self.open_positions[symbol].append(position)
        self.daily_trades_opened += 1
        
        logger.debug(f"Opened position: {position}")
    
    def close_trade(
        self,
        symbol: str,
        exit_date: pd.Timestamp,
        exit_price: float,
    ) -> Optional[Dict]:
        """
        Close a position and record trade result.
        
        Args:
            symbol: Stock ticker
            exit_date: Date position closed
            exit_price: Exit price
        
        Returns:
            Dict with trade details or None if no position found
        """
        if symbol not in self.open_positions or not self.open_positions[symbol]:
            return None
        
        position = self.open_positions[symbol].pop(0)  # FIFO
        position.update_price(exit_price)
        
        # Record trade
        trade_return = (exit_price - position.entry_price) / position.entry_price
        pnl = position.unrealized_pnl
        
        trade_dict = {
            'symbol': symbol,
            'entry_date': position.entry_date,
            'exit_date': exit_date,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'position_size': position.position_size,
            'pnl': pnl,
            'return': trade_return,
            'confidence': position.confidence,
        }
        
        self.trades_closed.append(trade_dict)
        self.daily_trades_closed += 1
        self.last_trade_return = trade_return
        
        # Update consecutive losses
        if trade_return < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        # Update equity
        self.current_equity += pnl
        self.daily_pnl += pnl
        
        logger.debug(
            f"Closed position: {symbol} @ {exit_price:.2f}, "
            f"Return={trade_return:.2%}, PnL=${pnl:.2f}"
        )
        
        return trade_dict
    
    def update_equity_at_date(self, current_date: pd.Timestamp) -> None:
        """
        Update daily tracking for new date.
        
        Args:
            current_date: Current date in backtest
        """
        if self.daily_start_date is None or current_date.date() != self.daily_start_date.date():
            # New day
            self.daily_start_date = current_date
            self.daily_start_equity = self.current_equity
            self.daily_pnl = 0.0
            self.daily_trades_opened = 0
            self.daily_trades_closed = 0
    
    def get_portfolio_heat(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate total portfolio heat (risk at stake).
        
        Args:
            current_prices: Symbol -> current price dict
        
        Returns:
            Total portfolio heat as % of current equity
        """
        total_risk = 0.0
        
        for symbol, positions in self.open_positions.items():
            for position in positions:
                if symbol in current_prices:
                    position.update_price(current_prices[symbol])
                total_risk += position.risk_amount
        
        if self.current_equity <= 0:
            return 100.0  # Safety valve
        
        heat = total_risk / self.current_equity
        return heat
    
    def get_symbol_exposure(self, symbol: str) -> float:
        """
        Get total exposure to a symbol as % of equity.
        
        Args:
            symbol: Stock ticker
        
        Returns:
            Total position size for symbol as % of equity
        """
        if symbol not in self.open_positions:
            return 0.0
        
        total_value = sum(
            pos.get_current_value() for pos in self.open_positions[symbol]
        )
        
        if self.current_equity <= 0:
            return 100.0
        
        return total_value / self.current_equity
    
    def get_available_capital(self) -> float:
        """
        Get available capital for new trades.
        
        Returns:
            Available capital (current equity - open position value)
        """
        total_open_value = sum(
            pos.get_current_value()
            for positions in self.open_positions.values()
            for pos in positions
        )

        available = max(0.0, self.current_equity - total_open_value)

        # Subtract active cash reserve (set by LiquidityManager)
        if self.cash_reserve is not None:
            reserved = self.cash_reserve.get_reserved_amount()
            if reserved > 0:
                available = max(0.0, available - reserved)

        return available
    
    def get_open_positions_count(self) -> int:
        """Get total number of open positions."""
        return sum(
            len(positions) for positions in self.open_positions.values()
        )
    
    def get_open_symbols(self) -> List[str]:
        """Get list of symbols with open positions."""
        return [s for s, pos in self.open_positions.items() if pos]
    
    def get_daily_loss_pct(self) -> float:
        """
        Get daily loss as % of starting equity.
        
        Returns:
            Daily loss percentage (negative if down, positive if up)
        """
        if self.daily_start_equity <= 0:
            return 0.0
        return self.daily_pnl / self.daily_start_equity
    
    def get_cumulative_return(self) -> float:
        """
        Get cumulative return since portfolio inception.
        
        Returns:
            Cumulative return as percentage
        """
        if self.initial_equity <= 0:
            return 0.0
        return (self.current_equity - self.initial_equity) / self.initial_equity
    
    def get_win_rate_from_trades(self) -> float:
        """
        Get win rate from closed trades.
        
        Returns:
            Win rate as percentage (0-100)
        """
        if not self.trades_closed:
            return 0.0
        
        winning_trades = sum(1 for t in self.trades_closed if t['return'] >= 0)
        return 100 * winning_trades / len(self.trades_closed)
    
    def get_summary(self) -> Dict:
        """
        Get complete portfolio summary.
        
        Returns:
            Dict with current state
        """
        return {
            'current_equity': self.current_equity,
            'available_capital': self.get_available_capital(),
            'open_positions': self.get_open_positions_count(),
            'open_symbols': self.get_open_symbols(),
            'daily_pnl': self.daily_pnl,
            'daily_loss_pct': self.get_daily_loss_pct(),
            'cumulative_return': self.get_cumulative_return(),
            'consecutive_losses': self.consecutive_losses,
            'total_trades_closed': len(self.trades_closed),
            'win_rate': self.get_win_rate_from_trades(),
            'cash_reserve': self.cash_reserve.get_reserved_amount() if self.cash_reserve else 0.0,
        }
    
    def log_summary(self) -> None:
        """Log current portfolio summary."""
        summary = self.get_summary()
        logger.info("\nPortfolio Summary:")
        logger.info(f"  Equity: ${summary['current_equity']:,.2f}")
        logger.info(f"  Open positions: {summary['open_positions']}")
        logger.info(f"  Daily P&L: ${summary['daily_pnl']:,.2f} ({summary['daily_loss_pct']:.2%})")
        logger.info(f"  Cumulative return: {summary['cumulative_return']:.2%}")
        logger.info(f"  Win rate: {summary['win_rate']:.1f}%")
