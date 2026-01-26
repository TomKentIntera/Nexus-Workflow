#!/usr/bin/env bash
set -euo pipefail

# Recalculate scheduled_time for approved images.
#
# This script runs a Python script in the API container that uses the same
# scheduling logic as the API to ensure consistency. It applies random delays
# between WF_SCHEDULE_DELAY_MIN and WF_SCHEDULE_DELAY_MAX between consecutive
# images, while respecting the posting window and max posts per day.
#
# Configuration is read from the API .env:
#   WF_MAX_POSTS_PER_DAY
#   WF_POSTING_WINDOW_START
#   WF_POSTING_WINDOW_END
#   WF_SCHEDULE_DELAY_MIN
#   WF_SCHEDULE_DELAY_MAX
#
# Run:
#   ./Scripts/recalculate_schedule.sh [--dry-run]
#
# Options:
#   --dry-run, -n    Show what would happen without updating the database

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "docker-compose.yml not found at ${COMPOSE_FILE}" >&2
  exit 1
fi

# Check if API service is running
if ! docker compose -f "${COMPOSE_FILE}" ps api | grep -q "Up"; then
  echo "⚠️  API service is not running. Starting it..."
  docker compose -f "${COMPOSE_FILE}" up -d api
  echo "Waiting for API service to be healthy..."
  sleep 5
fi

# Copy the Python script into the container
RECALC_SCRIPT="${ROOT_DIR}/services/api/recalculate_schedule.py"
if [[ ! -f "${RECALC_SCRIPT}" ]]; then
  echo "Error: recalculate_schedule.py not found at ${RECALC_SCRIPT}" >&2
  exit 1
fi

# Change to root directory to use relative paths (avoids Windows path issues)
cd "${ROOT_DIR}"

# Copy using relative path from docker-compose.yml location
docker compose -f docker-compose.yml cp services/api/recalculate_schedule.py api:/app/recalculate_schedule.py

# Pass through arguments (--dry-run or -n)
echo "Running schedule recalculation..."

# Build the command - check if dry-run was requested
DRY_RUN_ARG=""
for arg in "$@"; do
  if [[ "${arg}" == "--dry-run" ]] || [[ "${arg}" == "-n" ]]; then
    DRY_RUN_ARG="--dry-run"
    break
  fi
done

# Execute in container - change to /app first, then run with relative path
if [[ -n "${DRY_RUN_ARG}" ]]; then
  docker compose -f docker-compose.yml exec -T api sh -c "cd /app && python recalculate_schedule.py --dry-run"
else
  docker compose -f docker-compose.yml exec -T api sh -c "cd /app && python recalculate_schedule.py"
fi
