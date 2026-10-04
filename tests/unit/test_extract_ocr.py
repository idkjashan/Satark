"""OCR fallback for screenshots (CONTRACTS §4, LLD §6.5 point 5)."""

from __future__ import annotations

import io

import pytest

from satark.harness.extract import ocr

try:
    from PIL import Image, ImageDraw

    HAVE_PIL = True
except ImportError:  # pragma: no cover - Pillow is an installed dependency in this project
    HAVE_PIL = False


def _render(text: str) -> bytes:
    img = Image.new("RGB", (420, 80), "white")
    ImageDraw.Draw(img).text((10, 25), text, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.skipif(not HAVE_PIL, reason="Pillow not importable")
async def test_ocr_reads_rendered_text():
    image = _render("rajesh.vip@okaxis")
    text = await ocr.run(image, "image/png")
    assert text is not None
    assert "okaxis" in text.lower()


@pytest.mark.skipif(not HAVE_PIL, reason="Pillow not importable")
async def test_ocr_joins_multiple_lines_with_newlines():
    img = Image.new("RGB", (420, 140), "white")
    d = ImageDraw.Draw(img)
    d.text((10, 10), "SEBI Registered Adviser", fill="black")
    d.text((10, 60), "INA000012345", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    text = await ocr.run(buf.getvalue(), "image/png")
    assert text is not None
    assert "\n" in text


async def test_ocr_returns_none_on_garbage_bytes():
    assert await ocr.run(b"not an image at all", "image/png") is None


async def test_ocr_returns_none_when_engine_unavailable(monkeypatch):
    monkeypatch.setattr(ocr, "_unavailable", True)
    monkeypatch.setattr(ocr, "_engine", None)
    assert await ocr.run(b"irrelevant bytes", "image/png") is None
