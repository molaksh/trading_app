# ============================================================================
# Multi-Market Trading Platform - Dockerfile
# ============================================================================
#
# PURPOSE:
#   Containerize Python swing trading platform for:
#   - India market observation & paper trading
#   - US market paper trading
#   - Future: live trading, day trading, options
#
# CRITICAL DESIGN DECISIONS:
#   1. Logs are NEVER written inside the image
#   2. All logs persist via host-mounted volumes
#   3. Image contains only code and dependencies
#   4. Secrets (API keys) come from environment, not baked in
#   5. Default mode is paper trading (safe)
#
# USAGE:
#   Build: docker build -t swing-trader .
#   Run:   docker-compose up
#
# ============================================================================

# Base image: Python 3.11 slim (small footprint, stable)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (if needed for any packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker layer caching optimization)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create log directory structure inside container
# (These will be mounted from host via docker-compose volumes)
RUN mkdir -p /app/logs/india/observation && \
    mkdir -p /app/logs/india/paper && \
    mkdir -p /app/logs/india/live && \
    mkdir -p /app/logs/us/paper && \
    mkdir -p /app/logs/us/live

# Environment variables (defaults, can be overridden)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default command: run trading platform with scheduler (continuous mode)
# Override in docker-compose.yml or docker run for different modes
CMD ["python", "main.py", "--schedule"]

# ============================================================================
# IMPORTANT NOTES:
# ============================================================================
#
# 1. LOGS & PERSISTENCE:
#    - /app/logs MUST be mounted as a volume in docker-compose.yml
#    - Without volume mount, logs will be lost on container restart
#    - Log structure: /app/logs/{market}/{mode}/execution_log.jsonl
#
# 2. SECRETS & API KEYS:
#    - NEVER bake secrets into the image
#    - Pass via environment variables in docker-compose.yml
#    - For Alpaca: APCA_API_KEY_ID, APCA_API_SECRET_KEY
#
# 3. TRADING MODES:
#    - observation: Monitor only, no orders
#    - paper: Paper trading (simulated)
#    - live: Real money (future, separate logs)
#
# 4. MULTI-MARKET:
#    - india: India market
#    - us: US market (Alpaca)
#
# 5. IMMUTABILITY:
#    - Trading logic is immutable inside container
#    - Only logs change (via mounted volumes)
#    - Rebuild image for code changes
#
# ============================================================================
