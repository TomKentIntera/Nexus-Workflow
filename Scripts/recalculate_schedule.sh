#!/usr/bin/env bash
set -euo pipefail

# Recalculate scheduled_time for approved images.
#
# Update the configuration values below, then run:
#   ./Scripts/recalculate_schedule.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Configuration ---
IMAGES_PER_DAY=8
WINDOW_START="09:00:00" # HH:MM or HH:MM:SS
WINDOW_END="21:00:00"   # HH:MM or HH:MM:SS
# Set START_DATE to override the first scheduled date (YYYY-MM-DD).
START_DATE=""

# Optional: status value for approved images (matches DB enum).
APPROVED_STATUS="APPROVED"

API_ENV_FILE="${ROOT_DIR}/services/api/.env"

if [[ -z "${WF_DATABASE_URL:-}" && -f "${API_ENV_FILE}" ]]; then
  # Load WF_DATABASE_URL from services/api/.env if present.
  wf_line="$(grep -E '^WF_DATABASE_URL=' "${API_ENV_FILE}" | head -n 1 || true)"
  if [[ -n "${wf_line}" ]]; then
    WF_DATABASE_URL="${wf_line#WF_DATABASE_URL=}"
    WF_DATABASE_URL="${WF_DATABASE_URL%\"}"
    WF_DATABASE_URL="${WF_DATABASE_URL#\"}"
    WF_DATABASE_URL="${WF_DATABASE_URL%\'}"
    WF_DATABASE_URL="${WF_DATABASE_URL#\'}"
    export WF_DATABASE_URL
  fi
fi

if [[ -z "${WF_DATABASE_URL:-}" ]]; then
  echo "WF_DATABASE_URL is not set. Export it or add it to services/api/.env." >&2
  exit 1
fi

if [[ "${IMAGES_PER_DAY}" -le 0 ]]; then
  echo "IMAGES_PER_DAY must be > 0." >&2
  exit 1
fi

if [[ ! "${WINDOW_START}" =~ ^[0-2][0-9]:[0-5][0-9](:[0-5][0-9])?$ ]]; then
  echo "WINDOW_START must be HH:MM or HH:MM:SS." >&2
  exit 1
fi

if [[ ! "${WINDOW_END}" =~ ^[0-2][0-9]:[0-5][0-9](:[0-5][0-9])?$ ]]; then
  echo "WINDOW_END must be HH:MM or HH:MM:SS." >&2
  exit 1
fi

if [[ "${WINDOW_END}" <= "${WINDOW_START}" ]]; then
  echo "WINDOW_END must be later than WINDOW_START." >&2
  exit 1
fi

if [[ -n "${START_DATE}" && ! "${START_DATE}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "START_DATE must be YYYY-MM-DD when set." >&2
  exit 1
fi

db_url="${WF_DATABASE_URL}"
db_url="${db_url#*://}"
db_url="${db_url%%\?*}"

userpass_hostdb="${db_url%%/*}"
dbname="${db_url#*/}"
dbname="${dbname%%\?*}"

userpass="${userpass_hostdb%@*}"
hostport="${userpass_hostdb#*@}"

db_user="${userpass%%:*}"
db_pass="${userpass#*:}"

db_host="${hostport%%:*}"
db_port="${hostport#*:}"
if [[ "${db_port}" == "${db_host}" ]]; then
  db_port="3306"
fi

mysql_args=(
  --protocol=TCP
  --host="${db_host}"
  --port="${db_port}"
  --user="${db_user}"
  --password="${db_pass}"
  --database="${dbname}"
  --batch
  --skip-column-names
)

read -r scheduled_count start_date <<<"$(
  mysql "${mysql_args[@]}" -e \
    "SELECT COUNT(*), DATE(MIN(scheduled_time))
     FROM run_images
     WHERE status = '${APPROVED_STATUS}'
       AND scheduled_time IS NOT NULL;"
)"

if [[ "${scheduled_count}" -eq 0 ]]; then
  echo "No approved scheduled images found. Nothing to do."
  exit 0
fi

if [[ -n "${START_DATE}" ]]; then
  start_date="${START_DATE}"
fi

if [[ -z "${start_date}" || "${start_date}" == "NULL" ]]; then
  echo "Unable to determine start date from scheduled images." >&2
  exit 1
fi

echo "Found ${scheduled_count} approved scheduled images."
echo "Scheduling ${IMAGES_PER_DAY}/day between ${WINDOW_START}-${WINDOW_END}."
echo "Start date: ${start_date}"

mysql "${mysql_args[@]}" <<SQL
SET @images_per_day := ${IMAGES_PER_DAY};
SET @window_start := '${WINDOW_START}';
SET @window_end := '${WINDOW_END}';
SET @start_date := '${start_date}';
SET @interval_seconds := TIMESTAMPDIFF(
  SECOND,
  CONCAT('2000-01-01 ', @window_start),
  CONCAT('2000-01-01 ', @window_end)
) / @images_per_day;

UPDATE run_images AS ri
JOIN (
  SELECT id,
         ROW_NUMBER() OVER (ORDER BY scheduled_time ASC, id ASC) - 1 AS idx
  FROM run_images
  WHERE status = '${APPROVED_STATUS}'
    AND scheduled_time IS NOT NULL
) AS ordered
  ON ordered.id = ri.id
SET ri.scheduled_time = DATE_ADD(
  TIMESTAMP(
    DATE_ADD(@start_date, INTERVAL FLOOR(ordered.idx / @images_per_day) DAY),
    @window_start
  ),
  INTERVAL FLOOR(@interval_seconds * (ordered.idx % @images_per_day)) SECOND
);
SQL

echo "Recalculation complete."
