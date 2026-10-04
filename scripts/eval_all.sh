#!/usr/bin/env bash
# Regression run of the whole harness against a model: three message sets, the chat set and the screenshots.
# Usage: SATARK_LLM=local:qwen3:4b-instruct-2507-q4_K_M SATARK_LLM_BASE_URL=http://<ollama>:11434/v1 \
#        [SATARK_LLM_IMAGE=local:minicpm-v:8b] scripts/eval_all.sh out_dir [--network]
# Each run writes <set>.json and <set>.log to out_dir; compare two runs with scripts/eval_errors.py.
set -uo pipefail
cd "$(dirname "$0")/.."
out="${1:?out_dir}"; shift || true
mkdir -p "$out"
for set in heldout_v3 heldout_v2 online_v1; do
  uv run python -u scripts/eval_set.py "tests/golden/$set.yaml" --json "$out/$set.json" "$@" > "$out/$set.log" 2>&1
  echo "$set: $(grep 'scams caught' "$out/$set.log")"
done
uv run python -u scripts/eval_chat.py --json "$out/chat.json" > "$out/chat.log" 2>&1
echo "chat: $(grep '^passed' "$out/chat.log")"
uv run python -u scripts/eval_screens.py --json "$out/screens.json" > "$out/screens.log" 2>&1
echo "screens: $(grep 'scams caught' "$out/screens.log")"
