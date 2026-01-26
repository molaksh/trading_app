"""
Demo script for exit logic in swing trading system.

Shows:
1. Swing exit evaluation (EOD)
2. Emergency exit evaluation (intraday)
3. Exit execution
4. Audit logging

This demonstrates the strict separation between:
- Swing exits (normal strategy, EOD only)
- Emergency exits (capital protection, intraday allowed)
"""

import logging
from datetime import datetime, date, timedelta
import pandas as pd

from strategy.exit_evaluator import (
    ExitEvaluator,
    SwingExitEvaluator,
    EmergencyExitEvaluator,
    ExitType,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def demo_swing_exits():
    """Demonstrate swing exit evaluation (EOD only)."""
    logger.info("\n" + "=" * 80)
    logger.info("SWING EXIT EVALUATION (EOD)")
    logger.info("=" * 80)
    
    swing_eval = SwingExitEvaluator(
        max_holding_days=20,
        profit_target_pct=0.10,
        use_trend_invalidation=True,
    )
    
    # Test case 1: Max holding period
    logger.info("\n📊 Test Case 1: Max Holding Period")
    entry_date = date.today() - timedelta(days=21)
    exit_signal = swing_eval.evaluate(
        symbol="AAPL",
        entry_date=entry_date,
        entry_price=150.0,
        current_price=155.0,
        confidence=4,
        evaluation_date=date.today(),
    )
    
    if exit_signal:
        logger.info(f"✓ Exit Signal: {exit_signal.exit_type.value}")
        logger.info(f"  Reason: {exit_signal.reason}")
        logger.info(f"  Holding Days: {exit_signal.holding_days}")
        logger.info(f"  Urgency: {exit_signal.urgency}")
    else:
        logger.info("✗ No exit signal")
    
    # Test case 2: Profit target
    logger.info("\n📊 Test Case 2: Profit Target Reached")
    entry_date = date.today() - timedelta(days=10)
    exit_signal = swing_eval.evaluate(
        symbol="TSLA",
        entry_date=entry_date,
        entry_price=200.0,
        current_price=225.0,  # +12.5% (exceeds 10% target)
        confidence=3,
        evaluation_date=date.today(),
    )
    
    if exit_signal:
        logger.info(f"✓ Exit Signal: {exit_signal.exit_type.value}")
        logger.info(f"  Reason: {exit_signal.reason}")
        logger.info(f"  Holding Days: {exit_signal.holding_days}")
        logger.info(f"  Urgency: {exit_signal.urgency}")
    else:
        logger.info("✗ No exit signal")
    
    # Test case 3: Trend invalidation
    logger.info("\n📊 Test Case 3: Trend Invalidation")
    entry_date = date.today() - timedelta(days=5)
    eod_data = pd.Series({
        'Close': 148.0,
        'SMA_200': 150.0,  # Close below SMA200
    })
    exit_signal = swing_eval.evaluate(
        symbol="MSFT",
        entry_date=entry_date,
        entry_price=145.0,
        current_price=148.0,
        confidence=4,
        eod_data=eod_data,
        evaluation_date=date.today(),
    )
    
    if exit_signal:
        logger.info(f"✓ Exit Signal: {exit_signal.exit_type.value}")
        logger.info(f"  Reason: {exit_signal.reason}")
        logger.info(f"  Holding Days: {exit_signal.holding_days}")
        logger.info(f"  Urgency: {exit_signal.urgency}")
    else:
        logger.info("✗ No exit signal")
    
    # Test case 4: No exit (normal holding)
    logger.info("\n📊 Test Case 4: Normal Holding (No Exit)")
    entry_date = date.today() - timedelta(days=5)
    exit_signal = swing_eval.evaluate(
        symbol="GOOGL",
        entry_date=entry_date,
        entry_price=100.0,
        current_price=103.0,  # +3% (below target)
        confidence=4,
        evaluation_date=date.today(),
    )
    
    if exit_signal:
        logger.info(f"✓ Exit Signal: {exit_signal.exit_type.value}")
    else:
        logger.info("✗ No exit signal (continue holding)")


def demo_emergency_exits():
    """Demonstrate emergency exit evaluation (intraday)."""
    logger.info("\n" + "=" * 80)
    logger.info("EMERGENCY EXIT EVALUATION (INTRADAY)")
    logger.info("=" * 80)
    
    emergency_eval = EmergencyExitEvaluator(
        max_position_loss_pct=0.03,  # 3% of portfolio
        atr_multiplier=4.0,
        enable_volatility_check=True,
    )
    
    portfolio_equity = 100000.0
    
    # Test case 1: Catastrophic loss
    logger.info("\n🚨 Test Case 1: Catastrophic Loss")
    entry_date = date.today() - timedelta(days=3)
    exit_signal = emergency_eval.evaluate(
        symbol="NVDA",
        entry_date=entry_date,
        entry_price=200.0,
        current_price=170.0,  # -15% on position
        position_size=100,    # $20k position, $3k loss = 3% of portfolio
        portfolio_equity=portfolio_equity,
        confidence=4,
        evaluation_date=date.today(),
    )
    
    if exit_signal:
        logger.info(f"✓ Emergency Exit: {exit_signal.exit_type.value}")
        logger.info(f"  Reason: {exit_signal.reason}")
        logger.info(f"  Holding Days: {exit_signal.holding_days}")
        logger.info(f"  Urgency: {exit_signal.urgency}")
    else:
        logger.info("✗ No emergency exit")
    
    # Test case 2: Extreme ATR move
    logger.info("\n🚨 Test Case 2: Extreme ATR Move")
    entry_date = date.today() - timedelta(days=2)
    exit_signal = emergency_eval.evaluate(
        symbol="AMD",
        entry_date=entry_date,
        entry_price=150.0,
        current_price=135.0,  # -$15 move
        position_size=50,
        portfolio_equity=portfolio_equity,
        confidence=3,
        atr=3.0,  # ATR = $3, 4×ATR = $12 threshold
        evaluation_date=date.today(),
    )
    
    if exit_signal:
        logger.info(f"✓ Emergency Exit: {exit_signal.exit_type.value}")
        logger.info(f"  Reason: {exit_signal.reason}")
        logger.info(f"  Holding Days: {exit_signal.holding_days}")
        logger.info(f"  Urgency: {exit_signal.urgency}")
    else:
        logger.info("✗ No emergency exit")
    
    # Test case 3: Same-day protection (catastrophic only)
    logger.info("\n🚨 Test Case 3: Same-Day Entry (No Exit Unless Catastrophic)")
    entry_date = date.today()  # Entered today
    exit_signal = emergency_eval.evaluate(
        symbol="META",
        entry_date=entry_date,
        entry_price=300.0,
        current_price=285.0,  # -5% (not catastrophic)
        position_size=20,
        portfolio_equity=portfolio_equity,
        confidence=4,
        evaluation_date=date.today(),
    )
    
    if exit_signal:
        logger.info(f"✓ Emergency Exit: {exit_signal.exit_type.value}")
    else:
        logger.info("✗ No same-day exit (not catastrophic)")
    
    # Test case 4: Normal loss (no emergency)
    logger.info("\n🚨 Test Case 4: Normal Loss (No Emergency)")
    entry_date = date.today() - timedelta(days=5)
    exit_signal = emergency_eval.evaluate(
        symbol="AAPL",
        entry_date=entry_date,
        entry_price=150.0,
        current_price=147.0,  # -2% (normal)
        position_size=100,
        portfolio_equity=portfolio_equity,
        confidence=4,
        evaluation_date=date.today(),
    )
    
    if exit_signal:
        logger.info(f"✓ Emergency Exit: {exit_signal.exit_type.value}")
    else:
        logger.info("✗ No emergency exit (normal volatility)")


def demo_exit_logging():
    """Demonstrate exit signal logging and audit trail."""
    logger.info("\n" + "=" * 80)
    logger.info("EXIT SIGNAL LOGGING & AUDIT TRAIL")
    logger.info("=" * 80)
    
    evaluator = ExitEvaluator()
    
    # Generate swing exit signal
    entry_date = date.today() - timedelta(days=15)
    swing_signal = evaluator.evaluate_eod(
        symbol="SPY",
        entry_date=entry_date,
        entry_price=400.0,
        current_price=445.0,  # +11.25% (profit target)
        confidence=5,
        evaluation_date=date.today(),
    )
    
    if swing_signal:
        logger.info("\n📝 Swing Exit Signal:")
        signal_dict = swing_signal.to_dict()
        for key, value in signal_dict.items():
            logger.info(f"  {key}: {value}")
    
    # Generate emergency exit signal
    emergency_signal = evaluator.evaluate_emergency(
        symbol="QQQ",
        entry_date=date.today() - timedelta(days=3),
        entry_price=350.0,
        current_price=320.0,  # Catastrophic loss
        position_size=100,
        portfolio_equity=100000.0,
        confidence=4,
        atr=5.0,
        evaluation_date=date.today(),
    )
    
    if emergency_signal:
        logger.info("\n📝 Emergency Exit Signal:")
        signal_dict = emergency_signal.to_dict()
        for key, value in signal_dict.items():
            logger.info(f"  {key}: {value}")


def demo_design_principles():
    """Document design principles and constraints."""
    logger.info("\n" + "=" * 80)
    logger.info("EXIT LOGIC DESIGN PRINCIPLES")
    logger.info("=" * 80)
    
    principles = """
1. SWING TRADING SYSTEM
   - NOT a day trading system
   - Entries allowed intraday
   - Normal exits MUST NOT trigger intraday
   
2. LAYER 1: SWING EXITS (Primary)
   - Evaluated on EOD data only
   - Executed at next market open
   - Never same-day entry and exit
   - Examples: trend invalidation, max holding days, profit target
   - Classification: SWING_EXIT
   
3. LAYER 2: EMERGENCY EXITS (Secondary)
   - Evaluated continuously during market hours
   - Purpose: capital preservation, NOT profit optimization
   - May exit intraday if triggered
   - Should be RARE (hard thresholds)
   - Examples: catastrophic loss, extreme ATR move
   - Classification: EMERGENCY_EXIT
   
4. AUDIT TRAIL
   - Every exit logged with:
     * exit_type (SWING_EXIT or EMERGENCY_EXIT)
     * reason (human-readable)
     * timestamp
     * symbol
     * entry_date
     * holding_days
   - Emergency exits distinguishable in analytics
   
5. MODULARITY
   - Swing logic independent of emergency logic
   - Clear function boundaries
   - Strategy stats treat exits separately
"""
    
    logger.info(principles)


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("EXIT LOGIC DEMONSTRATION")
    logger.info("Swing Trading System: EOD Strategy + Emergency Protection")
    logger.info("=" * 80)
    
    demo_design_principles()
    demo_swing_exits()
    demo_emergency_exits()
    demo_exit_logging()
    
    logger.info("\n" + "=" * 80)
    logger.info("✓ EXIT LOGIC DEMONSTRATION COMPLETE")
    logger.info("=" * 80)
