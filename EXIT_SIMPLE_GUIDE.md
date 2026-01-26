# Exit Logic - Simple Guide

## How It Works

Your trading system now automatically **sells positions** based on two types of exit signals:

### 1. **Normal Exits** (Swing Trading)
Checked **once per day after market close**. If triggered, sells execute **tomorrow at market open**.

**When it sells:**
- ✅ Held position for 20 days → "Time to exit"
- ✅ Position up 10% or more → "Take profit"  
- ✅ Price broke below key trend (if enabled) → "Trend broken"

**Example:**
```
Today 4 PM: AAPL up 11% after 15 days
Decision: Swing exit signal generated
Tomorrow 9:30 AM: Sell AAPL at market open
```

### 2. **Emergency Exits** (Risk Protection)
Checked **continuously during market hours**. If triggered, sells execute **immediately**.

**When it sells:**
- 🚨 Single position lost 3% of entire portfolio → "Stop the bleeding"
- 🚨 Price dropped 4× more than normal volatility → "Extreme move"

**Example:**
```
10:15 AM: NVDA crashes, position down $3,000 (3% of $100k portfolio)
Decision: Emergency exit triggered
10:16 AM: Sell NVDA immediately at market price
```

## Key Rules

1. **No Day Trading**: Won't sell same day you bought (unless catastrophic loss)
2. **Rare Emergencies**: Emergency exits should almost never happen in normal markets
3. **Complete Logs**: Every exit records WHY it sold and what type it was

## Configuration (in main.py)

```python
exit_evaluator = ExitEvaluator(
    swing_config={
        "max_holding_days": 20,      # Hold max 20 days
        "profit_target_pct": 0.10,   # Sell at +10%
    },
    emergency_config={
        "max_position_loss_pct": 0.03,  # Max 3% portfolio loss per position
        "atr_multiplier": 4.0,          # 4× normal volatility = extreme
    }
)
```

## What Happens When You Run

```
1. Buy signals generated → Orders submitted → Fills confirmed ✅
2. Exit signals evaluated:
   - Emergency check: "Any catastrophic losses?" → No ✅
   - Swing check: "Time to exit any positions?" → No ✅
3. Positions continue holding
```

Later when exits trigger:
```
Day 20: AAPL held max days
  → Swing exit signal logged
  → Sell order submitted to Alpaca
  → Trade log: "SWING_EXIT - Max holding period reached"
```

## Logs

Check [logs/trades_2026-01-26.jsonl](logs/trades_2026-01-26.jsonl) for:

```json
{
  "event": "exit_signal",
  "symbol": "AAPL",
  "exit_type": "SWING_EXIT",
  "reason": "Profit target reached (11.5% >= 10.0%)",
  "holding_days": 16,
  "urgency": "eod"
}
```

```json
{
  "event": "position_closed",
  "symbol": "AAPL",
  "pnl": 1725.0,
  "exit_type": "SWING_EXIT",
  "exit_reason": "Profit target reached"
}
```

## Status

✅ Exit logic implemented and integrated  
✅ Alpaca sell orders execute automatically  
✅ All exits logged with classification  
✅ Currently running: No exits needed (all positions new and within targets)

Your system is now a complete **buy-and-sell** swing trading engine!
