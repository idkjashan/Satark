"""EventBus: per-run ordered SSE events with reconnect replay (CONTRACTS §5, LLD §12.3).

`emit` is synchronous per the contract, so a live subscriber blocked in `subscribe` is woken with
a plain `asyncio.Future` "waiter" resolved in place — not `asyncio.Condition`, whose `notify()`
requires the caller to already hold its lock, which only an `async` caller can acquire. Since the
whole harness runs on one event loop (LLD §3.7), a synchronous `set_result()` from `emit` is safe
and wakes the waiting `subscribe()` coroutine on its next turn.

`RunRegistry` keeps a reference to each run's `asyncio.Task` so it is never garbage-collected
mid-run, and is the source of truth for `Orchestrator.active_runs()`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from satark.harness.state import Event

PURGE_AFTER_S = 300.0  # events are kept 5 minutes after a run ends (LLD §14.4)
_END_TYPES = frozenset({"done", "error"})


class _Run:
    __slots__ = ("events", "waiters", "ended_at")

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.waiters: list[asyncio.Future[None]] = []
        self.ended_at: float | None = None


class EventBus:
    def __init__(self) -> None:
        self._runs: dict[str, _Run] = {}

    def _sweep(self) -> None:
        now = time.monotonic()
        dead = [rid for rid, run in self._runs.items() if run.ended_at is not None and now - run.ended_at > PURGE_AFTER_S]
        for rid in dead:
            del self._runs[rid]

    def emit(self, run_id: str, type: str, data: dict) -> int:  # noqa: A002 (CONTRACTS names it `type`)
        self._sweep()
        run = self._runs.setdefault(run_id, _Run())
        event = Event(id=len(run.events) + 1, type=type, data=data)
        run.events.append(event)
        if type in _END_TYPES and run.ended_at is None:
            run.ended_at = time.monotonic()
        waiters, run.waiters = run.waiters, []
        for fut in waiters:
            if not fut.done():
                fut.set_result(None)
        return event.id

    async def subscribe(self, run_id: str, after_id: int = 0) -> AsyncIterator[Event]:
        self._sweep()
        last = after_id
        while True:
            run = self._runs.get(run_id)
            if run is None:
                return
            for event in run.events:
                if event.id > last:
                    last = event.id
                    yield event
                    if event.type in _END_TYPES:
                        return
            if run.ended_at is not None:
                return
            fut: asyncio.Future[None] = asyncio.get_event_loop().create_future()
            run.waiters.append(fut)
            await fut

    def exists(self, run_id: str) -> bool:
        self._sweep()
        return run_id in self._runs


class RunRegistry:
    """Keeps each run's asyncio task referenced (no GC) and counts active runs."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def add(self, run_id: str, task: asyncio.Task) -> None:
        self._tasks[run_id] = task
        task.add_done_callback(lambda _t, rid=run_id: self._tasks.pop(rid, None))

    def get(self, run_id: str) -> asyncio.Task | None:
        return self._tasks.get(run_id)

    def count(self) -> int:
        return len(self._tasks)
