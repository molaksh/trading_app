"""
Phase G Demo: Execution Realism

Shows how execution realism affects backtesting results.
Compares idealized fills vs realistic fills with:
- Slippage costs
- Liquidity constraints
- Next-open entry timing
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

from config.settings import (
    STARTING_CAPITAL,
    HOLD_DAYS,
    BACKTEST_LOOKBACK_YEARS,
    BACKTEST_MIN_CONFIDENCE,
    LOOKBACK_DAYS,
    ENTRY_SLIPPAGE_BPS,
    EXIT_SLIPPAGE_BPS,
    MAX_POSITION_ADV_PCT,
    USE_NEXT_OPEN_ENTRY,
)
from data.price_loader import load_price_data
from features.feature_engine import compute_features
from scoring.rule_scorer import score_symbol
from backtest.simple_backtest import Trade
from execution.execution_model import (
    ExecutionModel,
    compute_entry_price,
    compute_exit_price,
    compute_slippage_cost,
)

logger = logging.getLogger(__name__)


class ExecutionRealisticBacktest:
    """
    Backtest with realistic execution.
    
    Compares idealized vs realistic fills side-by-side.
    """
    
    def __init__(self, symbols: List[str], use_realistic: bool = True):
        """
        Initialize execution-realistic backtest.
        
        Args:
            symbols: List of stock tickers
            use_realistic: If True, apply execution realism; if False, idealized
        """
        self.symbols = symbols
        self.use_realistic = use_realistic
        self.execution_model = ExecutionModel() if use_realistic else None
        
        # Results
        self.trades_idealized: List[Trade] = []
        self.trades_realistic: List[Trade] = []
        self.execution_stats: List[Dict] = []
        self.rejected_trades: List[Dict] = []
        
        logger.info("=" * 100)
        logger.info(f"Execution Realistic Backtest ({BACKTEST_LOOKBACK_YEARS}Y, hold {HOLD_DAYS}D)")
        if use_realistic:
            logger.info("MODE: REALISTIC")
            logger.info(f"  Entry slippage: {ENTRY_SLIPPAGE_BPS} bps")
            logger.info(f"  Exit slippage: {EXIT_SLIPPAGE_BPS} bps")
            logger.info(f"  Max position: {MAX_POSITION_ADV_PCT:.1%} of ADV")
            logger.info(f"  Entry timing: {'Next open' if USE_NEXT_OPEN_ENTRY else 'Same day close'}")
        else:
            logger.info("MODE: IDEALIZED (no slippage or liquidity checks)")
        logger.info("=" * 100)
    
    def run(self) -> Tuple[List[Trade], List[Trade]]:
        """
        Run backtest comparing idealized vs realistic.
        
        Returns:
            Tuple of (trades_idealized, trades_realistic)
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * BACKTEST_LOOKBACK_YEARS)
        
        for symbol in self.symbols:
            logger.info(f"\nProcessing {symbol}...")
            
            # Load price data
            full_df = load_price_data(symbol, BACKTEST_LOOKBACK_YEARS * 252)
            if full_df is None or len(full_df) < 252:
                logger.warning(f"Insufficient data for {symbol}")
                continue
            
            # Compute features for entire history
            featured_df = compute_features(full_df)
            if featured_df is None or len(featured_df) < LOOKBACK_DAYS + HOLD_DAYS:
                logger.warning(f"Insufficient featured data for {symbol}")
                continue
            
            # Generate signals and backtest
            self._backtest_symbol(symbol, featured_df, full_df)
        
        return self.trades_idealized, self.trades_realistic
    
    def _backtest_symbol(self, symbol: str, featured_df: pd.DataFrame, full_df: pd.DataFrame):
        """Backtest a single symbol."""
        positions_held: Dict[str, Dict] = {}  # symbol -> {entry_date, entry_price, ...}
        
        for i in range(LOOKBACK_DAYS, len(featured_df) - HOLD_DAYS):
            signal_date = featured_df.index[i]
            
            # Check if we should exit existing positions
            exit_candidates = [
                (pos_key, pos_info) for pos_key, pos_info in positions_held.items()
                if (signal_date - pos_info["entry_date"]).days >= HOLD_DAYS
            ]
            
            for pos_key, pos_info in exit_candidates:
                # Get exit price
                try:
                    exit_idx = full_df.index.get_loc(signal_date)
                    if exit_idx >= len(full_df):
                        continue
                    
                    # Idealized exit
                    exit_close = full_df.iloc[exit_idx]["Close"]
                    trade_idealized = Trade(
                        symbol=symbol,
                        entry_date=pos_info["entry_date"],
                        entry_price=pos_info["entry_price_idealized"],
                        exit_date=signal_date,
                        exit_price=exit_close,
                        confidence=pos_info["confidence"],
                    )
                    self.trades_idealized.append(trade_idealized)
                    
                    # Realistic exit (if enabled)
                    if self.use_realistic:
                        exit_price_realistic = compute_exit_price(
                            signal_date, full_df, USE_NEXT_OPEN_ENTRY
                        )
                        if exit_price_realistic is not None:
                            trade_realistic = Trade(
                                symbol=symbol,
                                entry_date=pos_info["entry_date"],
                                entry_price=pos_info["entry_price_realistic"],
                                exit_date=signal_date,
                                exit_price=exit_price_realistic,
                                confidence=pos_info["confidence"],
                            )
                            self.trades_realistic.append(trade_realistic)
                            
                            # Track slippage
                            slippage = compute_slippage_cost(
                                pos_info["entry_price_idealized"],
                                exit_close,
                                pos_info["entry_price_realistic"],
                                exit_price_realistic,
                                pos_info["position_size"],
                            )
                            
                            self.execution_stats.append({
                                "symbol": symbol,
                                "entry_date": pos_info["entry_date"],
                                "exit_date": signal_date,
                                "pnl_idealized": trade_idealized.return_pct * 100,
                                "pnl_realistic": trade_realistic.return_pct * 100,
                                **slippage,
                            })
                    
                    del positions_held[pos_key]
                
                except Exception as e:
                    logger.warning(f"Error exiting {symbol}: {e}")
                    continue
            
            # Check for entry signal
            try:
                row = featured_df.iloc[i]
                confidence = row.get("confidence_score", 0)
                
                if confidence < BACKTEST_MIN_CONFIDENCE:
                    continue
                
                # Check if already holding
                if symbol in positions_held:
                    continue
                
                # Get entry prices
                entry_price_idealized = row["Close"]
                
                entry_price_realistic = None
                if self.use_realistic:
                    entry_price_realistic = compute_entry_price(
                        signal_date, full_df, USE_NEXT_OPEN_ENTRY
                    )
                    if entry_price_realistic is None:
                        self.rejected_trades.append({
                            "symbol": symbol,
                            "date": signal_date,
                            "reason": "No next day data for entry",
                        })
                        continue
                
                # Check liquidity (if realistic mode)
                if self.use_realistic:
                    avg_volume = full_df.iloc[i:i+20]["Volume"].mean()
                    avg_price = full_df.iloc[i:i+20]["Close"].mean()
                    adv = avg_volume * avg_price
                    
                    # Position size: $10k position
                    position_notional = 10_000
                    
                    passed, reason = self.execution_model.check_liquidity_for_position(
                        position_notional, adv
                    )
                    
                    if not passed:
                        self.rejected_trades.append({
                            "symbol": symbol,
                            "date": signal_date,
                            "reason": reason or "Liquidity check failed",
                        })
                        continue
                
                # Record position
                position_size = 10_000 / entry_price_idealized
                positions_held[symbol] = {
                    "entry_date": signal_date,
                    "entry_price_idealized": entry_price_idealized,
                    "entry_price_realistic": entry_price_realistic,
                    "position_size": position_size,
                    "confidence": confidence,
                }
            
            except Exception as e:
                logger.warning(f"Error entering {symbol}: {e}")
                continue
    
    def get_summary(self) -> Dict:
        """Get comprehensive backtest summary."""
        if not self.trades_idealized:
            return {"error": "No trades generated"}
        
        # Calculate returns
        idealized_returns = [t.return_pct for t in self.trades_idealized]
        realistic_returns = [t.return_pct for t in self.trades_realistic] if self.use_realistic else []
        
        # Calculate statistics
        def calc_stats(returns):
            if not returns:
                return {
                    "total_return": 0.0,
                    "avg_return": 0.0,
                    "win_rate": 0.0,
                    "max_gain": 0.0,
                    "max_loss": 0.0,
                }
            
            returns = list(returns)
            winners = [r for r in returns if r > 0]
            losers = [r for r in returns if r <= 0]
            
            return {
                "total_return": sum(returns),
                "avg_return": sum(returns) / len(returns),
                "win_rate": len(winners) / len(returns) if returns else 0,
                "max_gain": max(returns),
                "max_loss": min(returns),
                "num_trades": len(returns),
            }
        
        stats_idealized = calc_stats(idealized_returns)
        stats_realistic = calc_stats(realistic_returns)
        
        # Calculate total slippage
        total_slippage = 0.0
        if self.execution_stats:
            total_slippage = sum(s["total_slippage_cost"] for s in self.execution_stats)
        
        return {
            "idealized": stats_idealized,
            "realistic": stats_realistic,
            "execution": {
                "total_slippage_cost": total_slippage,
                "trades_rejected_liquidity": len(self.rejected_trades),
                "avg_slippage_per_trade": (
                    total_slippage / len(self.execution_stats)
                    if self.execution_stats else 0.0
                ),
            },
            "impact": {
                "return_difference": (
                    stats_realistic.get("total_return", 0.0) - 
                    stats_idealized.get("total_return", 0.0)
                ),
                "win_rate_difference": (
                    stats_realistic.get("win_rate", 0.0) - 
                    stats_idealized.get("win_rate", 0.0)
                ),
            },
        }
    
    def print_summary(self):
        """Print formatted summary."""
        summary = self.get_summary()
        
        print("\n" + "=" * 100)
        print("EXECUTION REALISM IMPACT ANALYSIS")
        print("=" * 100)
        
        if "error" in summary:
            print(f"Error: {summary['error']}")
            return
        
        ideal = summary["idealized"]
        real = summary["realistic"]
        exec_stats = summary["execution"]
        impact = summary["impact"]
        
        print("\nIDEALIZED (No Slippage):")
        print(f"  Trades:           {ideal['num_trades']}")
        print(f"  Total Return:     {ideal['total_return']:+.2%}")
        print(f"  Avg Return:       {ideal['avg_return']:+.3%}")
        print(f"  Win Rate:         {ideal['win_rate']:.1%}")
        print(f"  Max Gain:         {ideal['max_gain']:+.2%}")
        print(f"  Max Loss:         {ideal['max_loss']:+.2%}")
        
        if self.use_realistic:
            print("\nREALISTIC (With Slippage & Liquidity):")
            print(f"  Trades:           {real['num_trades']}")
            print(f"  Total Return:     {real['total_return']:+.2%}")
            print(f"  Avg Return:       {real['avg_return']:+.3%}")
            print(f"  Win Rate:         {real['win_rate']:.1%}")
            print(f"  Max Gain:         {real['max_gain']:+.2%}")
            print(f"  Max Loss:         {real['max_loss']:+.2%}")
            
            print("\nEXECUTION COSTS:")
            print(f"  Total Slippage:             ${exec_stats['total_slippage_cost']:,.0f}")
            print(f"  Avg Slippage per Trade:     ${exec_stats['avg_slippage_per_trade']:,.0f}")
            print(f"  Trades Rejected (Liquidity):{exec_stats['trades_rejected_liquidity']}")
            
            print("\nIMPACT vs IDEALIZED:")
            print(f"  Return Difference:          {impact['return_difference']:+.2%}")
            print(f"  Win Rate Difference:        {impact['win_rate_difference']:+.1%}")
        
        print("\n" + "=" * 100)


def run_execution_realism_demo():
    """Run execution realism demo."""
    from universe.symbols import SYMBOLS
    
    # Run with small symbol set for demo
    demo_symbols = SYMBOLS[:3] if SYMBOLS else ["AAPL", "MSFT"]
    
    logger.info(f"\nRunning execution realism demo with {len(demo_symbols)} symbols...")
    
    # Idealized backtest
    print("\n" + "=" * 100)
    print("PHASE G: EXECUTION REALISM DEMO")
    print("=" * 100)
    print("\nPart 1: Running idealized backtest...")
    
    backtest_idealized = ExecutionRealisticBacktest(demo_symbols, use_realistic=False)
    backtest_idealized.run()
    
    # Realistic backtest
    print("\nPart 2: Running realistic backtest with execution costs...")
    
    backtest_realistic = ExecutionRealisticBacktest(demo_symbols, use_realistic=True)
    backtest_realistic.run()
    
    # Compare
    print("\nPart 3: Comparing results...")
    backtest_realistic.print_summary()
    
    print("\nKEY INSIGHTS:")
    print("  • Slippage reduces returns on every fill")
    print("  • Liquidity constraints reject high-impact trades")
    print("  • Next-open entry timing is more realistic")
    print("  • Conservative realism improves production performance")
    
    return backtest_idealized, backtest_realistic


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
    )
    
    run_execution_realism_demo()
