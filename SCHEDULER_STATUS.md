# Scheduler Status - All Schedules In Place ✅

**Last Verified:** January 28, 2026  
**Status:** PRODUCTION READY

---

## Quick Summary

✅ **All 8 scheduled tasks are implemented and configured**  
✅ **All intervals are tunable via environment variables**  
✅ **Scheduler runs in continuous container mode**  
✅ **State persists across restarts**  
✅ **Idempotent operations prevent duplicate executions**

---

## Configuration

### Location
- **Settings file:** `config/scheduler_settings.py`
- **Scheduler implementation:** `execution/scheduler.py`
- **Default environment:** Production-safe defaults

### Current Settings (Default Values)

```
MARKET_TIMEZONE = America/New_York          # US Eastern
SCHEDULER_TICK_SECONDS = 60                 # Loop cadence
RECONCILIATION_INTERVAL_MINUTES = 60        # Full state check
EMERGENCY_EXIT_INTERVAL_MINUTES = 20        # Emergency exits (intraday)
ORDER_POLL_INTERVAL_MINUTES = 3             # Poll pending orders
HEALTH_CHECK_INTERVAL_MINUTES = 60          # Account status
ENTRY_WINDOW_MINUTES_BEFORE_CLOSE = 25      # Entry signal generation window
SWING_EXIT_DELAY_MINUTES_AFTER_CLOSE = 10   # Post-close delay before swing exits
RUN_STARTUP_RECONCILIATION = true           # Verify state on startup
RUN_HEALTH_CHECK_ON_BOOT = true             # Check account on startup
```

All settings are **100% environment-driven** - can be overridden at container startup:
```bash
docker run -e RECONCILIATION_INTERVAL_MINUTES=30 -e EMERGENCY_EXIT_INTERVAL_MINUTES=15 ...
```

---

## Scheduled Tasks (8 Total)

### 1. ✅ Continuous Reconciliation
- **Task:** `_run_reconciliation()`
- **Purpose:** Verify positions, orders, account state consistency
- **Interval:** Every **60 minutes** (configurable)
- **Runs:** During all market hours
- **Idempotent:** Yes (tracks last run time)

### 2. ✅ Exit Intent Execution
- **Task:** `_run_exit_intent_execution()`
- **Purpose:** Execute pending exit intents during market hours
- **Timing:** Post-market-open execution window (configurable start/end minutes)
- **Frequency:** Once per trading day
- **Idempotent:** Yes (tracks by date)
- **Requirements:** SWING_EXIT_TWO_PHASE_ENABLED must be true

### 3. ✅ Emergency Exit Monitoring
- **Task:** `_run_monitoring_cycle()`
- **Purpose:** Check for emergency exit conditions, forced liquidations
- **Interval:** Every **20 minutes** during market hours (configurable)
- **Runs:** Only while market is open
- **Idempotent:** Yes (tracks last run time)

### 4. ✅ Order Polling
- **Task:** `_run_monitoring_cycle()` (reused for polling)
- **Purpose:** Poll fill status for pending orders
- **Condition:** Only runs if pending orders exist
- **Interval:** Every **3 minutes** (configurable)
- **Runs:** During market hours
- **Idempotent:** Yes (tracks last poll time)

### 5. ✅ Entry Signal Generation
- **Task:** `_run_entry_cycle()`
- **Purpose:** Generate swing entry signals near market close
- **Timing:** **25 minutes before market close** to market close (configurable)
- **Frequency:** Once per trading day
- **Runs:** During market hours
- **Idempotent:** Yes (tracks by date)
- **Uses:** SwingEquityStrategy container with 5 philosophies

### 6. ✅ Swing Exit Evaluation
- **Task:** `_run_swing_exit_cycle()`
- **Purpose:** Evaluate exit conditions for swing positions
- **Timing:** After market close + **10 minutes delay** (configurable)
- **Frequency:** Once per trading session
- **Runs:** Post-market hours
- **Idempotent:** Yes (tracks by date)

### 7. ✅ Offline ML Training
- **Task:** `_run_offline_ml_cycle()`
- **Purpose:** Train ML models on accumulated trade data (optional)
- **Timing:** After market close
- **Frequency:** Once per day
- **Idempotent:** Yes (fingerprints dataset, skips if unchanged)
- **Requirements:** ML orchestrator available
- **Behavior:** Gracefully degrades if not configured

### 8. ✅ Health Check
- **Task:** `_run_health_check()`
- **Purpose:** Monitor account equity, buying power, positions, orders
- **Interval:** Every **60 minutes** (configurable)
- **Runs:** Continuous (all times)
- **Idempotent:** Yes (logs only, no side effects)

---

## Scheduler Main Loop

Located in `execution/scheduler.py:run_forever()`

```python
while True:
    # Every SCHEDULER_TICK_SECONDS (default 60s)
    now = get_current_time()
    clock = get_market_clock()  # With retry + caching
    
    # Task 1: Always reconcile
    run_reconciliation()
    
    if market_is_open:
        # Task 2: Execute pending exit intents (execution window)
        run_exit_intent_execution()
        
        # Task 3: Monitor emergencies every N minutes
        if should_run("monitor", EMERGENCY_EXIT_INTERVAL_MINUTES):
            run_monitoring_cycle()
        
        # Task 4: Poll pending orders if any exist
        if has_pending_orders and should_run("poll", ORDER_POLL_INTERVAL_MINUTES):
            run_monitoring_cycle()
        
        # Task 5: Entry signals in final N minutes before close
        if time_to_close <= ENTRY_WINDOW_MINUTES_BEFORE_CLOSE:
            if not already_ran_today:
                run_entry_cycle()
    
    else:  # After hours
        # Task 6: Swing exits with post-close delay
        if not already_ran_today and past_delay_window:
            run_swing_exit_cycle()
        
        # Task 7: Offline ML training
        if not already_ran_today:
            run_offline_ml_cycle()
    
    # Task 8: Health check (always)
    run_health_check()
    
    sleep(SCHEDULER_TICK_SECONDS)
```

---

## State Persistence

### State File
- **Location:** `{BASE_DIR}/state/scheduler_state.json`
- **Format:** JSON with ISO timestamps
- **Purpose:** Track last run time for each task
- **Loaded at:** Scheduler startup
- **Updated:** After each task completes
- **Idempotency:** Prevents duplicate executions even if scheduler restarts

### Example State
```json
{
  "reconciliation": "2026-01-28T16:42:00-05:00",
  "monitor": "2026-01-28T16:41:00-05:00",
  "entry": "2026-01-28T16:55:00-05:00",
  "swing_exit": "2026-01-28T17:10:00-05:00",
  "offline_ml": "2026-01-28T17:15:00-05:00",
  "health_check": "2026-01-28T16:43:00-05:00"
}
```

---

## Market Clock Integration

### Clock Source
- **Primary:** Alpaca `get_clock()` API
- **Fallback:** Cached clock (if API fails)
- **Safety:** Forces `is_open=false` if repeated failures

### Retry Logic
- **Max retries:** 3 with exponential backoff
- **Fallback behavior:** Uses cached data for up to 5 failures
- **Failure threshold:** After 5 consecutive failures, returns safe defaults

### Clock Data
```python
clock = {
    "is_open": bool,              # Market open/closed
    "timestamp": datetime,        # Current market time
    "next_open": datetime,        # Next market open
    "next_close": datetime,       # Next market close
}
```

---

## Startup Sequence

1. **Phase 0 Validation**
   - Validates configuration
   - Checks dependencies
   - Loads scope (market, mode, broker)

2. **ML Model Loading** (if available)
   - Loads active ML model version
   - Degrades gracefully if unavailable
   - Does NOT train on startup

3. **Startup Tasks** (if enabled)
   - Run reconciliation (default: true)
   - Run health check (default: true)
   - These verify state before continuous loop starts

4. **Continuous Loop**
   - Starts `run_forever()` which never returns
   - Runs all 8 scheduled tasks continuously

---

## Environment Variables (Tuning)

### Override Any Setting at Container Runtime

```bash
# Base command with .env file for credentials
docker run -d \
  --name paper-alpaca-swing-us \
  --env-file ./.env \
  -e MARKET=us \
  -e APP_ENV=paper \
  -e RECONCILIATION_INTERVAL_MINUTES=30 \
  -e EMERGENCY_EXIT_INTERVAL_MINUTES=15 \
  -e ORDER_POLL_INTERVAL_MINUTES=2 \
  -e ENTRY_WINDOW_MINUTES_BEFORE_CLOSE=30 \
  -e SCHEDULER_TICK_SECONDS=30 \
  -e RUN_STARTUP_RECONCILIATION=true \
  -e RUN_HEALTH_CHECK_ON_BOOT=true \
  -e MARKET_TIMEZONE="America/Chicago" \
  -v $(pwd)/logs:/app/logs \
  trading-app:latest \
  python main.py --schedule
```

**All settings are optional** - defaults apply if not specified. Only provide `--env-file ./.env` once for credentials.

---

## Failure Handling

### Market Clock Failures
- ✅ Automatic retry with exponential backoff
- ✅ Fallback to cached clock data
- ✅ Safety default: assume market is closed

### Task Failures
- ✅ Exceptions caught and logged
- ✅ Scheduler continues running
- ✅ Next interval will retry automatically

### API Failures
- ✅ Retry logic in broker adapter
- ✅ Graceful degradation
- ✅ Logged for monitoring

---

## Production Checklist

- ✅ All 8 tasks implemented
- ✅ All intervals configurable
- ✅ State persists across restarts
- ✅ Idempotent operations prevent duplicates
- ✅ Market clock with retry logic
- ✅ Failure handling graceful
- ✅ Environment-driven configuration
- ✅ Startup validation (Phase 0)
- ✅ Health checks built-in
- ✅ ML training optional and graceful

---

## Running the Scheduler

### Docker Container
```bash
# Run scheduler continuously (credentials from .env file)
docker run -d \
  --name paper-alpaca-swing-us \
  --env-file ./.env \
  -e MARKET=us \
  -e APP_ENV=paper \
  -e BASE_DIR=/app/logs \
  -e PYTHONUNBUFFERED=1 \
  -v $(pwd)/logs:/app/logs \
  trading-app:latest \
  python main.py --schedule
```

**Note:** Alpaca credentials are loaded from `.env` file:
```dotenv
APCA_API_BASE_URL=https://paper-api.alpaca.markets
APCA_API_KEY_ID=your_key_here
APCA_API_SECRET_KEY=your_secret_here
```

### Local Development
```bash
python main.py --schedule
```

### Logs Location
```
logs/us/paper/scheduler.log    # Main logs
logs/us/paper/trades.jsonl     # Trade execution logs
```

---

## Monitoring Scheduled Tasks

### View Live Logs
```bash
docker logs -f trading-scheduler
```

### Check State File
```bash
cat logs/us/paper/state/scheduler_state.json
```

### Common Log Patterns
```
Reconciliation status=ok safe_mode=false positions=2 orders=1
Health check | equity=$24500.00 buying_power=$20000.00 open_positions=2 pending_orders=1
Entry window reached. Running trade cycle once for today.
Executed 3 pending exit intents
Offline ML training cycle...
Market clock recovered after 2 failures
```

---

## Summary

**✅ Status: PRODUCTION READY**

All 8 scheduled tasks are in place:
1. Continuous reconciliation
2. Exit intent execution
3. Emergency exit monitoring
4. Order polling
5. Entry signal generation
6. Swing exit evaluation
7. Offline ML training
8. Health monitoring

All intervals are tunable via environment variables. State persists across restarts. Scheduler is designed for long-running container mode with automatic recovery from failures.
