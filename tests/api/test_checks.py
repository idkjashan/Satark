"""POST /v1/checks (CONTRACTS §6)."""

from __future__ import annotations

import pytest

from tests.api.fakes import build_fake_runtime

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 32
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 32


async def test_happy_path_text(client):
    resp = await client.post("/v1/checks", data={"text": "please help me verify this", "lang": "en"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] and body["case_id"]
    assert body["events_url"] == f"/v1/runs/{body['run_id']}/events"
    assert "T" in body["expires_at"]  # ISO 8601


async def test_happy_path_image(client):
    resp = await client.post("/v1/checks", data={"lang": "en"}, files={"image": ("x.png", PNG_BYTES, "image/png")})
    assert resp.status_code == 202


async def test_happy_path_jpeg_and_webp(client):
    for name, data, declared in (("x.jpg", JPEG_BYTES, "image/jpeg"), ("x.webp", WEBP_BYTES, "image/webp")):
        resp = await client.post("/v1/checks", data={"lang": "en"}, files={"image": (name, data, declared)})
        assert resp.status_code == 202, (name, resp.text)


async def test_happy_path_qr(client):
    resp = await client.post("/v1/checks", data={"qr": "upi://pay?pa=test@okaxis", "lang": "en"})
    assert resp.status_code == 202


async def test_text_too_large(client):
    resp = await client.post("/v1/checks", data={"text": "a" * 4001, "lang": "en"})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "input_too_large"
    assert resp.json()["error"]["retryable"] is False


async def test_qr_too_large(client):
    resp = await client.post("/v1/checks", data={"qr": "a" * 1001, "lang": "en"})
    assert resp.status_code == 413


async def test_image_too_large(client):
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2_000_001
    resp = await client.post("/v1/checks", data={"lang": "en"}, files={"image": ("x.png", big, "image/png")})
    assert resp.status_code == 413


async def test_unsupported_media(client):
    resp = await client.post("/v1/checks", data={"lang": "en"}, files={"image": ("x.gif", b"GIF89a" + b"\x00" * 20, "image/gif")})
    assert resp.status_code == 415
    assert resp.json()["error"]["code"] == "unsupported_media"


async def test_media_type_sniffed_not_trusted(client):
    """A text file masquerading as a PNG (wrong magic bytes) must still be rejected."""
    resp = await client.post(
        "/v1/checks", data={"lang": "en"}, files={"image": ("x.png", b"not actually a png", "image/png")}
    )
    assert resp.status_code == 415


@pytest.mark.parametrize("text", ["", "   ", "\n\t", "🙂🙂🙂", "😀 😭 🎉"])
async def test_nothing_to_check(client, text):
    resp = await client.post("/v1/checks", data={"text": text, "lang": "en"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "nothing_to_check"


async def test_nothing_to_check_absent_fields(client):
    resp = await client.post("/v1/checks", data={"lang": "en"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "nothing_to_check"


async def test_bad_language(client):
    resp = await client.post("/v1/checks", data={"text": "hello", "lang": "xx"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "bad_language"


async def test_disabled_language_rejected(client):
    """mr is defined in config/languages.yaml but enabled: false."""
    resp = await client.post("/v1/checks", data={"text": "hello", "lang": "mr"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "bad_language"


async def test_missing_lang_is_422(client):
    resp = await client.post("/v1/checks", data={"text": "hello"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


async def test_busy(settings, config):
    rt = build_fake_runtime(settings, config, busy=True)
    from httpx import ASGITransport, AsyncClient

    from satark.app import create_app

    app = create_app(settings=settings, runtime=rt)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/checks", data={"text": "hello", "lang": "en"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "busy"
    assert resp.headers["retry-after"] == "5"


async def test_not_ready(settings, config):
    rt = build_fake_runtime(settings, config, ready=False, not_ready_reason="registry missing")
    from httpx import ASGITransport, AsyncClient

    from satark.app import create_app

    app = create_app(settings=settings, runtime=rt)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/checks", data={"text": "hello", "lang": "en"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "not_ready"


async def test_oversized_multipart_body_rejected(client):
    """A body this large is rejected (via the streaming body-size guard, the per-field image
    cap, or both — see test_limits.py for a guard that isolates the streaming check alone)."""
    huge_image = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2_600_000
    resp = await client.post("/v1/checks", data={"lang": "en"}, files={"image": ("x.png", huge_image, "image/png")})
    assert resp.status_code == 413
