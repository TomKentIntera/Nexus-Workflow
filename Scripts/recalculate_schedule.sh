#!/usr/bin/env bash
set -euo pipefail

# Recalculate scheduled_time for approved images.
#
# Configuration is read from the reviewer app .env:
#   REVIEWER_IMAGES_PER_DAY
#   REVIEWER_POSTING_WINDOW_START
#   REVIEWER_POSTING_WINDOW_END
#
# Run:
#   ./Scripts/recalculate_schedule.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Optional: status value for approved images (matches DB enum).
APPROVED_STATUS="APPROVED"

REVIEWER_ENV_FILE="${ROOT_DIR}/services/reviewer/.env"
API_ENV_FILE="${ROOT_DIR}/services/api/.env"

load_env_value() {
  local key="$1"
  local file="$2"
  if [[ -n "${!key:-}" ]]; then
    return 0
  fi
  if [[ ! -f "${file}" ]]; then
    return 0
  fi
  local line=""
  line="$(grep -E "^${key}=" "${file}" | head -n 1 || true)"
  if [[ -z "${line}" ]]; then
    return 0
  fi
  local value="${line#${key}=}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"
  printf -v "${key}" "%s" "${value}"
  export "${key}"
}

if ! command -v mysql >/dev/null 2>&1; then
  echo "mysql client not found. Install it or run from a machine with mysql CLI." >&2
  exit 1
fi

load_env_value "REVIEWER_IMAGES_PER_DAY" "${REVIEWER_ENV_FILE}"
load_env_value "REVIEWER_POSTING_WINDOW_START" "${REVIEWER_ENV_FILE}"
load_env_value "REVIEWER_POSTING_WINDOW_END" "${REVIEWER_ENV_FILE}"

if [[ -z "${WF_DATABASE_URL:-}" && -f "${API_ENV_FILE}" ]]; then
  load_env_value "WF_DATABASE_URL" "${API_ENV_FILE}"
fi

images_per_day="${REVIEWER_IMAGES_PER_DAY:-}"
window_start="${REVIEWER_POSTING_WINDOW_START:-}"
window_end="${REVIEWER_POSTING_WINDOW_END:-}"

if [[ -z "${WF_DATABASE_URL:-}" ]]; then
  echo "WF_DATABASE_URL is not set. Export it or add it to services/api/.env." >&2
  exit 1
fi

if [[ -z "${images_per_day}" ]]; then
  echo "REVIEWER_IMAGES_PER_DAY is not set in services/reviewer/.env." >&2
  exit 1
fi

if [[ -z "${window_start}" ]]; then
  echo "REVIEWER_POSTING_WINDOW_START is not set in services/reviewer/.env." >&2
  exit 1
fi

if [[ -z "${window_end}" ]]; then
  echo "REVIEWER_POSTING_WINDOW_END is not set in services/reviewer/.env." >&2
  exit 1
fi

if [[ "${images_per_day}" -le 0 ]]; then
  echo "REVIEWER_IMAGES_PER_DAY must be > 0." >&2
  exit 1
fi

if [[ ! "${window_start}" =~ ^[0-2][0-9]:[0-5][0-9](:[0-5][0-9])?$ ]]; then
  echo "REVIEWER_POSTING_WINDOW_START must be HH:MM or HH:MM:SS." >&2
  exit 1
fi

if [[ ! "${window_end}" =~ ^[0-2][0-9]:[0-5][0-9](:[0-5][0-9])?$ ]]; then
  echo "REVIEWER_POSTING_WINDOW_END must be HH:MM or HH:MM:SS." >&2
  exit 1
fi

if [[ "${window_end}" <= "${window_start}" ]]; then
  echo "REVIEWER_POSTING_WINDOW_END must be later than START." >&2
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

if [[ -z "${start_date}" || "${start_date}" == "NULL" ]]; then
  echo "Unable to determine start date from scheduled images." >&2
  exit 1
fi

echo "Found ${scheduled_count} approved scheduled images."
echo "Scheduling ${images_per_day}/day between ${window_start}-${window_end}."
echo "Start date: ${start_date}"

mysql "${mysql_args[@]}" <<SQL
SET @images_per_day := ${images_per_day};
SET @window_start := '${window_start}';
SET @window_end := '${window_end}';
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
