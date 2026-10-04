#!/usr/bin/env bash
# Run the API locally the same way the container does (LLD §19.1), on :8000.
# Builds the PWA first if web/dist is missing, so a fresh checkout works with one command.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d web/dist ]; then
  echo "web/dist missing; building the PWA..."
  npm --prefix web install
  npm --prefix web run build
fi

export PORT="${PORT:-8000}"
exec uv run uvicorn satark.app:create_app --factory --host 0.0.0.0 --port "$PORT" --workers 1
