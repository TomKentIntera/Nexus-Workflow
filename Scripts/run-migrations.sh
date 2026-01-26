#!/usr/bin/env bash
set -euo pipefail

# Script to run any pending database migrations
# This script finds all migration files and runs those that haven't been executed yet

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
API_DIR="${ROOT_DIR}/services/api"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  echo "docker-compose.yml not found at ${COMPOSE_FILE}" >&2
  exit 1
fi

if [[ ! -d "${API_DIR}" ]]; then
  echo "API directory not found at ${API_DIR}" >&2
  exit 1
fi

# Check if API service is running
if ! docker compose -f "${COMPOSE_FILE}" ps api | grep -q "Up"; then
  echo "⚠️  API service is not running. Starting it..."
  docker compose -f "${COMPOSE_FILE}" up -d api
  echo "Waiting for API service to be healthy..."
  sleep 5
fi

echo "Running pending migrations..."

# First, copy the migrations table creation script into the container if it doesn't exist
echo "Ensuring migration scripts are available in container..."
MIGRATION_TABLE_SCRIPT="${API_DIR}/migrate_create_migrations_table.py"
if [[ -f "${MIGRATION_TABLE_SCRIPT}" ]]; then
  docker compose -f "${COMPOSE_FILE}" cp "${MIGRATION_TABLE_SCRIPT}" api:/app/migrate_create_migrations_table.py 2>/dev/null || true
fi

# Copy any other migration files that might be missing
for MIG_FILE in "${API_DIR}"/migrate*.py; do
  if [[ -f "${MIG_FILE}" ]]; then
    MIG_BASENAME=$(basename "${MIG_FILE}")
    docker compose -f "${COMPOSE_FILE}" cp "${MIG_FILE}" "api:/app/${MIG_BASENAME}" 2>/dev/null || true
  fi
done

# First, ensure the migrations tracking table exists
echo "Ensuring migrations tracking table exists..."
if ! docker compose -f "${COMPOSE_FILE}" exec -T api sh -c "cd /app && python migrate_create_migrations_table.py"; then
  echo "❌ Failed to create migrations table. Cannot proceed." >&2
  exit 1
fi

# Find all migration files (excluding the tracking table migration itself to avoid recursion)
MIGRATION_FILES=$(find "${API_DIR}" -maxdepth 1 -name "migrate*.py" -type f ! -name "migrate_create_migrations_table.py" | sort)

if [[ -z "${MIGRATION_FILES}" ]]; then
  echo "No migration files found in ${API_DIR}"
  exit 0
fi

# Track which migrations were run
MIGRATIONS_RUN=0
MIGRATIONS_SKIPPED=0

# Run each migration
for MIGRATION_FILE in ${MIGRATION_FILES}; do
  MIGRATION_NAME=$(basename "${MIGRATION_FILE}")
  
  echo ""
  echo "Checking migration: ${MIGRATION_NAME}"
  
  # Check if this migration has already been run
  # We do this by checking if the migration name exists in the schema_migrations table
  MIGRATION_EXISTS=$(docker compose -f "${COMPOSE_FILE}" exec -T -e MIGRATION_NAME="${MIGRATION_NAME}" api sh -c 'cd /app && python -c "
import sys
import os
sys.path.insert(0, \"/app\")
from app.database import engine
from sqlalchemy import text

migration_name = os.environ[\"MIGRATION_NAME\"]
try:
    with engine.connect() as conn:
        result = conn.execute(
            text(\"SELECT COUNT(*) FROM schema_migrations WHERE migration_name = :name\"),
            {\"name\": migration_name}
        )
        count = result.scalar_one()
        print(\"1\" if count > 0 else \"0\")
except Exception as e:
    # If table does not exist or any other error, assume migration has not run
    print(\"0\")
"')

  if [[ "${MIGRATION_EXISTS}" == "1" ]]; then
    echo "  ⏭️  Skipping ${MIGRATION_NAME} (already applied)"
    ((MIGRATIONS_SKIPPED++)) || true
    continue
  fi

  echo "  ▶️  Running ${MIGRATION_NAME}..."
  
  # Run the migration
  if docker compose -f "${COMPOSE_FILE}" exec -T api sh -c "cd /app && python ${MIGRATION_NAME}"; then
    # Record the migration in the tracking table
    docker compose -f "${COMPOSE_FILE}" exec -T -e MIGRATION_NAME="${MIGRATION_NAME}" api sh -c 'cd /app && python -c "
import sys
import os
from uuid import uuid4
sys.path.insert(0, \"/app\")
from app.database import engine
from sqlalchemy import text
from datetime import datetime

migration_name = os.environ[\"MIGRATION_NAME\"]
migration_id = str(uuid4())

with engine.begin() as conn:
    conn.execute(
        text(\"INSERT INTO schema_migrations (id, migration_name, applied_at) VALUES (:id, :name, :applied_at)\"),
        {
            \"id\": migration_id,
            \"name\": migration_name,
            \"applied_at\": datetime.utcnow()
        }
    )
"' 2>/dev/null && {
      echo "  ✅ ${MIGRATION_NAME} completed and recorded"
      ((MIGRATIONS_RUN++)) || true
    } || {
      echo "  ⚠️  ${MIGRATION_NAME} completed but failed to record in tracking table"
      ((MIGRATIONS_RUN++)) || true
    }
  else
    echo "  ❌ ${MIGRATION_NAME} failed!"
    exit 1
  fi
done

echo ""
echo "Migration summary:"
echo "  - Migrations run: ${MIGRATIONS_RUN}"
echo "  - Migrations skipped: ${MIGRATIONS_SKIPPED}"
echo "  - Total migrations: $((MIGRATIONS_RUN + MIGRATIONS_SKIPPED))"

if [[ ${MIGRATIONS_RUN} -gt 0 ]]; then
  echo ""
  echo "✅ All pending migrations have been applied successfully!"
else
  echo ""
  echo "ℹ️  No pending migrations to run."
fi

