#!/usr/bin/env bash
set -euo pipefail

# Restarts the docker-compose "image-generator" service.
# Useful as a cron/systemd target to mitigate long-running "stuck" states.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

exec docker compose -f "${REPO_ROOT}/docker-compose.yml" restart image-generator
