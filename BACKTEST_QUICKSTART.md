"""
BACKTEST MODULE - QUICK START GUIDE
"""

# ============================================================================
# QUICK START - BACKTEST MODULE
# ============================================================================

# ENABLE BACKTEST IN MAIN.PY
# ========================
# File: main.py
# Line ~22: Change
#   RUN_BACKTEST = False
# To:
#   RUN_BACKTEST = True
# 
# Then run:
#   python3 main.py
#
# Output will include:
#   1. Standard screener results
#   2. Backtest results table by confidence level

# CONFIGURE BACKTEST PARAMETERS
# =============================
# File: config/settings.py
# Lines 47-51:
#   BACKTEST_LOOKBACK_YEARS = 5      # Years of history
#   HOLD_DAYS = 5                    # Days to hold positions
#   BACKTEST_MIN_CONFIDENCE = 3      # Min confidence to enter
#
# Example: Test last 10 years with 3-day hold:
#   BACKTEST_LOOKBACK_YEARS = 10
#   HOLD_DAYS = 3
#   BACKTEST_MIN_CONFIDENCE = 3

# RUN DEMO (NO NETWORK)
# ====================
# Command:
#   python3 demo_backtest.py
#
# Output:
#   Confidence | Trades | WinRate | AvgReturn | MedianReturn
#   5          | 50     | 92%     | 2.17%     | 2.10%
#   4          | 100    | 66%     | 1.01%     | 0.87%
#   3          | 100    | 53%     | -0.00%    | 0.15%

# USE IN CUSTOM CODE
# ==================
# from backtest.simple_backtest import run_backtest
# from backtest.metrics import print_metrics
# from universe.symbols import SYMBOLS
#
# trades = run_backtest(SYMBOLS)
# print_metrics(trades)

# KEY PARAMETERS EXPLAINED
# ========================
# Trade Count
#   How many trades triggered at this confidence level
#   Higher count = more opportunities
#
# Win Rate
#   % of trades that made money
#   Target: Higher confidence should have higher win rate
#
# Avg Return
#   Average profit/loss per trade
#   Target: Higher confidence should have positive average
#
# Median Return
#   Middle return (50th percentile)
#   Less sensitive to outliers than average
#
# Max Loss
#   Worst single loss at this confidence level
#   Shows downside risk

# ENTRY CONDITIONS
# ================
# - Only when score >= BACKTEST_MIN_CONFIDENCE
# - Entry price = next day open (or close if unavailable)
# - One position per symbol (no overlapping)
#
# EXIT CONDITIONS
# ===============
# - After HOLD_DAYS have passed since entry
# - Exit price = open on exit date (or close if unavailable)
# - Automatic, no discretion

# DATA & DATES
# ============
# - Backtests BACKTEST_LOOKBACK_YEARS of history
# - No lookahead bias (uses data up to signal date only)
# - Handles missing data gracefully
# - Dates based on actual market trading days

# VALIDATION CHECKLIST
# ====================
# ✓ Does win rate increase with confidence? (should be yes)
# ✓ Does average return increase with confidence? (should be yes)
# ✓ Are max losses smaller for higher confidence? (should be yes)
# ✓ Is trade count sufficient for statistical significance?
#   (Ideally >100 trades per confidence level)

# COMMON ISSUES & FIXES
# =====================
# Issue: "ImportError: cannot import name 'Trade'"
# Fix: Make sure you're in the right directory and run from repo root
#
# Issue: No trades generated
# Fix: Check that symbols have BACKTEST_LOOKBACK_YEARS of history
#      Try lowering BACKTEST_MIN_CONFIDENCE to 1
#
# Issue: Empty metrics output
# Fix: Ensure RUN_BACKTEST = True
#      Check BACKTEST_MIN_CONFIDENCE is reasonable (3-5)

# EXAMPLE WORKFLOW
# ================
# 1. Run screener normally:
#    python3 main.py
#
# 2. Review daily results
#
# 3. Set RUN_BACKTEST = True to validate historical performance
#    python3 main.py
#
# 4. Check if higher confidence scores had better returns
#
# 5. If happy, adjust thresholds:
#    - If conf 5 very good: use RUN_BACKTEST = True on prod
#    - If conf 5 bad: review scoring logic
#
# 6. Compare across different HOLD_DAYS:
#    Set HOLD_DAYS = 3, 5, 10 and see which performs best

# FILES
# =====
# backtest/
#   __init__.py           - Package init
#   simple_backtest.py    - Trade simulation
#   metrics.py            - Statistics calculation
#
# demo_backtest.py        - Standalone demo (no network)
# BACKTEST_README.md      - Full documentation
# BACKTEST_IMPLEMENTATION.md - Implementation details

# NEXT STEPS
# ==========
# After validating:
#
# 1. Consider walk-forward testing (out-of-sample)
# 2. Add risk metrics (Sharpe, Sortino, drawdown)
# 3. Implement money management (position sizing)
# 4. Test on different time periods
# 5. Add transaction costs (commissions, slippage)
