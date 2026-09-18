#!/usr/bin/env bash
# scripts/run_e2e.sh — Run the e2e suite against the isolated test stack (macOS/Linux)
#
# The test stack is a separate compose project (`resumetailor-e2e`) on a
# separate host port with tmpfs storage and a mock LLM. It cannot reach the
# dev stack's data. Nothing survives the run: `down -v` removes the containers
# and the network, and tmpfs storage is gone with the container.
#
# Usage:
#   ./scripts/run_e2e.sh              # build, run the suite in-container, tear down
#   E2E_HOST_PORT=19000 ./scripts/run_e2e.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.test.yml"

# Must not be 8000: that is the dev stack's port. Also refuse it if the caller
# overrides it, so this script cannot be talked into a collision.
E2E_HOST_PORT="${E2E_HOST_PORT:-18173}"
if [ "${E2E_HOST_PORT}" = "8000" ]; then
  echo "Error: E2E_HOST_PORT=8000 is the dev stack's port. Pick another." >&2
  exit 1
fi
export E2E_HOST_PORT

cleanup() {
  echo ""
  echo "Tearing down the test stack..."
  docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Starting the e2e stack (project resumetailor-e2e, host port ${E2E_HOST_PORT})..."
docker compose -f "${COMPOSE_FILE}" up \
  --build \
  --abort-on-container-exit \
  --exit-code-from playwright
