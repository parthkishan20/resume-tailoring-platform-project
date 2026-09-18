#!/usr/bin/env bash
# scripts/migrate.sh — Apply pending database migrations outside the app's
# own lifespan (D-02).
#
# `resumetailor.db.migrate.migrate()` is a plain function, not a CLI: it
# takes a `db_path`, brings it to the newest schema version, and is exactly
# what `main.py`'s lifespan already calls on every boot. This script exists
# for operators who want that to happen without starting the server — ahead
# of a deploy, so a migration (and any failure in it) happens before traffic
# is routed rather than on it.
#
# Usage:
#   ./scripts/migrate.sh                      # local: backend/db/resumedb.db
#   DB_PATH=/some/path.db ./scripts/migrate.sh # local: a different file
#   ./scripts/migrate.sh --docker             # migrate inside the running compose service
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
SERVICE="app"

MODE="local"
if [ "${1:-}" = "--docker" ]; then
  MODE="docker"
fi

# $1 is the db_path; resumetailor is only importable from inside the backend
# project (local) or the image (docker), so this cannot be a standalone
# script.
MIGRATE_PY='
import sys
from resumetailor.db.migrate import migrate
applied = migrate(sys.argv[1])
print("applied:", applied if applied else "(already up to date)")
'

if [ "${MODE}" = "docker" ]; then
  if ! command -v docker >/dev/null 2>&1 ||
     [ -z "$(docker compose -f "${COMPOSE_FILE}" ps -q "${SERVICE}" 2>/dev/null)" ]; then
    echo "Error: the '${SERVICE}' service is not running. Start it, or drop --docker." >&2
    exit 1
  fi
  echo "==> Migrating (docker) ${DB_PATH:-/app/db/resumedb.db}"
  docker compose -f "${COMPOSE_FILE}" exec -T "${SERVICE}" \
    python -c "${MIGRATE_PY}" "${DB_PATH:-/app/db/resumedb.db}"
else
  DB_PATH="${DB_PATH:-${REPO_ROOT}/backend/db/resumedb.db}"
  mkdir -p "$(dirname "${DB_PATH}")"
  echo "==> Migrating (local) ${DB_PATH}"
  ( cd "${REPO_ROOT}/backend" && uv run -- python -c "${MIGRATE_PY}" "${DB_PATH}" )
fi
