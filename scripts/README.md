# Docker Container Management Utilities

## Overview
Reusable bash functions for consistent docker container lifecycle management across all trading modes, markets, and strategies.

## Location
`scripts/docker_utils.sh`

## Functions

### `persist_docker_logs`
Saves docker container stdout/stderr logs before container removal.

**Usage:**
```bash
persist_docker_logs CONTAINER_NAME SCOPE_DIR
```

**Example:**
```bash
persist_docker_logs "paper-alpaca-swing-us" "$SCOPE_DIR"
```

**Saves to:**
`$SCOPE_DIR/logs/docker_YYYYMMDD_HHMMSS.log`

---

### `stop_and_remove_container`
Stops container, persists logs, then removes container.

**Usage:**
```bash
stop_and_remove_container CONTAINER_NAME SCOPE_DIR
```

**Example:**
```bash
stop_and_remove_container "paper-alpaca-swing-us" "$SCOPE_DIR"
```

---

### `rebuild_image`
Removes old image and builds fresh one.

**Usage:**
```bash
rebuild_image IMAGE_NAME [DOCKERFILE]
```

**Examples:**
```bash
rebuild_image "paper-alpaca-swing-us"                    # Uses Dockerfile
rebuild_image "paper-nse-swing-india" "Dockerfile.india" # Custom Dockerfile
```

---

### `setup_scope_directories`
Creates required scope directories (logs, ledger, models) and initializes ledger file.

**Usage:**
```bash
setup_scope_directories SCOPE_DIR LEDGER_FILE
```

**Example:**
```bash
setup_scope_directories "$SCOPE_DIR" "$SCOPE_DIR/ledger/trades.jsonl"
```

---

## Integration

**In any run script:**

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load docker utilities
source "$SCRIPT_DIR/scripts/docker_utils.sh"

# Your scope setup
SCOPE="paper_broker_mode_market"
SCOPE_DIR="logs/$SCOPE"
LEDGER_FILE="$SCOPE_DIR/ledger/trades.jsonl"

# Use utilities
setup_scope_directories "$SCOPE_DIR" "$LEDGER_FILE"
stop_and_remove_container "my-container" "$SCOPE_DIR"
rebuild_image "my-image"
```

---

## Log Persistence

All docker logs are automatically persisted to:
```
logs/<scope>/logs/docker_YYYYMMDD_HHMMSS.log
```

This ensures logs survive:
- ✅ `docker rm` (container removal)
- ✅ `docker rmi` (image removal)
- ✅ Container rebuilds
- ✅ System restarts

---

## Future Scripts

When creating new run scripts for different:
- Markets (crypto, forex, etc.)
- Modes (live, backtest, etc.)
- Strategies (scalp, day, etc.)
- Brokers (interactive brokers, zerodha, etc.)

Simply source `scripts/docker_utils.sh` and use these functions for consistent log persistence and container management.
