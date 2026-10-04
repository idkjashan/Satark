"""POST /v1/feedback (CONTRACTS §6)."""

from __future__ import annotations


async def test_happy_path_helpful(client):
    resp = await client.post("/v1/feedback", json={"kind": "helpful"})
    assert resp.status_code == 204
    assert resp.content == b""


async def test_happy_path_mistake_with_reason_codes(client):
    resp = await client.post(
        "/v1/feedback", json={"case_id": "case-1", "kind": "mistake", "level": "HIGH_RISK", "reason_codes": ["REG_NOT_FOUND"]}
    )
    assert resp.status_code == 204


async def test_invalid_kind_is_422(client):
    resp = await client.post("/v1/feedback", json={"kind": "not_a_real_kind"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


async def test_missing_kind_is_422(client):
    resp = await client.post("/v1/feedback", json={})
    assert resp.status_code == 422
