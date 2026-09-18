#!/usr/bin/env bash
# scripts/start_mac.sh — Start ResumeTailor (macOS/Linux)
set -euo pipefail

CONTAINER_NAME="resumetailor"
IMAGE_NAME="resumetailor"
# Override to move the dev stack off 8000 (the e2e stack uses 18173 and never 8000).
PORT="${PORT:-8000}"

# Check for .env file
if [ ! -f ".env" ]; then
  echo "Error: .env file not found. Copy .env.example to .env and set OPENAI_API_KEY."
  exit 1
fi

# Stop any existing container with this name
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping existing container..."
  docker stop "${CONTAINER_NAME}" 2>/dev/null || true
  docker rm "${CONTAINER_NAME}" 2>/dev/null || true
fi

# Build if --build flag passed or image doesn't exist
if [[ "${1:-}" == "--build" ]] || ! docker image inspect "${IMAGE_NAME}" &>/dev/null; then
  echo "Building Docker image..."
  docker build -t "${IMAGE_NAME}" .
fi

echo "Starting ResumeTailor..."
docker run -d \
  --name "${CONTAINER_NAME}" \
  -p "${PORT}:8000" \
  -v resumedb-data:/app/db \
  -v resumepdf-data:/app/pdfs \
  --env-file .env \
  --restart unless-stopped \
  "${IMAGE_NAME}"

echo ""
echo "ResumeTailor is starting at http://localhost:${PORT}"
echo "Waiting for health check..."

# Wait up to 90s for health
for i in $(seq 1 18); do
  if curl -sf "http://localhost:${PORT}/api/health" > /dev/null 2>&1; then
    echo "Ready! Opening http://localhost:${PORT}"
    # Open browser if on macOS
    if command -v open &>/dev/null; then
      open "http://localhost:${PORT}"
    fi
    exit 0
  fi
  sleep 5
done

echo "Warning: app did not become healthy within 90s. Check: docker logs ${CONTAINER_NAME}"
