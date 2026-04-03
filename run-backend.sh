#!/usr/bin/env sh
# Rebuilds and starts the backend stack.
# WARNING: This removes stopped Docker containers via `docker system prune -f`.
# This does NOT wipe named volumes / database data.

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

docker compose down
docker system prune -f
find services -type d -name '__pycache__' -prune -exec rm -rf {} +
docker compose build --no-cache
docker compose up
