#!/usr/bin/env sh
# Starts the static frontend at http://localhost:8080/
# Run this from anywhere; the script jumps to the repo's frontend folder.

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$SCRIPT_DIR/frontend"
python3 -m http.server 8080
