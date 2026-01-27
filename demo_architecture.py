"""
Architecture Integration Example - Multi-strategy, multi-market trading.

This demonstrates how the modular architecture works end-to-end.
"""

import logging
from datetime import datetime, date, timedelta

# Core components
from core.engine import TradingEngine

# Strategies
from strategies.swing import SwingEquityStrategy

# Instruments
from instruments.base import EquityInstrument, OptionInstrument

# Markets
from markets.base import IndiaMarket, USMarket

# Risk components
from risk.trade_intent_guard import TradeIntentGuard, create_account_context

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def demo_india_swing_trading():
    """
    Demo: Swing trading equities in India market.
    
    Setup:
    - Market: NSE (India)
    - Strategy: Swing equity
    - Instrument: Indian stocks
    - Rules: No PDT, but behavioral guard active
    """
    logger.info("\n" + "=" * 80)
    logger.info("DEMO: India Swing Trading")
    logger.info("=" * 80)
    
    # 1. Initialize market
    market = IndiaMarket()
    logger.info(f"Market: {market.market_id} (timezone={market.trading_hours.timezone})")
    
    # 2. Initialize strategy
    swing_strategy = SwingEquityStrategy(
        name="nse_swing",
        config={
            "min_confidence": 4,
            "max_positions": 5,
            "hold_days_min": 2,
            "hold_days_max": 15,  # Shorter for India (more volatile)
        }
    )
    
    # 3. Initialize intent guard
    intent_guard = TradeIntentGuard(allow_manual_override=False)
    
    # 4. Mock broker and risk manager
    class MockBroker:
        def get_account(self):
            return {
                "equity": 500000.0,  # INR 5 lakhs
                "account_type": "MARGIN",
                "day_trade_count_5d": 0,  # India has no PDT
            }
    
    class MockRiskManager:
        pass
    
    broker = MockBroker()
    risk_manager = MockRiskManager()
    
    # 5. Create trading engine
    engine = TradingEngine(
        strategies=[swing_strategy],
        market=market,
        intent_guard=intent_guard,
        risk_manager=risk_manager,
        broker=broker,
    )
    
    # 6. Simulate market data (entry signals)
    market_data = {
        "signals": [
            {"symbol": "RELIANCE", "confidence": 5, "features": {"sma20_slope": 0.05}},
            {"symbol": "TCS", "confidence": 4, "features": {"sma20_slope": 0.03}},
            {"symbol": "INFY", "confidence": 4, "features": {"sma20_slope": 0.02}},
        ],
        "prices": {"RELIANCE": 2500.0, "TCS": 3400.0, "INFY": 1500.0},
    }
    
    portfolio_state = {
        "positions": [],
        "buying_power": 500000.0,
    }
    
    # 7. Run engine
    results = engine.process_strategies(market_data, portfolio_state)
    
    logger.info("\n" + "=" * 80)
    logger.info("Results:")
    logger.info(f"  Entry intents: {results['entry_intents']}")
    logger.info(f"  Approved entries: {results['approved_entries']}")
    logger.info("=" * 80)


def demo_us_multi_strategy():
    """
    Demo: Multiple strategies on US market.
    
    Setup:
    - Market: NYSE (US)
    - Strategy 1: Swing equity (long-only)
    - Strategy 2: Cash-secured put (options)
    - Rules: PDT applies, intent guard active
    """
    logger.info("\n" + "=" * 80)
    logger.info("DEMO: US Multi-Strategy Trading")
    logger.info("=" * 80)
    
    # 1. Initialize market
    market = USMarket()
    logger.info(f"Market: {market.market_id} (timezone={market.trading_hours.timezone})")
    
    # 2. Initialize strategies
    swing_strategy = SwingEquityStrategy(
        name="us_swing",
        config={"min_confidence": 3, "max_positions": 10}
    )
    
    # 3. Initialize intent guard
    intent_guard = TradeIntentGuard(allow_manual_override=False)
    
    # 4. Mock broker (small account with PDT)
    class MockBroker:
        def get_account(self):
            return {
                "equity": 15000.0,  # < $25k, PDT applies
                "account_type": "MARGIN",
                "day_trade_count_5d": 1,  # 1 day trade used
            }
    
    class MockRiskManager:
        pass
    
    broker = MockBroker()
    risk_manager = MockRiskManager()
    
    # 5. Create trading engine
    engine = TradingEngine(
        strategies=[swing_strategy],
        market=market,
        intent_guard=intent_guard,
        risk_manager=risk_manager,
        broker=broker,
    )
    
    # 6. Simulate exit scenario (test PDT guard)
    market_data = {
        "signals": [],
        "prices": {"AAPL": 155.0},
    }
    
    # Position entered today (same-day exit would trigger PDT)
    portfolio_state = {
        "positions": [
            {
                "symbol": "AAPL",
                "strategy": "us_swing",
                "entry_date": date.today(),
                "entry_price": 150.0,
                "quantity": 100,
                "confidence": 4,
            }
        ],
        "buying_power": 5000.0,
    }
    
    # 7. Run engine (will attempt exit)
    # Strategy will generate exit intent (profit target)
    # Intent guard will BLOCK same-day exit
    
    logger.info("\n📊 Testing PDT guard with same-day position...")
    logger.info("Position: AAPL (entered today)")
    logger.info("Current price: $155 (up from $150)")
    logger.info("Expected: Intent guard blocks same-day discretionary exit\n")
    
    results = engine.process_strategies(market_data, portfolio_state)
    
    logger.info("\n" + "=" * 80)
    logger.info("Results:")
    logger.info(f"  Exit intents: {results['exit_intents']}")
    logger.info(f"  Approved exits: {results['approved_exits']}")
    logger.info(f"  Rejected exits: {results['rejected_exits']}")
    logger.info("=" * 80)


def demo_instrument_validation():
    """Demo: Instrument-specific validation."""
    logger.info("\n" + "=" * 80)
    logger.info("DEMO: Instrument Validation")
    logger.info("=" * 80)
    
    # Equity instrument (US)
    equity = EquityInstrument("AAPL", lot_size=1, margin_pct=1.0)
    
    # Validate quantities
    valid, msg = equity.validate_quantity(100)
    logger.info(f"Equity (AAPL) - 100 shares: {valid}")
    
    valid, msg = equity.validate_quantity(0)
    logger.info(f"Equity (AAPL) - 0 shares: {valid} ({msg})")
    
    # Calculate position value
    position_value = equity.calculate_position_value(100, 150.0)
    logger.info(f"Position value: 100 shares @ $150 = ${position_value:,.2f}")
    
    # Calculate margin
    margin_required = equity.calculate_margin_required(100, 150.0)
    logger.info(f"Margin required (cash account): ${margin_required:,.2f}")
    
    # Option instrument
    logger.info("\n" + "-" * 80)
    option = OptionInstrument("AAPL", strike=150.0, expiry="2026-02-21", option_type="call")
    
    # Option contracts
    valid, msg = option.validate_quantity(5)
    logger.info(f"Option (AAPL $150 Call) - 5 contracts: {valid}")
    
    position_value = option.calculate_position_value(5, 3.50)  # $3.50 premium
    logger.info(f"Position value: 5 contracts @ $3.50 = ${position_value:,.2f}")
    
    # Indian equity (lot size = 25)
    logger.info("\n" + "-" * 80)
    indian_equity = EquityInstrument("RELIANCE", lot_size=25, margin_pct=0.5)
    
    valid, msg = indian_equity.validate_quantity(25)
    logger.info(f"Indian equity (RELIANCE) - 25 shares: {valid}")
    
    valid, msg = indian_equity.validate_quantity(30)
    logger.info(f"Indian equity (RELIANCE) - 30 shares: {valid} ({msg})")
    
    logger.info("=" * 80)


def demo_market_hours():
    """Demo: Market hours and status checking."""
    logger.info("\n" + "=" * 80)
    logger.info("DEMO: Market Hours & Status")
    logger.info("=" * 80)
    
    # India market
    india = IndiaMarket()
    india_status = india.get_market_status()
    logger.info(f"NSE (India): {india_status.value}")
    logger.info(f"  Open: {india.is_market_open()}")
    logger.info(f"  Hours: {india.trading_hours.market_open} - {india.trading_hours.market_close} IST")
    
    # US market
    us = USMarket()
    us_status = us.get_market_status()
    logger.info(f"\nNYSE (US): {us_status.value}")
    logger.info(f"  Open: {us.is_market_open()}")
    logger.info(f"  Hours: {us.trading_hours.market_open} - {us.trading_hours.market_close} ET")
    
    # PDT check
    small_margin = {"account_equity": 10000.0, "account_type": "MARGIN"}
    large_margin = {"account_equity": 50000.0, "account_type": "MARGIN"}
    cash_account = {"account_equity": 10000.0, "account_type": "CASH"}
    
    logger.info(f"\nPDT Rules (US):")
    logger.info(f"  $10k margin: {us.requires_pdt_check(small_margin)}")
    logger.info(f"  $50k margin: {us.requires_pdt_check(large_margin)}")
    logger.info(f"  $10k cash: {us.requires_pdt_check(cash_account)}")
    
    logger.info(f"\nPDT Rules (India):")
    logger.info(f"  Any account: {india.requires_pdt_check(small_margin)}")
    
    logger.info("=" * 80)


if __name__ == "__main__":
    # Run all demos
    demo_india_swing_trading()
    demo_us_multi_strategy()
    demo_instrument_validation()
    demo_market_hours()
