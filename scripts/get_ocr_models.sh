#!/usr/bin/env bash
# Downloads the optional Devanagari OCR recognition model (PaddleOCR PP-OCRv3 devanagari, Apache-2.0, ~9 MB)
# used by satark/harness/extract/ocr.py to read Hindi screenshots on the server. Not stored in git.
set -euo pipefail
dir="$(cd "$(dirname "$0")/.." && pwd)/data/models/ocr-hi"
mkdir -p "$dir"
base="https://huggingface.co/monkt/paddleocr-onnx/resolve/main/languages/hindi"
for f in rec.onnx dict.txt config.json; do curl -fsSL -o "$dir/$f" "$base/$f"; done
echo "Devanagari OCR model in $dir"
