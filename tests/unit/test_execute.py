"""DagExecutor: timeouts, retries, breakers, cache, derived entities (LLD §5.3)."""

from __future__ import annotations

import asyncio

from satark.checkers.base import TransientError, clear, hit
from satark.harness.budget import Budget
from satark.harness.execute import DagExecutor
from satark.harness.state import EntityDraft, Evidence, PlanStep, SourceRef
from tests.unit.harness_fakes import FakeChecker, FakePipeline, make_entity, make_registry


class _Config:
    sources: dict = {}


def _budget(verdict_s: float = 9, run_s: float = 12, tool_calls: int = 10) -> Budget:
    return Budget(verdict_deadline_s=verdict_s, run_deadline_s=run_s, tool_calls=tool_calls)


def _executor(*checkers, db=None, http=None, network: bool = True, config=None) -> DagExecutor:
    return DagExecutor(make_registry(*checkers), config or _Config(), FakePipeline(), db=db, http=http, network=network)


def _step(checker_id: str, entity_id: str = "e1", family: str = "link") -> PlanStep:
    return PlanStep(id="s1", checker_id=checker_id, entity_ids=[entity_id], family=family)


def _returns(result):
    """`FakeChecker.check()` awaits `run(...)`, so a fixed-result fake must still be async."""

    async def _run(entity, ctx):
        return result

    return _run


async def _run_one(executor: DagExecutor, step: PlanStep, case, budget) -> Evidence:
    evs = [ev async for ev in executor.run([step], case, budget)]
    assert len(evs) == 1
    return evs[0]


async def test_slow_checker_times_out_as_unknown(make_case):
    async def sleepy(entity, ctx):
        await asyncio.sleep(1.0)
        return clear()

    checker = FakeChecker("slow", timeout_s=0.02, run=sleepy)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    ev = await _run_one(_executor(checker), _step("slow"), case, _budget())

    assert ev.status == "unknown"
    assert ev.reason == "timeout"
    assert case.ledger == [ev]


async def test_transient_error_retries_once_then_succeeds(make_case):
    calls = {"n": 0}

    async def flaky(entity, ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransientError("connection reset")
        return clear("UPI_VALID_HANDLE")

    checker = FakeChecker("flaky", produces=frozenset({"UPI_VALID_HANDLE"}), run=flaky)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    ev = await _run_one(_executor(checker), _step("flaky"), case, _budget())

    assert calls["n"] == 2
    assert ev.status == "clear"


async def test_transient_error_with_no_time_left_gives_up(make_case):
    async def always_transient(entity, ctx):
        raise TransientError("down")

    checker = FakeChecker("flaky", timeout_s=1.0, run=always_transient)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    # run_deadline barely bigger than timeout_s so "budget.run_left() <= checker.timeout_s" after the first failure
    ev = await _run_one(_executor(checker), _step("flaky"), case, _budget(verdict_s=1.0, run_s=1.05))

    assert ev.status == "unknown"
    assert ev.reason == "timeout"


async def test_checker_exception_becomes_error(make_case):
    async def boom(entity, ctx):
        raise ValueError("bug")

    checker = FakeChecker("buggy", run=boom)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    ev = await _run_one(_executor(checker), _step("buggy"), case, _budget())

    assert ev.status == "error"
    assert ev.reason == "checker_error"


async def test_undeclared_signal_becomes_contract_error(make_case):
    async def sneaky(entity, ctx):
        return hit("NOT_DECLARED")

    checker = FakeChecker("sneaky", produces=frozenset({"OTHER_CODE"}), run=sneaky)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    ev = await _run_one(_executor(checker), _step("sneaky"), case, _budget())

    assert ev.status == "error"
    assert ev.reason == "contract"


async def test_breaker_opens_after_five_consecutive_failures(make_case):
    async def always_fails(entity, ctx):
        raise TransientError("down")

    checker = FakeChecker("flaky", source="rdap", timeout_s=0.3, run=always_fails)
    case = make_case()
    executor = _executor(checker)
    budget = _budget(verdict_s=0.05, run_s=0.06)  # shorter than timeout_s, so no retry hides a failure

    statuses = []
    for i in range(6):
        entity_id = f"e{i}"
        case.entities.append(make_entity("url", id=entity_id, value=f"x{i}.test"))
        ev = await _run_one(executor, _step("flaky", entity_id=entity_id), case, budget)
        statuses.append(ev.reason)

    # the 6th call finds the breaker already open from the first 5 consecutive failures
    assert statuses[:5] == ["timeout"] * 5
    assert statuses[5] == "source_unavailable"


async def test_rate_limit_without_a_free_token_is_unknown(make_case):
    async def ok(entity, ctx):
        return clear()

    checker = FakeChecker("limited", source="tranco", run=ok)
    case = make_case()
    case.entities = [make_entity("url", id="e1"), make_entity("url", id="e2", value="b.test")]
    config = _Config()
    config.sources = {"tranco": {"rate": "1/5s"}}
    executor = _executor(checker, config=config)
    budget = _budget()

    first = await _run_one(executor, _step("limited", "e1"), case, budget)
    second = await _run_one(executor, _step("limited", "e2"), case, budget)

    assert first.status == "clear"
    assert second.status == "unknown"
    assert second.reason == "rate_limited"


async def test_cache_hit_is_marked_cached_and_skips_the_call(make_case):
    calls = {"n": 0}

    async def counted(entity, ctx):
        calls["n"] += 1
        return clear("DOMAIN_OLD")

    checker = FakeChecker("cached", produces=frozenset({"DOMAIN_OLD"}), cache_ttl_s=60, run=counted)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    executor = _executor(checker)
    budget = _budget()

    first = await _run_one(executor, _step("cached"), case, budget)
    second_step = PlanStep(id="s2", checker_id="cached", entity_ids=["e1"], family="link")
    second = await _run_one(executor, second_step, case, budget)

    assert calls["n"] == 1
    assert first.cached is False
    assert second.cached is True
    assert second.status == "clear"


async def test_needs_http_offline_is_unknown_without_calling(make_case):
    async def never(entity, ctx):  # pragma: no cover
        raise AssertionError("must not be called when offline")

    checker = FakeChecker("net", needs=("http",), run=never)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    ev = await _run_one(_executor(checker, network=False), _step("net"), case, _budget())

    assert ev.status == "unknown"
    assert ev.reason == "offline"


async def test_needs_db_missing_is_unknown(make_case):
    checker = FakeChecker("needs_db", needs=("db",), run=_returns(clear()))
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    ev = await _run_one(_executor(checker, db=None), _step("needs_db"), case, _budget())

    assert ev.status == "unknown"
    assert ev.reason == "source_missing"


async def test_derived_entities_are_added_via_pipeline(make_case):
    async def derives(entity, ctx):
        return hit("URL_SHORTENED", derived=[EntityDraft(type="domain", value="final.example")])

    checker = FakeChecker("unshorten", produces=frozenset({"URL_SHORTENED"}), run=derives)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    case.counters["e"] = 1  # the fake entity above was hand-built, not minted via case.next_id
    pipeline = FakePipeline()
    executor = DagExecutor(make_registry(checker), _Config(), pipeline, network=True)

    ev = await _run_one(executor, _step("unshorten"), case, _budget())

    assert ev.derived_ids and case.entity(ev.derived_ids[0]).type == "domain"
    assert pipeline.added_drafts[0].value == "final.example"


async def test_deadline_mid_wave_marks_unfinished_steps_unknown(make_case):
    async def forever(entity, ctx):
        await asyncio.sleep(5)
        return clear()  # pragma: no cover

    fast = FakeChecker("fast", timeout_s=2, run=_returns(clear()))
    slow = FakeChecker("slow", timeout_s=2, run=forever)
    case = make_case()
    case.entities = [make_entity("url", id="e1"), make_entity("url", id="e2", value="b.test")]
    executor = _executor(fast, slow)
    # run deadline is the tight one here: each checker's own timeout_s is clamped to verdict_left(),
    # so a plenty of verdict time + a tiny run time is what makes the *wave* timeout fire first.
    budget = _budget(verdict_s=2.0, run_s=0.05)

    evs = [
        ev
        async for ev in executor.run(
            [_step("fast", "e1"), _step("slow", "e2")],
            case,
            budget,
        )
    ]

    assert {ev.checker_id: ev.status for ev in evs} == {"fast": "clear", "slow": "unknown"}
    slow_ev = next(ev for ev in evs if ev.checker_id == "slow")
    assert slow_ev.reason == "deadline"


async def test_unmet_dependency_is_skipped(make_case):
    checker = FakeChecker("dep", run=_returns(clear()))
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    step = PlanStep(id="s1", checker_id="dep", entity_ids=["e1"], family="link", depends_on=["s0-never"])

    evs = [ev async for ev in _executor(checker).run([step], case, _budget())]

    assert evs[0].status == "skipped"
    assert evs[0].reason == "unmet_dependency"


async def test_stale_when_source_older_than_max_age(make_case):
    checker = FakeChecker("src", run=_returns(clear(source=SourceRef(id="old_src", as_on="2000-01-01"))))
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    config = _Config()
    config.sources = {"old_src": {"max_age_days": 30}}
    ev = await _run_one(_executor(checker, config=config), _step("src"), case, _budget())

    assert ev.stale is True
