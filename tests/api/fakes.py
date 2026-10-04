"""A fake Runtime for tests/api/*, standing in for D's satark.harness.runtime (CONTRACTS §5)
until it lands. Mirrors the Runtime dataclass's fields and the EventBus/Orchestrator/CaseStore
contracts closely enough that satark/api/*.py cannot tell the difference.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from satark.api.deps import Busy, CaseExpired
from satark.config import Config, Settings
from satark.harness.state import CaseState, Event, Reason, Verdict, utcnow


class FakeEventBus:
    """Mirrors satark.harness.events.EventBus (CONTRACTS §5): buffered replay, then live, ends
    after done/error."""

    def __init__(self) -> None:
        self._events: dict[str, list[Event]] = {}
        self._done: set[str] = set()
        self._waiters: dict[str, list[asyncio.Event]] = {}

    def register(self, run_id: str) -> None:
        """Make the run known to `exists()` before its first event — the real EventBus must do
        the same, since the client is expected to connect right after the 202 (LLD §13)."""
        self._events.setdefault(run_id, [])

    def emit(self, run_id: str, type: str, data: dict) -> int:  # noqa: A002 - matches the contract name
        buf = self._events.setdefault(run_id, [])
        event = Event(id=len(buf) + 1, type=type, data=data)
        buf.append(event)
        if type in ("done", "error"):
            self._done.add(run_id)
        for waiter in self._waiters.pop(run_id, []):
            waiter.set()
        return event.id

    def exists(self, run_id: str) -> bool:
        return run_id in self._events

    async def subscribe(self, run_id: str, after_id: int = 0):
        idx = after_id
        while True:
            buf = self._events.get(run_id, [])
            while idx < len(buf):
                yield buf[idx]
                idx += 1
            if run_id in self._done:
                return
            waiter = asyncio.Event()
            self._waiters.setdefault(run_id, []).append(waiter)
            await waiter.wait()


class FakeCaseStore:
    """Mirrors CaseStore (CONTRACTS §5 class diagram): get/put, idle expiry."""

    def __init__(self) -> None:
        self._cases: dict[str, CaseState] = {}

    def get(self, case_id: str) -> CaseState | None:
        case = self._cases.get(case_id)
        if case is None:
            return None
        if case.expires_at < utcnow():
            return None
        return case

    def put(self, case: CaseState) -> None:
        self._cases[case.case_id] = case

    def by_content_hash(self, digest: str) -> CaseState | None:
        return None


class _RunHandle(SimpleNamespace):
    run_id: str
    case_id: str
    expires_at: object


class FakeOrchestrator:
    """Mirrors Orchestrator (CONTRACTS §5): start_check/start_chat return at once; the run
    continues as a background task emitting a realistic event sequence onto the bus."""

    def __init__(self, bus: FakeEventBus, cases: FakeCaseStore, busy: bool = False) -> None:
        self.bus = bus
        self.cases = cases
        self.busy = busy
        self._active = 0

    def active_runs(self) -> int:
        return 999 if self.busy else self._active

    def _new_case(self, lang: str, simple: bool) -> CaseState:
        case = CaseState(case_id=f"case-{uuid4().hex[:8]}", lang=lang, simple=simple, expires_at=utcnow() + timedelta(minutes=30))
        self.cases.put(case)
        return case

    async def start_check(self, inp) -> _RunHandle:
        if self.busy:
            raise Busy()
        run_id = f"run-{uuid4().hex[:8]}"
        case = self._new_case(inp.lang, inp.simple)
        case.verdict = Verdict(
            revision=1,
            level="SUSPICIOUS",
            confidence="FAIRLY_SURE",
            reasons=[Reason(code="URGENCY", weight="medium", basis="rule")],
            assurances=[],
            scam_type="T1",
            scoring_version="test",
        )
        self.cases.put(case)
        self.bus.register(run_id)
        asyncio.ensure_future(self._emit_check_sequence(run_id, case))
        return _RunHandle(run_id=run_id, case_id=case.case_id, expires_at=case.expires_at)

    async def start_chat(self, case_id, message, choice, lang, simple) -> _RunHandle:
        if self.busy:
            raise Busy()
        if case_id is not None and self.cases.get(case_id) is None:
            raise CaseExpired(case_id)
        case = self.cases.get(case_id) if case_id else self._new_case(lang, simple)
        run_id = f"run-{uuid4().hex[:8]}"
        self.bus.register(run_id)
        asyncio.ensure_future(self._emit_chat_sequence(run_id, case))
        return _RunHandle(run_id=run_id, case_id=case.case_id, expires_at=case.expires_at)

    async def _emit_check_sequence(self, run_id: str, case: CaseState) -> None:
        self._active += 1
        try:
            self.bus.emit(run_id, "stage", {"stage": "received", "t_ms": 0})
            await asyncio.sleep(0)
            self.bus.emit(run_id, "stage", {"stage": "extracting", "t_ms": 1})
            self.bus.emit(run_id, "entities", {"items": []})
            self.bus.emit(run_id, "plan", {"revision": 1, "steps": []})
            self.bus.emit(run_id, "check_result", {"step_id": "s1", "checker_id": "fake.checker", "family": "text", "status": "clear", "signals": [], "source": {"id": None, "as_on": None}, "stale": False, "cached": False})
            self.bus.emit(
                run_id,
                "verdict",
                {
                    "revision": 1,
                    "level": case.verdict.level,
                    "confidence": case.verdict.confidence,
                    "reasons": [{"code": "URGENCY", "weight": "medium", "title": "Urgency pressure", "source": {"id": None, "as_on": None}}],
                    "worth_noting": [],
                    "assurances": [],
                    "actions": ["dont_pay"],
                    "scam_type": case.verdict.scam_type,
                    "simulator": None,
                    "lesson": None,
                    "checked": [],
                    "scoring_version": "test",
                },
            )
            self.bus.emit(run_id, "explanation", {"summary": "This looks suspicious.", "reasons": [], "chips": [], "fallback_used": True, "lang": case.lang})
            self.bus.emit(run_id, "done", {"case_id": case.case_id, "timings": {}})
        finally:
            self._active -= 1

    async def _emit_chat_sequence(self, run_id: str, case: CaseState) -> None:
        self._active += 1
        try:
            self.bus.emit(run_id, "stage", {"stage": "answering", "t_ms": 0})
            await asyncio.sleep(0)
            self.bus.emit(run_id, "answer", {"text": "Here is what I found.", "cites": [], "actions": [], "chips": [], "fallback_used": True})
            self.bus.emit(run_id, "done", {"case_id": case.case_id, "timings": {}})
        finally:
            self._active -= 1


class FakeRegistry:
    def __init__(self, disabled: dict[str, str] | None = None) -> None:
        self.disabled = disabled or {}

    def all(self) -> list:
        return []


class FakeRouter:
    def status(self) -> dict[str, str]:
        return {"extract": "off", "explain": "off", "respond": "off"}


def build_fake_runtime(
    settings: Settings,
    config: Config,
    db=None,
    ready: bool = True,
    not_ready_reason: str | None = None,
    busy: bool = False,
) -> SimpleNamespace:
    bus = FakeEventBus()
    cases = FakeCaseStore()
    orchestrator = FakeOrchestrator(bus, cases, busy=busy)
    return SimpleNamespace(
        settings=settings,
        config=config,
        registry=FakeRegistry(),
        db=db,
        http=None,
        router=FakeRouter(),
        bus=bus,
        cases=cases,
        orchestrator=orchestrator,
        ready=ready,
        not_ready_reason=not_ready_reason,
    )
