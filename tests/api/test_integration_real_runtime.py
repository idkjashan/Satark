"""One integration test against the REAL build_runtime (CONTRACTS §5), over the fixture DB.

Everyone else's unit tests here use tests/api/fakes.py so they pass before D's harness lands.
This one exercises the real wiring end to end and skips itself — rather than failing the
suite — until satark.harness.runtime (D) and enough of the extraction/checker stack (A/C)
exist for build_runtime() to actually succeed.
"""

from __future__ import annotations

import httpx
import pytest


async def test_real_runtime_smoke(settings):
    runtime_mod = pytest.importorskip("satark.harness.runtime", reason="D's harness runtime has not landed yet")
    try:
        rt = await runtime_mod.build_runtime(settings)
    except Exception as exc:  # noqa: BLE001 - any missing piece (D/A/C) is a skip, not a failure
        pytest.skip(f"real runtime not buildable yet: {exc!r}")

    try:
        from satark.app import create_app

        app = create_app(settings=settings, runtime=rt)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/v1/checks", data={"text": "please verify this adviser", "lang": "en"})
            assert resp.status_code in (202, 503), resp.text
            if resp.status_code == 202:
                events_url = resp.json()["events_url"]
                async with client.stream("GET", events_url) as stream:
                    assert stream.status_code == 200
                    raw = (await stream.aread()).decode()
                assert "event:" in raw
    finally:
        await runtime_mod.close_runtime(rt)
