"""
Risk-governed backtest with position sizing and trade approval.

Wraps the standard backtest with:
- Trade approval by risk manager
- Confidence-based position sizing
- Portfolio state tracking
- Risk metric logging
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import pandas as pd

from config.settings import (
    BACKTEST_LOOKBACK_YEARS,
    HOLD_DAYS,
    BACKTEST_MIN_CONFIDENCE,
    LOOKBACK_DAYS,
    STARTING_CAPITAL,
)
from data.price_loader import load_price_data
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol
from backtest.simple_backtest import Trade
from risk.risk_manager import RiskManager, TradeDecision
from risk.portfolio_state import PortfolioState

logger = logging.getLogger(__name__)


class RiskGovernedBacktest:
    """
    Backtest with strict risk management.
    
    Applies risk rules during backtesting:
    - Trade approval before entry
    - Position sizing based on confidence
    - Portfolio heat tracking
    - Daily loss limits
    - Consecutive loss limits
    """
    
    def __init__(self, symbols: List[str], enforce_risk: bool = True):
        """
        Initialize risk-governed backtest.
        
        Args:
            symbols: List of stock tickers to backtest
            enforce_risk: If True, apply risk limits; if False, execute all trades
        """
        self.symbols = symbols
        self.enforce_risk = enforce_risk
        
        # Initialize risk manager
        self.risk_manager = RiskManager(PortfolioState(STARTING_CAPITAL))
        self.portfolio_state = self.risk_manager.portfolio
        
        # Results tracking
        self.trades: List[Trade] = []
        self.rejected_trades: List[Dict] = []
        self.max_portfolio_heat: float = 0.0
        
        logger.info("=" * 100)
        logger.info(f"Running risk-governed backtest ({BACKTEST_LOOKBACK_YEARS}Y, hold {HOLD_DAYS}D)")
        if self.enforce_risk:
            logger.info("RISK MANAGEMENT: ENABLED")
        else:
            logger.info("RISK MANAGEMENT: DISABLED (research mode)")
        logger.info("=" * 100)
    
    def run(self) -> List[Trade]:
        """
        Execute risk-governed backtest.
        
        Returns:
            List of Trade objects
        """
        trades: List[Trade] = []
        
        # Calculate start date
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * BACKTEST_LOOKBACK_YEARS)
        
        logger.info(f"\nBacktest period: {start_date.date()} to {end_date.date()}")
        logger.info(f"Testing {len(self.symbols)} symbols...")
        
        for i, symbol in enumerate(self.symbols):
            logger.debug(f"[{i+1}/{len(self.symbols)}] {symbol}")
            
            try:
                # Load full history
                full_df = load_price_data(
                    symbol,
                    lookback_days=LOOKBACK_DAYS + 365 * BACKTEST_LOOKBACK_YEARS
                )
                if full_df is None or len(full_df) == 0:
                    continue
                
                # Generate trade dates
                trade_dates = [d for d in full_df.index if start_date <= d <= end_date]
                if not trade_dates:
                    continue
                
                # Open positions for this symbol
                open_positions: Dict = {}
                
                # Walk through dates
                for trade_date in trade_dates:
                    # Update date tracking for risk manager
                    self.portfolio_state.update_equity_at_date(trade_date)
                    
                    # Get data up to this date
                    data_up_to_date = full_df.loc[:trade_date].copy()
                    
                    if len(data_up_to_date) < LOOKBACK_DAYS:
                        continue
                    
                    # Compute features
                    features_df = compute_features(data_up_to_date)
                    if features_df is None or len(features_df) == 0:
                        continue
                    
                    latest_row = features_df.iloc[-1].copy()
                    if latest_row.isna().any():
                        continue
                    
                    # Score the signal
                    confidence = score_symbol(latest_row)
                    if confidence is None:
                        continue
                    
                    # Check for exit: if position open and hold period expired
                    if symbol in open_positions:
                        entry_date = open_positions[symbol]["entry_date"]
                        exit_check_date = entry_date + timedelta(days=HOLD_DAYS)
                        
                        if trade_date >= exit_check_date:
                            # Exit position
                            exit_price = (
                                full_df.loc[trade_date, "Open"]
                                if "Open" in full_df.columns
                                else full_df.loc[trade_date, "Close"]
                            )
                            
                            # Record trade
                            trade = Trade(
                                symbol=symbol,
                                entry_date=open_positions[symbol]["entry_date"],
                                entry_price=open_positions[symbol]["entry_price"],
                                exit_date=trade_date,
                                exit_price=exit_price,
                                confidence=open_positions[symbol]["confidence"],
                            )
                            trades.append(trade)
                            
                            # Update portfolio state
                            self.portfolio_state.close_trade(
                                symbol, trade_date, exit_price
                            )
                            
                            del open_positions[symbol]
                    
                    # Check for entry
                    if symbol not in open_positions and confidence >= BACKTEST_MIN_CONFIDENCE:
                        # Get current prices for portfolio heat
                        current_prices = {symbol: full_df.loc[trade_date, "Close"]}
                        
                        # Evaluate trade under risk constraints
                        if self.enforce_risk:
                            decision = self.risk_manager.evaluate_trade(
                                symbol=symbol,
                                entry_price=full_df.loc[trade_date, "Close"],
                                confidence=confidence,
                                current_prices=current_prices,
                            )
                            
                            if not decision.approved:
                                self.rejected_trades.append({
                                    'symbol': symbol,
                                    'date': trade_date,
                                    'reason': decision.reason,
                                })
                                logger.debug(
                                    f"  {symbol} REJECTED: {decision.reason}"
                                )
                                continue
                            
                            position_size = decision.position_size
                            risk_amount = decision.risk_amount
                        else:
                            # Research mode: no risk limits
                            position_size = STARTING_CAPITAL * 0.01 / full_df.loc[trade_date, "Close"]
                            risk_amount = STARTING_CAPITAL * 0.01
                        
                        # Get entry price for next day
                        trade_dates_list = list(full_df.index)
                        current_idx = trade_dates_list.index(trade_date)
                        
                        if current_idx + 1 < len(trade_dates_list):
                            next_date = trade_dates_list[current_idx + 1]
                            entry_price = (
                                full_df.loc[next_date, "Open"]
                                if "Open" in full_df.columns
                                else full_df.loc[next_date, "Close"]
                            )
                        else:
                            entry_price = full_df.loc[trade_date, "Close"]
                        
                        # Record open position in portfolio
                        self.portfolio_state.open_trade(
                            symbol=symbol,
                            entry_date=trade_date,
                            entry_price=entry_price,
                            position_size=position_size,
                            risk_amount=risk_amount,
                            confidence=confidence,
                        )
                        
                        # Track position locally
                        open_positions[symbol] = {
                            "entry_date": trade_date,
                            "entry_price": entry_price,
                            "confidence": confidence,
                        }
                        
                        # Update max portfolio heat
                        heat = self.risk_manager._calculate_proposed_portfolio_heat(
                            risk_amount, current_prices
                        )
                        self.max_portfolio_heat = max(self.max_portfolio_heat, heat)
            
            except Exception as e:
                logger.debug(f"{symbol}: {type(e).__name__}: {e}")
                continue
        
        self.trades = trades
        
        logger.info(f"\nBacktest complete:")
        logger.info(f"  Total trades: {len(trades)}")
        logger.info(f"  Rejected trades: {len(self.rejected_trades)}")
        
        return trades
    
    def get_summary(self) -> Dict:
        """Get backtest summary with risk metrics."""
        portfolio_summary = self.portfolio_state.get_summary()
        risk_summary = self.risk_manager.get_summary()
        
        return {
            'trades': len(self.trades),
            'rejected_trades': len(self.rejected_trades),
            'final_equity': portfolio_summary['current_equity'],
            'cumulative_return': portfolio_summary['cumulative_return'],
            'win_rate': portfolio_summary['win_rate'],
            'max_portfolio_heat': self.max_portfolio_heat,
            'consecutive_losses': portfolio_summary['consecutive_losses'],
            'approval_rate': risk_summary['approval_rate'],
            'rejection_breakdown': risk_summary['rejection_breakdown'],
        }
    
    def log_summary(self) -> None:
        """Log complete backtest summary."""
        logger.info("\n" + "=" * 100)
        logger.info("RISK-GOVERNED BACKTEST SUMMARY")
        logger.info("=" * 100)
        
        summary = self.get_summary()
        
        logger.info(f"\nTrading Results:")
        logger.info(f"  Total trades: {summary['trades']}")
        logger.info(f"  Rejected trades: {summary['rejected_trades']}")
        logger.info(f"  Win rate: {summary['win_rate']:.1f}%")
        
        logger.info(f"\nPortfolio Performance:")
        logger.info(f"  Final equity: ${summary['final_equity']:,.2f}")
        logger.info(f"  Cumulative return: {summary['cumulative_return']:.2%}")
        logger.info(f"  Max portfolio heat: {summary['max_portfolio_heat']:.2%}")
        
        logger.info(f"\nRisk Metrics:")
        logger.info(f"  Approvals: {summary['trades']}")
        logger.info(f"  Approval rate: {summary['approval_rate']:.1%}")
        logger.info(f"  Consecutive losses triggered: {summary['consecutive_losses']}")
        
        if summary['rejection_breakdown']:
            logger.info(f"\nRejection Breakdown:")
            for reason, count in summary['rejection_breakdown'].items():
                logger.info(f"  {reason}: {count}")
        
        logger.info("=" * 100)


def run_risk_governed_backtest(
    symbols: List[str],
    enforce_risk: bool = True
) -> List[Trade]:
    """
    Run backtest with risk governance.
    
    Args:
        symbols: List of stock tickers
        enforce_risk: If True, apply risk limits
    
    Returns:
        List of Trade objects
    """
    backtest = RiskGovernedBacktest(symbols, enforce_risk=enforce_risk)
    trades = backtest.run()
    backtest.log_summary()
    return trades
