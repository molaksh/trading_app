#!/bin/bash
#
# Docker utility functions for container management
# Source this file in run scripts to get common functionality
#

# Persist docker logs before container removal
# Usage: persist_docker_logs CONTAINER_NAME SCOPE_DIR
persist_docker_logs() {
  local container_name="$1"
  local scope_dir="$2"
  
  if [ -z "$container_name" ] || [ -z "$scope_dir" ]; then
    echo "⚠️  persist_docker_logs: missing arguments (container_name, scope_dir)" >&2
    return 1
  fi
  
  # Check if container exists
  if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
    local ts=$(date +%Y%m%d_%H%M%S)
    local log_file="${scope_dir}/logs/docker_${ts}.log"
    
    # Ensure logs directory exists
    mkdir -p "${scope_dir}/logs"
    
    # Persist docker logs
    if docker logs "$container_name" > "$log_file" 2>&1; then
      echo "📦 Docker logs persisted: $(basename $log_file)"
    else
      echo "⚠️  Failed to persist docker logs for $container_name" >&2
    fi
  fi
}

# Stop and remove container with log persistence
# Usage: stop_and_remove_container CONTAINER_NAME SCOPE_DIR
stop_and_remove_container() {
  local container_name="$1"
  local scope_dir="$2"
  
  echo "Stopping old container (if running)..."
  docker stop "$container_name" 2>/dev/null || true
  
  # Persist docker logs before removal
  persist_docker_logs "$container_name" "$scope_dir"
  
  echo "Removing old container (if exists)..."
  docker rm "$container_name" 2>/dev/null || true
}

# Rebuild image (remove old image first)
# Usage: rebuild_image IMAGE_NAME [DOCKERFILE]
rebuild_image() {
  local image_name="$1"
  local dockerfile="${2:-Dockerfile}"
  
  echo "Removing old image (if exists)..."
  docker rmi "$image_name" 2>/dev/null || true
  
  echo "Building Docker image: $image_name..."
  if [ "$dockerfile" = "Dockerfile" ]; then
    docker build -t "$image_name" .
  else
    docker build -f "$dockerfile" -t "$image_name" .
  fi
}

# Setup scope directories and ledger file
# Usage: setup_scope_directories SCOPE_DIR LEDGER_FILE
setup_scope_directories() {
  local scope_dir="$1"
  local ledger_file="$2"
  
  mkdir -p "$scope_dir/logs" "$scope_dir/ledger" "$scope_dir/models"
  touch "$ledger_file"
}
