"""Regression (code review): a ping must not end the event stream.

asyncio.wait_for cancelled the pending __anext__ on every ping timeout, which closed the subscription
generator, so the stream ended after one ping and the verdict never arrived on that connection."""

import asyncio
from types import SimpleNamespace

from satark.api import runs
from satark.harness.events import EventBus


async def test_stream_survives_pings_and_delivers_later_events(monkeypatch):
    monkeypatch.setattr(runs, "PING_SECONDS", 0.05)
    bus = EventBus()
    rt = SimpleNamespace(bus=bus)
    bus.emit("r1", "stage", {"stage": "received", "t_ms": 0})

    async def later():
        await asyncio.sleep(0.2)  # several ping intervals of silence (e.g. a slow model call)
        bus.emit("r1", "verdict", {"level": "HIGH_RISK"})
        bus.emit("r1", "done", {"case_id": "c1"})

    task = asyncio.create_task(later())
    chunks = [c async for c in runs._stream(rt, "r1", 0)]
    await task
    text = "".join(chunks)
    assert text.count(": ping") >= 2
    assert "event: verdict" in text and text.rstrip().splitlines()[-2].startswith("event: done")
