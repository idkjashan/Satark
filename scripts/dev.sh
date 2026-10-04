#!/usr/bin/env bash
# Dev loop: the API with autoreload on :8000, and Vite's dev server alongside it. Vite proxies
# /v1, /healthz, /readyz, /share to :8000 (web/vite.config.ts, owned by F) so the PWA can call
# the API from its own dev port without CORS.
set -euo pipefail
cd "$(dirname "$0")/.."

export PORT="${PORT:-8000}"

cleanup() { kill 0; }
trap cleanup EXIT INT TERM

uv run uvicorn satark.app:create_app --factory --reload --host 0.0.0.0 --port "$PORT" &
npm --prefix web run dev &

wait
