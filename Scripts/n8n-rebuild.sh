#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "docker-compose.yml not found at ${COMPOSE_FILE}" >&2
  exit 1
fi

echo "Stopping existing n8n stack (if running)..."
docker compose -f "${COMPOSE_FILE}" down || true

echo "Rebuilding docker images..."
docker compose -f "${COMPOSE_FILE}" build

echo "Starting stack with rebuilt images..."
docker compose -f "${COMPOSE_FILE}" up -d
echo "n8n stack rebuilt and running."
