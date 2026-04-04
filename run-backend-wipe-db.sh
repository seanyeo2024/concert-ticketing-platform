#!/usr/bin/env sh
# Rebuilds and starts the backend stack from a clean state.
# WARNING: This removes Docker volumes and wipes database data.
# WARNING: This also removes stopped Docker containers via `docker system prune -f`.

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR"

docker compose down -v
docker system prune -f
find services -type d -name '__pycache__' -prune -exec rm -rf {} +
docker compose build --no-cache
docker compose up
