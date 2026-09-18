#!/usr/bin/env bash
# scripts/restore.sh — Put a backup back (D-03).
#
# Restoring is destructive: it replaces the live database and every PDF with
# the contents of a backup directory. So this script does three things before
# it writes anything.
#
#  1. It verifies the backup opens and passes `PRAGMA integrity_check`. A
#     corrupt backup must not be allowed to overwrite working data.
#  2. It takes a safety backup of what is there now, unless told not to. If the
#     restore turns out to be the wrong one, the previous state is still on
#     disk.
#  3. It asks, showing what it is about to overwrite and with what. `--force`
#     skips the question and nothing else.
#
# It also deletes the `-wal` and `-shm` sidecars. Dropping a database file next
# to a stale write-ahead log is how a restore silently ends up as a mixture of
# both.
#
# Usage:
#   ./scripts/restore.sh backups/20260918T074103Z
#   ./scripts/restore.sh --local backups/20260918T074103Z
#   ./scripts/restore.sh --force --no-safety-backup backups/20260918T074103Z
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
SERVICE="app"

CONTAINER_DB="/app/db/resumedb.db"
CONTAINER_DB_DIR="/app/db"
CONTAINER_PDFS="/app/pdfs"

MODE="auto"
FORCE="no"
SAFETY="yes"
SRC=""

while [ $# -gt 0 ]; do
  case "$1" in
    --local)  MODE="local"; shift ;;
    --docker) MODE="docker"; shift ;;
    --force)  FORCE="yes"; shift ;;
    --no-safety-backup) SAFETY="no"; shift ;;
    -h|--help) sed -n '2,24p' "${BASH_SOURCE[0]}"; exit 0 ;;
    -*) echo "Unknown argument: $1" >&2; exit 2 ;;
    *)  SRC="$1"; shift ;;
  esac
done

if [ -z "${SRC}" ]; then
  echo "Usage: $0 [--local|--docker] [--force] <backup-directory>" >&2
  exit 2
fi
if [ ! -f "${SRC}/resumedb.db" ]; then
  echo "Error: ${SRC}/resumedb.db not found. Point at a directory made by backup.sh." >&2
  exit 1
fi

# 1. Verify before touching anything.
python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
result = conn.execute('PRAGMA integrity_check').fetchone()[0]
version = conn.execute('SELECT COALESCE(MAX(version), 0) FROM schema_version').fetchone()[0]
conn.close()
if result != 'ok':
    sys.exit('refusing to restore a corrupt backup: ' + result)
print(f'backup is intact, schema version {version}')
" "${SRC}/resumedb.db"

running_in_docker() {
  command -v docker >/dev/null 2>&1 &&
    [ -n "$(docker compose -f "${COMPOSE_FILE}" ps -q "${SERVICE}" 2>/dev/null)" ]
}

if [ "${MODE}" = "auto" ]; then
  if running_in_docker; then MODE="docker"; else MODE="local"; fi
fi

DB_PATH="${DB_PATH:-${REPO_ROOT}/backend/db/resumedb.db}"
PDFS_DIR="${PDFS_DIR:-${REPO_ROOT}/backend/pdfs}"

echo ""
echo "Restore (${MODE})"
echo "  from: ${SRC}"
if [ -f "${SRC}/MANIFEST" ]; then sed 's/^/        /' "${SRC}/MANIFEST"; fi
if [ "${MODE}" = "docker" ]; then
  echo "  onto: the ${SERVICE} service's volumes (${CONTAINER_DB}, ${CONTAINER_PDFS})"
else
  echo "  onto: ${DB_PATH} and ${PDFS_DIR}"
fi
echo ""
echo "This REPLACES the current database and every PDF."

if [ "${FORCE}" != "yes" ]; then
  printf "Type 'restore' to continue: "
  read -r answer
  if [ "${answer}" != "restore" ]; then
    echo "Aborted; nothing was changed."
    exit 1
  fi
fi

# 2. Safety backup of the current state, while the app is still up.
if [ "${SAFETY}" = "yes" ]; then
  echo "==> Safety backup of the current state first"
  if [ "${MODE}" = "docker" ]; then
    "${REPO_ROOT}/scripts/backup.sh" --docker --out "${REPO_ROOT}/backups/pre-restore" --keep 0
  elif [ -f "${DB_PATH}" ]; then
    DB_PATH="${DB_PATH}" PDFS_DIR="${PDFS_DIR}" \
      "${REPO_ROOT}/scripts/backup.sh" --local --out "${REPO_ROOT}/backups/pre-restore" --keep 0
  else
    echo "    nothing to back up: ${DB_PATH} does not exist"
  fi
fi

# 3. Restore.
if [ "${MODE}" = "docker" ]; then
  echo "==> Stopping ${SERVICE}"
  docker compose -f "${COMPOSE_FILE}" stop "${SERVICE}"

  # A one-shot container on the same volumes: the service container is stopped,
  # so this is the only way to remove files inside them.
  echo "==> Clearing the live database sidecars and the PDF directory"
  docker compose -f "${COMPOSE_FILE}" run --rm --no-deps --entrypoint sh "${SERVICE}" -c \
    "rm -f ${CONTAINER_DB}-wal ${CONTAINER_DB}-shm; rm -rf ${CONTAINER_PDFS}/*"

  echo "==> Copying the backup in"
  docker compose -f "${COMPOSE_FILE}" cp "${SRC}/resumedb.db" "${SERVICE}:${CONTAINER_DB}"
  if [ -d "${SRC}/pdfs" ]; then
    docker compose -f "${COMPOSE_FILE}" cp "${SRC}/pdfs/." "${SERVICE}:${CONTAINER_PDFS}"
  fi

  echo "==> Starting ${SERVICE}"
  docker compose -f "${COMPOSE_FILE}" start "${SERVICE}"
else
  echo "==> Replacing ${DB_PATH}"
  mkdir -p "$(dirname "${DB_PATH}")"
  rm -f "${DB_PATH}-wal" "${DB_PATH}-shm"
  cp "${SRC}/resumedb.db" "${DB_PATH}"

  echo "==> Replacing ${PDFS_DIR}"
  rm -rf "${PDFS_DIR}"
  mkdir -p "${PDFS_DIR}"
  if [ -d "${SRC}/pdfs" ]; then
    (cd "${SRC}/pdfs" && tar cf - .) | (cd "${PDFS_DIR}" && tar xf -)
  fi
fi

echo ""
echo "==> Restore complete."
echo "    The app migrates on start, so a backup from an older schema version"
echo "    is brought forward automatically on the next boot."
if [ "${SAFETY}" = "yes" ]; then
  echo "    The previous state is under ${REPO_ROOT}/backups/pre-restore."
fi
