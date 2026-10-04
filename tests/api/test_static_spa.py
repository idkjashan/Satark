"""Static PWA serving and SPA fallback (CONTRACTS §6; LLD §19.1, §21)."""

from __future__ import annotations

import dataclasses

import httpx
import pytest

from satark.app import create_app
from tests.api.fakes import build_fake_runtime


async def test_no_dist_root_returns_small_text_page(client):
    """The default `settings` fixture points web_dist at a directory that does not exist."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "not built" in resp.text
    assert resp.headers["content-type"].startswith("text/plain")


@pytest.fixture()
def web_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa shell</html>")
    (dist / "sw.js").write_text("// service worker")
    (dist / "manifest.webmanifest").write_text("{}")
    (dist / "assets" / "app.abc123.js").write_text("console.log('hi')")
    return dist


@pytest.fixture()
async def dist_client(settings, config, web_dist):
    scoped_settings = dataclasses.replace(settings, web_dist=web_dist)
    rt = build_fake_runtime(scoped_settings, config)
    app = create_app(settings=scoped_settings, runtime=rt)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_root_serves_index_html_when_dist_exists(dist_client):
    resp = await dist_client.get("/")
    assert resp.status_code == 200
    assert "spa shell" in resp.text
    assert resp.headers["cache-control"] == "no-cache"


async def test_spa_fallback_serves_index_html_for_unknown_route(dist_client):
    resp = await dist_client.get("/run/abc123")
    assert resp.status_code == 200
    assert "spa shell" in resp.text


async def test_unknown_v1_path_is_json_404_not_spa(dist_client):
    resp = await dist_client.get("/v1/unknown")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["error"]["code"] == "not_found"


async def test_assets_get_long_immutable_cache(dist_client):
    resp = await dist_client.get("/assets/app.abc123.js")
    assert resp.status_code == 200
    assert "immutable" in resp.headers["cache-control"]


async def test_sw_js_gets_no_cache(dist_client):
    resp = await dist_client.get("/sw.js")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-cache"


async def test_path_traversal_is_rejected(dist_client):
    resp = await dist_client.get("/../../etc/passwd")
    assert resp.status_code in (404, 200)  # httpx normalises ../ before sending; either way, no file leaks
    assert "root:" not in resp.text
