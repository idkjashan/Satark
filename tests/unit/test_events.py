"""EventBus: ordering, replay-after-id, end-on-done/error, purge (CONTRACTS §5, LLD §12.3)."""

from __future__ import annotations

import asyncio

from satark.harness import events as events_mod
from satark.harness.events import EventBus, RunRegistry


def test_emit_ids_increase_from_one():
    bus = EventBus()
    assert bus.emit("r1", "stage", {"stage": "received"}) == 1
    assert bus.emit("r1", "stage", {"stage": "extracting"}) == 2
    assert bus.emit("r1", "done", {"case_id": "c1"}) == 3


def test_exists_false_for_unknown_run():
    bus = EventBus()
    assert bus.exists("nope") is False
    bus.emit("r1", "stage", {})
    assert bus.exists("r1") is True


async def test_subscribe_replays_buffered_then_ends_on_done():
    bus = EventBus()
    bus.emit("r1", "stage", {"stage": "received"})
    bus.emit("r1", "entities", {"items": []})
    bus.emit("r1", "done", {"case_id": "c1"})
    out = [ev async for ev in bus.subscribe("r1")]
    assert [e.type for e in out] == ["stage", "entities", "done"]
    assert [e.id for e in out] == [1, 2, 3]


async def test_subscribe_replay_after_id_skips_already_seen():
    bus = EventBus()
    bus.emit("r1", "a", {})  # id 1
    bus.emit("r1", "b", {})  # id 2
    bus.emit("r1", "c", {})  # id 3
    bus.emit("r1", "done", {})  # id 4
    out = [ev async for ev in bus.subscribe("r1", after_id=1)]
    assert [e.id for e in out] == [2, 3, 4]


async def test_subscribe_waits_for_live_events_then_ends_on_error():
    bus = EventBus()
    bus.emit("r1", "stage", {})
    received: list[str] = []

    async def collect():
        async for ev in bus.subscribe("r1"):
            received.append(ev.type)

    task = asyncio.create_task(collect())
    await asyncio.sleep(0)  # let it replay the buffered "stage" and start waiting
    bus.emit("r1", "check_result", {})
    bus.emit("r1", "error", {"code": "internal"})
    await asyncio.wait_for(task, timeout=1)
    assert received == ["stage", "check_result", "error"]


async def test_subscribe_on_unknown_run_ends_immediately():
    bus = EventBus()
    out = [ev async for ev in bus.subscribe("nope")]
    assert out == []


def test_purge_after_run_ends(monkeypatch):
    bus = EventBus()
    monkeypatch.setattr(events_mod, "PURGE_AFTER_S", 0.0)
    bus.emit("r1", "done", {})
    assert bus.exists("r1") is False  # swept on the next call now that it's "5 minutes" old


async def test_run_registry_tracks_active_count():
    reg = RunRegistry()

    async def noop():
        await asyncio.sleep(0.02)

    task = asyncio.create_task(noop())
    reg.add("r1", task)
    assert reg.count() == 1
    assert reg.get("r1") is task
    await task
    await asyncio.sleep(0)  # let the done-callback fire
    assert reg.count() == 0
