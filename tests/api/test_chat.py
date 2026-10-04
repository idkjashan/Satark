"""POST /v1/chat (CONTRACTS §6)."""

from __future__ import annotations

import httpx

from satark.app import create_app
from tests.api.fakes import build_fake_runtime


async def test_happy_path_new_case(client):
    resp = await client.post("/v1/chat", json={"message": "is this safe?", "lang": "en"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["run_id"] and body["case_id"] and body["events_url"].endswith("/events")


async def test_happy_path_choice(client):
    checks_resp = await client.post("/v1/checks", data={"text": "hello world", "lang": "en"})
    case_id = checks_resp.json()["case_id"]
    resp = await client.post(
        "/v1/chat", json={"case_id": case_id, "choice": {"question_id": "q1", "option_id": "a"}, "lang": "en"}
    )
    assert resp.status_code == 202


async def test_case_expired(client):
    resp = await client.post("/v1/chat", json={"case_id": "no-such-case", "message": "hi", "lang": "en"})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "case_expired"


async def test_message_too_large(client):
    resp = await client.post("/v1/chat", json={"message": "a" * 1001, "lang": "en"})
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "input_too_large"


async def test_nothing_to_check(client):
    resp = await client.post("/v1/chat", json={"lang": "en"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "nothing_to_check"


async def test_bad_language(client):
    resp = await client.post("/v1/chat", json={"message": "hi", "lang": "xx"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "bad_language"


async def test_busy(settings, config):
    rt = build_fake_runtime(settings, config, busy=True)
    app = create_app(settings=settings, runtime=rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/chat", json={"message": "hi", "lang": "en"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "busy"
    assert resp.headers["retry-after"] == "5"


async def test_not_ready(settings, config):
    rt = build_fake_runtime(settings, config, ready=False, not_ready_reason="still loading")
    app = create_app(settings=settings, runtime=rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/chat", json={"message": "hi", "lang": "en"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "not_ready"
