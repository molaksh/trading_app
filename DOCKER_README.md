# Docker Deployment Guide

## Quick Start

### 1. Build the Image
```bash
docker-compose build
```

### 2. Create .env File
Create `.env` in the same directory as `docker-compose.yml`:
```bash
# Alpaca API Credentials (Paper Trading)
APCA_API_BASE_URL=https://paper-api.alpaca.markets
APCA_API_KEY_ID=your_key_here
APCA_API_SECRET_KEY=your_secret_here
```

### 3. Start Services
```bash
# Start all services
docker-compose up -d

# Start only swing trader
docker-compose up -d swing-trader

# Start only risk monitor
docker-compose up -d risk-monitor
```

### 4. View Logs
```bash
# Real-time logs
docker-compose logs -f swing-trader
docker-compose logs -f risk-monitor

# Container logs
docker logs swing-trader
docker logs risk-monitor
```

### 5. Stop Services
```bash
# Stop all
docker-compose down

# Stop specific service
docker-compose stop swing-trader
```

---

## Log Persistence

### Directory Structure (Host)
All logs persist on your host machine in the `logs/` directory:

```
logs/
├── india/
│   ├── observation/
│   │   ├── observations.jsonl       # India market monitoring
│   │   └── errors.jsonl
│   ├── paper/
│   │   ├── execution_log.jsonl      # Paper trading logs
│   │   ├── trade_ledger.json        # Completed trades
│   │   └── errors.jsonl
│   └── live/                        # ⚠️ NEVER committed to Git
│       └── (future use)
│
└── us/
    ├── paper/
    │   ├── execution_log.jsonl      # US paper trading
    │   ├── trade_ledger.json        # Completed trades
    │   └── errors.jsonl
    └── live/                        # ⚠️ NEVER committed to Git
        └── (future use)
```

### How Logs Persist
- **Bind Mount**: `./logs` on host → `/app/logs` in container
- **Survives**: Container restarts, image rebuilds, Docker updates
- **Location**: Same directory as `docker-compose.yml`

### Accessing Logs
```bash
# View execution log
tail -f logs/us/paper/execution_log.jsonl

# View trade ledger
cat logs/us/paper/trade_ledger.json | jq

# View errors
tail -f logs/us/paper/errors.jsonl
```

---

## Service Configuration

### Swing Trader
**Purpose**: Main trading engine  
**Schedule**: Run once daily after market close  
**Mode**: `--trade`

```bash
# Manual run
docker-compose up swing-trader

# Scheduled (add to cron)
0 17 * * 1-5 cd /path/to/trading_app && docker-compose up -d swing-trader
```

**What it does**:
1. Generate buy signals from EOD data
2. Submit orders to broker
3. Poll for fills
4. Evaluate swing exits (time/profit/trend)
5. Execute exit orders
6. Update trade ledger

### Risk Monitor
**Purpose**: Emergency exit monitoring  
**Schedule**: Every 15-30 minutes during market hours  
**Mode**: `--monitor`

```bash
# Manual run
docker-compose up risk-monitor

# Scheduled (add to cron)
*/15 9-16 * * 1-5 cd /path/to/trading_app && docker-compose up -d risk-monitor
```

**What it does**:
1. Check all open positions
2. Detect catastrophic losses (>3% portfolio)
3. Detect extreme moves (4× ATR)
4. Execute emergency exits if triggered
5. Update trade ledger

---

## Multi-Market Configuration

### India Market
```yaml
# In docker-compose.yml
environment:
  - MARKET=india
  - APP_ENV=paper
```

Logs: `logs/india/paper/`

### US Market
```yaml
# In docker-compose.yml
environment:
  - MARKET=us
  - APP_ENV=paper
```

Logs: `logs/us/paper/`

---

## Trading Modes

### 1. Observation (Monitor Only)
```yaml
environment:
  - MARKET=india
  - APP_ENV=observation
```
- No trading, monitoring only
- Logs: `logs/india/observation/`
- Safe to run 24/7

### 2. Paper Trading (Simulated)
```yaml
environment:
  - MARKET=us
  - APP_ENV=paper
```
- Simulated trading with paper account
- Logs: `logs/us/paper/`
- **Safe to commit logs to Git**

### 3. Live Trading (Real Money) 🚨
```yaml
environment:
  - MARKET=us
  - APP_ENV=live
```
- Real money trading
- Logs: `logs/us/live/` (**EXCLUDED from Git**)
- **Use with extreme caution**

---

## Troubleshooting

### Logs Not Persisting
**Problem**: Logs disappear after container restart  
**Solution**: Ensure volume mount exists in `docker-compose.yml`:
```yaml
volumes:
  - ./logs:/app/logs
```

### Permission Errors
**Problem**: Container can't write to `./logs`  
**Solution**: 
```bash
# Create logs directory with correct permissions
mkdir -p logs/{india,us}/{observation,paper,live}
chmod -R 755 logs/
```

### Environment Variables Not Working
**Problem**: API keys not loaded  
**Solution**: 
1. Ensure `.env` file exists in same directory as `docker-compose.yml`
2. Rebuild: `docker-compose build`
3. Check: `docker-compose config` (shows merged config)

### Container Exits Immediately
**Problem**: Service stops after starting  
**Solution**: 
```bash
# Check logs
docker-compose logs swing-trader

# Run interactively for debugging
docker-compose run --rm swing-trader python main.py --trade
```

### Stale Data in Container
**Problem**: Code changes not reflected  
**Solution**: 
```bash
# Rebuild image
docker-compose build

# Restart with new image
docker-compose up -d
```

---

## Advanced Usage

### Override Environment Variables
```bash
# Run with different market
docker-compose run -e MARKET=india swing-trader

# Run with live mode (⚠️ CAUTION)
docker-compose run -e APP_ENV=live swing-trader
```

### Run One-Off Commands
```bash
# Query trade ledger
docker-compose run --rm swing-trader python query_trades.py --all

# Demo script
docker-compose run --rm swing-trader python demo_trade_ledger.py
```

### Interactive Debugging
```bash
# Start bash in container
docker-compose run --rm swing-trader bash

# Then inside container:
ls /app/logs/us/paper/
python main.py --trade
```

### View Container Resources
```bash
# Container stats
docker stats swing-trader risk-monitor

# Inspect container
docker inspect swing-trader
```

---

## Production Considerations

### Scheduling
Use cron or system scheduler:

```bash
# Example crontab
# Swing trader: Run daily at 5 PM EST (after US market close)
0 17 * * 1-5 cd /path/to/trading_app && docker-compose up -d swing-trader

# Risk monitor: Run every 15 minutes during market hours
*/15 9-16 * * 1-5 cd /path/to/trading_app && docker-compose up -d risk-monitor
```

### Monitoring
```bash
# Add health checks to docker-compose.yml
healthcheck:
  test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### Log Rotation
```bash
# Rotate old logs (keep last 30 days)
find logs/ -name "*.jsonl" -mtime +30 -delete
```

### Backup
```bash
# Backup trade ledgers
tar -czf backup_$(date +%Y%m%d).tar.gz logs/*/paper/trade_ledger.json
```

---

## Security

### Secrets Management
❌ **Never** commit `.env` to Git  
✅ Use environment variables or Docker secrets

### Live Trading Logs
❌ **Never** commit `logs/*/live/` to Git  
✅ `.gitignore` excludes them automatically

### API Keys
❌ **Never** bake into Docker image  
✅ Pass via environment variables

---

## Migration from Non-Docker

### Step 1: Backup Existing Logs
```bash
cp -r logs logs.backup
```

### Step 2: Reorganize Logs
```bash
# Move existing paper trading logs
mkdir -p logs/us/paper
mv logs/execution_log.jsonl logs/us/paper/
mv logs/trade_ledger.json logs/us/paper/
```

### Step 3: Update Configuration
```bash
# Set environment variables
export MARKET=us
export APP_ENV=paper
```

### Step 4: Test Docker
```bash
# Build and test
docker-compose build
docker-compose run --rm swing-trader python -c "from config.log_paths import get_log_path_resolver; print(get_log_path_resolver().get_config_summary())"
```

---

## Summary

| Task | Command |
|------|---------|
| Build | `docker-compose build` |
| Start all | `docker-compose up -d` |
| Start trader only | `docker-compose up -d swing-trader` |
| View logs | `docker-compose logs -f swing-trader` |
| Stop all | `docker-compose down` |
| Rebuild | `docker-compose build --no-cache` |
| Check config | `docker-compose config` |

**Logs Location**: `./logs/{market}/{mode}/`  
**Safe Modes**: `observation`, `paper`  
**Caution Mode**: `live` (real money, logs excluded from Git)
