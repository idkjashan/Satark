"""DagExecutor: runs a wave of plan steps concurrently, with timeouts, retries, circuit breakers,
rate limits and a TTL result cache (LLD §5.3).

`depends_on` is honoured (sub-waves within one `run()` call) even though `RulePlanner` never sets
it today — only a future LLM planner would — so that field is not a silent no-op if one lands.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date

from satark.checkers.base import CheckContext, TransientError
from satark.checkers.registry import CheckerRegistry
from satark.harness.budget import Budget
from satark.harness.state import CaseState, CheckResult, Evidence, PlanStep, SourceRef

log = logging.getLogger(__name__)

_BREAKER_FAILS_TO_OPEN = 5
_BREAKER_OPEN_S = 30.0
_RATE_WAIT_S = 0.2

_STEP_STATUS = {"hit": "done", "clear": "done", "unknown": "unknown", "error": "unknown", "skipped": "skipped"}


def _unknown(reason: str) -> CheckResult:
    return CheckResult(status="unknown", reason=reason)


@dataclass
class _Breaker:
    fails: int = 0
    opened_at: float | None = None

    def allow(self) -> bool:
        # note: a global per-source flag, not a single-slot semaphore, so several steps that
        # all land right as the 30s window ends can probe concurrently instead of just one. Add a
        # "probing" bool here if a source ever gets hammered by a whole wave at reopen time.
        if self.opened_at is None:
            return True
        return time.monotonic() - self.opened_at >= _BREAKER_OPEN_S

    def record(self, ok: bool) -> None:
        if ok:
            self.fails, self.opened_at = 0, None
        else:
            self.fails += 1
            if self.fails >= _BREAKER_FAILS_TO_OPEN:
                self.opened_at = time.monotonic()


@dataclass
class _Bucket:
    capacity: float
    refill_per_s: float
    tokens: float
    updated: float

    def take(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_s)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


def _parse_rate(rate: str) -> _Bucket:
    """"1/5s" -> 1 token / 5s; "3/s" -> 3 tokens / s. note: seconds only; extend if a source needs minutes/days."""
    n, _, per = rate.partition("/")
    secs = 1.0 if per in ("s", "") else float(per[:-1])
    tokens = float(n)
    return _Bucket(capacity=max(tokens, 1.0), refill_per_s=tokens / secs, tokens=tokens, updated=time.monotonic())


class SourceGuard:
    """Per-source circuit breaker + token bucket (LLD §5.3)."""

    def __init__(self, sources_cfg: dict[str, dict] | None = None) -> None:
        self._cfg = sources_cfg or {}
        self._breakers: dict[str, _Breaker] = {}
        self._buckets: dict[str, _Bucket] = {}

    def breaker_allows(self, source_id: str | None) -> bool:
        return source_id is None or self._breakers.setdefault(source_id, _Breaker()).allow()

    def record(self, source_id: str | None, ok: bool) -> None:
        if source_id is not None:
            self._breakers.setdefault(source_id, _Breaker()).record(ok)

    async def take_rate(self, source_id: str | None) -> bool:
        if source_id is None:
            return True
        rate = (self._cfg.get(source_id) or {}).get("rate")
        if not rate:
            return True
        bucket = self._buckets.setdefault(source_id, _parse_rate(rate))
        deadline = time.monotonic() + _RATE_WAIT_S
        while not bucket.take():
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(0.02)
        return True


class ResultCache:
    """TTL cache keyed (checker id, norm_hash, data_version); only hit/clear are cached (LLD §14.4)."""

    def __init__(self) -> None:
        self._store: dict[tuple, tuple[float | None, CheckResult]] = {}

    def get(self, key: tuple) -> CheckResult | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, result = entry
        if expires_at is not None and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return result

    def put(self, key: tuple, result: CheckResult, ttl_s: int) -> None:
        if ttl_s == 0 or result.status not in ("hit", "clear"):
            return
        self._store[key] = (None if ttl_s < 0 else time.monotonic() + ttl_s, result)


class DagExecutor:
    def __init__(
        self,
        registry: CheckerRegistry,
        config,
        pipeline,
        db=None,
        http=None,
        secrets: dict | None = None,
        network: bool = True,
    ) -> None:
        self.registry = registry
        self.config = config
        self.pipeline = pipeline  # ExtractorPipeline-shaped: .add_drafts(case, drafts) -> list[Entity]
        self.db = db
        self.http = http
        self.secrets = secrets or {}
        self.network = network
        self.guard = SourceGuard(getattr(config, "sources", None))
        self.cache = ResultCache()

    async def run(self, steps: list[PlanStep], case: CaseState, budget: Budget) -> AsyncIterator[Evidence]:
        pending = list(steps)
        done_ids: set[str] = set()
        while pending:
            ready = [s for s in pending if set(s.depends_on) <= done_ids]
            if not ready:  # a cycle, or a dependency that will never finish this run
                for s in pending:
                    s.status = "skipped"
                    yield self._evidence(s, CheckResult(status="skipped", reason="unmet_dependency"), case, time.monotonic())
                return
            pending = [s for s in pending if s not in ready]
            async for ev in self._run_wave(ready, case, budget):
                done_ids.add(ev.step_id)
                yield ev

    async def _run_wave(self, ready: list[PlanStep], case: CaseState, budget: Budget) -> AsyncIterator[Evidence]:
        for s in ready:
            s.status = "running"
        tasks = {asyncio.create_task(self._run_step(s, case, budget)): s for s in ready}
        remaining = set(tasks)
        while remaining:
            wait_s = max(0.0, min(budget.verdict_left(), budget.run_left()))
            done, remaining = await asyncio.wait(remaining, timeout=wait_s, return_when=asyncio.FIRST_COMPLETED)
            if not done:  # the deadline hit with tasks still in flight
                for t in remaining:
                    t.cancel()
                await asyncio.gather(*remaining, return_exceptions=True)
                for t in remaining:
                    step = tasks[t]
                    step.status = "unknown"
                    yield self._evidence(step, _unknown("deadline"), case, time.monotonic())
                return
            for t in done:
                step = tasks[t]
                ev = t.result()
                step.status = _STEP_STATUS[ev.status]
                yield ev

    async def _run_step(self, step: PlanStep, case: CaseState, budget: Budget) -> Evidence:
        start = time.monotonic()
        checker = self.registry.get(step.checker_id)
        entity = case.entity(step.entity_ids[0]) if step.entity_ids else None
        if checker is None or entity is None:
            return self._evidence(step, CheckResult(status="error", reason="contract"), case, start)

        # no content hash (claims, synthetic entities) = no cache: an entity id is only unique inside one case
        key = (checker.id, entity.norm_hash, self.db.data_version if self.db is not None else 0) if entity.norm_hash else None
        cached = self.cache.get(key) if key else None
        if cached is not None:
            return self._evidence(step, cached, case, start, cached=True)

        if "http" in checker.needs and not self.network:
            return self._evidence(step, _unknown("offline"), case, start)
        if "db" in checker.needs and self.db is None:
            return self._evidence(step, _unknown("source_missing"), case, start)
        if not budget.take(checker.cost):
            return self._evidence(step, CheckResult(status="skipped", reason="budget"), case, start)
        if not self.guard.breaker_allows(checker.source):
            return self._evidence(step, _unknown("source_unavailable"), case, start)
        if not await self.guard.take_rate(checker.source):
            return self._evidence(step, _unknown("rate_limited"), case, start)

        ctx = CheckContext(case=case, config=self.config, db=self.db, http=self.http, secrets=self.secrets)
        result = await self._call(checker, entity, ctx, budget)
        if result is None:  # timed out or failed with no time left to retry
            return self._evidence(step, _unknown("timeout"), case, start)
        if isinstance(result, CheckResult) and result.status == "error":
            return self._evidence(step, result, case, start)

        produced = {sig.code for sig in result.signals} | set(result.flags)
        if not produced <= checker.produces:
            log.error("checker %s produced undeclared codes %s", checker.id, produced - checker.produces)
            return self._evidence(step, CheckResult(status="error", reason="contract"), case, start)

        if key:
            self.cache.put(key, result, checker.cache_ttl_s)
        derived_ids = [e.id for e in self.pipeline.add_drafts(case, result.derived)] if result.derived else []
        return self._evidence(step, result, case, start, stale=self._is_stale(result.source), derived_ids=derived_ids)

    async def _call(self, checker, entity, ctx: CheckContext, budget: Budget) -> CheckResult | None:
        """Runs the checker once, with one retry on `TransientError` if time remains. None = give up."""
        timeout_s = max(0.0, min(checker.timeout_s, budget.verdict_left()))
        try:
            result = await asyncio.wait_for(checker.check(entity, ctx), timeout=timeout_s)
        except TimeoutError:
            self.guard.record(checker.source, False)
            return None
        except TransientError:
            self.guard.record(checker.source, False)
            if budget.run_left() <= checker.timeout_s:
                return None
            retry_timeout = max(0.0, min(checker.timeout_s, budget.verdict_left()))
            try:
                result = await asyncio.wait_for(checker.check(entity, ctx), timeout=retry_timeout)
            except Exception:
                return None
        except Exception:
            log.error("checker %s raised", checker.id, exc_info=True)
            return CheckResult(status="error", reason="checker_error")
        self.guard.record(checker.source, True)
        return result

    def _is_stale(self, source: SourceRef) -> bool:
        max_age = ((self.config.sources if self.config else {}) or {}).get(source.id or "", {}).get("max_age_days")
        if not max_age or not source.as_on:
            return False
        try:
            age_days = (date.today() - date.fromisoformat(source.as_on)).days
        except ValueError:
            return False
        return age_days > max_age

    def _evidence(
        self,
        step: PlanStep,
        result: CheckResult,
        case: CaseState,
        start: float,
        *,
        cached: bool = False,
        stale: bool = False,
        derived_ids: list[str] | None = None,
    ) -> Evidence:
        ev = Evidence(
            id=case.next_id("ev"),
            step_id=step.id,
            checker_id=step.checker_id,
            family=step.family,
            entity_ids=step.entity_ids,
            status=result.status,
            facts=result.facts,
            signals=result.signals,
            flags=result.flags,
            derived_ids=derived_ids or [],
            source=result.source,
            reason=result.reason,
            stale=stale,
            cached=cached,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        case.ledger.append(ev)
        return ev
