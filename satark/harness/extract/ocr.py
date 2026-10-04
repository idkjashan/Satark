"""OCR fallback for a screenshot (CONTRACTS §4, LLD §6.5 point 5, §8.6).

The vision LLM is the primary path for screenshots (it returns `ocr_text` directly); this
module is the deterministic fallback when that role is off or fails. Lazy module-level
RapidOCR engine (loading the model is slow; do it once), run in a thread since inference is
blocking CPU work.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_engine: object | None = None
_unavailable = False


def _get_engine() -> object | None:
    global _engine, _unavailable
    if _unavailable:
        return None
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
        except ImportError:
            _unavailable = True
            return None
    return _engine


# Optional Devanagari recognition (PaddleOCR PP-OCRv3 "devanagari" model, Apache-2.0, ~9 MB, not in git):
# scripts/get_ocr_models.sh puts rec.onnx and dict.txt here. The default model reads Latin script only, so a
# Hindi screenshot came out as noise; with this model each text line is read twice and the better reading kept.
_HI_DIR = Path(__file__).resolve().parents[3] / "data" / "models" / "ocr-hi"
_hi_engine: object | None = None
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_ID_LIKE = re.compile(r"@[a-zA-Z]{2,}|www\.|https?://|\.(?:in|com)\b|\d{3}[\d \-]{6,}")


def _get_hi_engine() -> object | None:
    global _hi_engine
    if _hi_engine is None and (_HI_DIR / "rec.onnx").exists() and (_HI_DIR / "dict.txt").exists():
        try:
            from rapidocr_onnxruntime import RapidOCR

            _hi_engine = RapidOCR(rec_model_path=str(_HI_DIR / "rec.onnx"), rec_keys_path=str(_HI_DIR / "dict.txt"))
        except Exception:  # noqa: BLE001 - optional model: Latin OCR still works
            log.warning("Devanagari OCR model failed to load", exc_info=True)
            _hi_engine = False
    return _hi_engine or None


def _pick(latin: tuple, hindi: tuple | None) -> str:
    """One text line read by both models: the Devanagari reading when most of its letters are Hindi (the Latin
    model turns a Hindi line into confident-looking noise), else the Latin reading (better at IDs and digits)."""
    if hindi:
        letters = [ch for ch in hindi[1] if ch.isalpha()]
        if letters and sum(bool(_DEVANAGARI.match(ch)) for ch in letters) / len(letters) >= 0.3:
            # the Latin model still spells IDs, links and numbers better: keep its line too when it holds one
            return hindi[1] + (f"\n{latin[1]}" if _ID_LIKE.search(latin[1]) else "")
    return latin[1]


def _recognise(image: bytes, mime: str) -> str | None:
    engine = _get_engine()
    if engine is None:
        return None
    try:
        import numpy as np
        from PIL import Image

        pixels = np.array(Image.open(io.BytesIO(image)).convert("RGB"))
        result, _elapse = engine(pixels)  # type: ignore[operator]
        hi_engine = _get_hi_engine()
        hindi = hi_engine(pixels)[0] if hi_engine is not None else None  # type: ignore[operator]
        if not result and not hindi:
            return ""
        if hindi and (not result or len(hindi) != len(result)):  # boxes differ: keep the run that saw Hindi
            if sum(len(_DEVANAGARI.findall(line[1])) for line in hindi) < 5 and result:
                return "\n".join(line[1] for line in result)
            ids = [line[1] for line in result or [] if _ID_LIKE.search(line[1])]
            return "\n".join([line[1] for line in hindi] + ids)
        return "\n".join(_pick(line, hindi[i] if hindi else None) for i, line in enumerate(result))
    except Exception:  # noqa: BLE001 - OCR must never raise; a bad image just means no text
        log.warning("ocr failed", exc_info=True)
        return None


async def run(image: bytes, mime: str) -> str | None:
    return await asyncio.to_thread(_recognise, image, mime)
