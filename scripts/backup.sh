#!/usr/bin/env bash
# scripts/backup.sh — Take a consistent backup of the database and the PDFs.
#
# The only durable copy of every resume lives in two Docker named volumes.
# `docker compose down -v` destroys both with no recovery (D-03). This script
# is the thing that makes that survivable.
#
# The database is copied with SQLite's online backup API, never with `cp`.
# `cp` on a live database can capture a torn file, and with WAL enabled it also
# misses everything still sitting in the `-wal` sidecar. The backup API takes a
# consistent snapshot of a database that is being written to, which is the
# whole point of running this without stopping the app.
#
# Usage:
#   ./scripts/backup.sh                    # auto-detect: container if running, else local files
#   ./scripts/backup.sh --local            # force local paths (DB_PATH / PDFS_DIR)
#   ./scripts/backup.sh --docker           # force the running compose service
#   ./scripts/backup.sh --out /mnt/backups # where to write (default: ./backups)
#   BACKUP_KEEP=14 ./scripts/backup.sh     # how many backups to keep (default: 7)
#
# Each run produces one self-contained directory:
#   backups/20260918T074103Z/
#     resumedb.db        the snapshot
#     pdfs/              every generated PDF
#     MANIFEST           schema version, row counts, sizes, sha256 of the database
#
# Restore with scripts/restore.sh, pointing at that directory.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
SERVICE="app"

# Container paths. These are the mount points in docker-compose.yml and the
# defaults in core/config.py; they are not the host paths.
CONTAINER_DB="/app/db/resumedb.db"
CONTAINER_PDFS="/app/pdfs"

MODE="auto"
OUT_ROOT="${BACKUP_OUT:-${REPO_ROOT}/backups}"
KEEP="${BACKUP_KEEP:-7}"

while [ $# -gt 0 ]; do
  case "$1" in
    --local)  MODE="local"; shift ;;
    --docker) MODE="docker"; shift ;;
    --out)    OUT_ROOT="${2:?--out needs a directory}"; shift 2 ;;
    --keep)   KEEP="${2:?--keep needs a number}"; shift 2 ;;
    -h|--help) sed -n '2,28p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

running_in_docker() {
  command -v docker >/dev/null 2>&1 &&
    [ -n "$(docker compose -f "${COMPOSE_FILE}" ps -q "${SERVICE}" 2>/dev/null)" ]
}

if [ "${MODE}" = "auto" ]; then
  if running_in_docker; then MODE="docker"; else MODE="local"; fi
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="${OUT_ROOT}/${STAMP}"
mkdir -p "${DEST}"

# A backup holds the user's real resume: name, email, phone, address. The
# default output directory is inside the repository, so it ignores itself
# rather than waiting for someone to run `git add -A` (this is D-01, and it is
# not worth risking twice).
if [ ! -f "${OUT_ROOT}/.gitignore" ]; then
  printf '*\n' > "${OUT_ROOT}/.gitignore"
fi

# The snapshot is written next to the live database first (SQLite's backup API
# needs a path the process running it can write) and then moved out.
SNAPSHOT_NAME="backup-${STAMP}.db"

# Runs SQLite's backup API against a live database. $1 is the source path,
# $2 the destination path, both in whatever filesystem the caller is using.
SQLITE_BACKUP_PY='
import sqlite3, sys
src = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close()
src.close()
'

echo "==> Backing up (${MODE}) to ${DEST}"

if [ "${MODE}" = "docker" ]; then
  if ! running_in_docker; then
    echo "Error: the '${SERVICE}' service is not running. Start it, or use --local." >&2
    exit 1
  fi
  docker compose -f "${COMPOSE_FILE}" exec -T "${SERVICE}" \
    python -c "${SQLITE_BACKUP_PY}" "${CONTAINER_DB}" "/tmp/${SNAPSHOT_NAME}"
  docker compose -f "${COMPOSE_FILE}" cp \
    "${SERVICE}:/tmp/${SNAPSHOT_NAME}" "${DEST}/resumedb.db"
  # Never leave the snapshot inside the live volume or the container.
  docker compose -f "${COMPOSE_FILE}" exec -T "${SERVICE}" rm -f "/tmp/${SNAPSHOT_NAME}"
  docker compose -f "${COMPOSE_FILE}" cp "${SERVICE}:${CONTAINER_PDFS}" "${DEST}/pdfs"
else
  DB_PATH="${DB_PATH:-${REPO_ROOT}/backend/db/resumedb.db}"
  PDFS_DIR="${PDFS_DIR:-${REPO_ROOT}/backend/pdfs}"
  if [ ! -f "${DB_PATH}" ]; then
    echo "Error: no database at ${DB_PATH}. Set DB_PATH, or use --docker." >&2
    exit 1
  fi
  python3 -c "${SQLITE_BACKUP_PY}" "${DB_PATH}" "${DEST}/resumedb.db"
  mkdir -p "${DEST}/pdfs"
  if [ -d "${PDFS_DIR}" ]; then
    # `.` so the contents land in pdfs/, not pdfs/pdfs/.
    (cd "${PDFS_DIR}" && tar cf - .) | (cd "${DEST}/pdfs" && tar xf -)
  fi
fi

# The manifest is read by a human deciding whether a backup is worth restoring,
# so it records what is in it rather than just that it exists.
{
  echo "taken_at:      ${STAMP}"
  echo "mode:          ${MODE}"
  echo "schema_version: $(python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
try:
    print(conn.execute('SELECT COALESCE(MAX(version), 0) FROM schema_version').fetchone()[0])
except sqlite3.Error:
    print('unknown')
conn.close()
" "${DEST}/resumedb.db")"
  python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
for table in ('master_resume', 'master_resume_history', 'generated_resumes',
              'chat_messages', 'generation_rules', 'system_prompt'):
    try:
        count = conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
    except sqlite3.Error:
        count = 'missing'
    print(f'rows.{table}: {count}')
conn.close()
" "${DEST}/resumedb.db"
  echo "pdf_count:     $(find "${DEST}/pdfs" -type f -name '*.pdf' 2>/dev/null | wc -l | tr -d ' ')"
  echo "db_bytes:      $(wc -c < "${DEST}/resumedb.db" | tr -d ' ')"
  echo "db_sha256:     $( (shasum -a 256 "${DEST}/resumedb.db" 2>/dev/null || sha256sum "${DEST}/resumedb.db") | awk '{print $1}')"
} > "${DEST}/MANIFEST"

# The snapshot is only a backup if it opens. Verify before reporting success
# and before retention deletes an older one.
python3 -c "
import sqlite3, sys
conn = sqlite3.connect(sys.argv[1])
result = conn.execute('PRAGMA integrity_check').fetchone()[0]
conn.close()
if result != 'ok':
    sys.exit('integrity_check failed: ' + result)
" "${DEST}/resumedb.db"

echo "==> Verified. Contents:"
sed 's/^/    /' "${DEST}/MANIFEST"

# Retention, oldest first, and only over directories this script made.
if [ "${KEEP}" -gt 0 ]; then
  # Not `mapfile`: macOS still ships bash 3.2 and this has to run there.
  ALL=()
  while IFS= read -r dir; do
    ALL+=("${dir}")
  done < <(find "${OUT_ROOT}" -mindepth 1 -maxdepth 1 -type d -name '2*Z' | sort)
  COUNT=${#ALL[@]}
  if [ "${COUNT}" -gt "${KEEP}" ]; then
    for old in "${ALL[@]:0:$((COUNT - KEEP))}"; do
      echo "==> Pruning ${old}"
      rm -rf "${old}"
    done
  fi
fi

echo "==> Backup complete: ${DEST}"
