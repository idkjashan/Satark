"""GET /v1/meta, /healthz, /readyz (CONTRACTS §6)."""

from __future__ import annotations

import httpx

from satark.app import create_app
from tests.api.fakes import build_fake_runtime


async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_readyz_ready(client):
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert "checkers" in body and "db_version" in body


async def test_readyz_not_ready(settings, config):
    rt = build_fake_runtime(settings, config, ready=False, not_ready_reason="registry missing")
    app = create_app(settings=settings, runtime=rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/readyz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "reason": "registry missing"}


async def test_meta_without_db(client):
    resp = await client.get("/v1/meta")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"] == []
    assert any(lang["code"] == "en" for lang in body["languages"])
    assert all(lang["code"] != "mr" for lang in body["languages"])  # disabled in config/languages.yaml
    assert body["disabled_checkers"] == []
    assert body["llm"] == {"extract": "off", "explain": "off", "respond": "off"}
    assert body["version"] == "0.1.0"
    assert "scoring_version" in body


async def test_meta_with_db_joins_sources(settings, config, fixture_db):
    rt = build_fake_runtime(settings, config, db=fixture_db)
    app = create_app(settings=settings, runtime=rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/meta")
    body = resp.json()
    assert len(body["sources"]) > 0
    row = next(s for s in body["sources"] if s["id"] == "sebi_ra")
    assert row["as_on"] == "2026-10-03"
    assert row["status"] == "ok"
    assert row["rows"] == 1


async def test_meta_reports_disabled_checkers(settings, config):
    rt = build_fake_runtime(settings, config)
    rt.registry.disabled["checker.x"] = "missing secret FOO"
    app = create_app(settings=settings, runtime=rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/v1/meta")
    assert resp.json()["disabled_checkers"] == [{"id": "checker.x", "reason": "missing secret FOO"}]
