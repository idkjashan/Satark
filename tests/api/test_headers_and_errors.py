"""Security headers, no CORS, and the generic error envelope (CONTRACTS §6, §17)."""

from __future__ import annotations

EXPECTED_HEADERS = {
    "content-security-policy": "default-src 'self'; connect-src 'self'; img-src 'self' blob: data:; "
    "media-src 'self' blob:; style-src 'self' 'unsafe-inline'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=(self), microphone=(self), geolocation=()",
}


async def test_security_headers_on_a_normal_response(client):
    resp = await client.get("/healthz")
    for key, value in EXPECTED_HEADERS.items():
        assert resp.headers[key] == value
    assert "access-control-allow-origin" not in resp.headers


async def test_security_headers_on_an_error_response(client):
    resp = await client.get("/v1/runs/missing/events")
    assert resp.status_code == 404
    for key, value in EXPECTED_HEADERS.items():
        assert resp.headers[key] == value
    assert "access-control-allow-origin" not in resp.headers


async def test_unknown_v1_path_is_json_404(client):
    resp = await client.get("/v1/unknown")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message_key"] == "error.not_found"
    assert body["error"]["retryable"] is False


async def test_every_error_body_matches_the_envelope_shape(client):
    resp = await client.post("/v1/checks", data={"text": "a" * 5000, "lang": "en"})
    body = resp.json()
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message_key", "retryable"}
    assert body["error"]["message_key"] == f"error.{body['error']['code']}"


async def test_no_cors_preflight_support(client):
    resp = await client.options("/v1/checks", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in resp.headers
