"""RulePlanner: dedupe, privacy filter, budget cut, decisive-first (LLD §4.2)."""

from __future__ import annotations

from satark.harness.budget import Budget
from satark.harness.plan import RulePlanner
from satark.harness.state import Evidence, SourceRef
from tests.unit.harness_fakes import FakeChecker, make_entity, make_registry


def _budget(tool_calls: int = 10) -> Budget:
    return Budget(verdict_deadline_s=9, run_deadline_s=12, tool_calls=tool_calls)


async def _noop(entity, ctx):  # pragma: no cover - never actually called by the planner
    raise AssertionError("the planner must not call checkers")


def test_plans_one_step_per_consumer_in_entity_order(make_case, config):
    url_checker = FakeChecker("link.rdap", family="link", consumes=frozenset({"url"}), run=_noop)
    reg = make_registry(url_checker)
    planner = RulePlanner(reg, config)
    case = make_case()
    case.entities = [make_entity("url", id="e1", value="a.test"), make_entity("url", id="e2", value="b.test")]

    steps = planner.plan(case, "check", _budget())

    assert [s.entity_ids for s in steps] == [["e1"], ["e2"]]
    assert all(s.checker_id == "link.rdap" and s.family == "link" for s in steps)
    assert case.plan.steps == steps
    assert case.plan.revision == 1
    assert all(e.planned for e in case.entities)


def test_second_plan_call_ignores_already_planned_entities(make_case, config):
    reg = make_registry(FakeChecker("link.rdap", consumes=frozenset({"url"}), run=_noop))
    planner = RulePlanner(reg, config)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]
    first = planner.plan(case, "check", _budget())
    second = planner.plan(case, "check", _budget())
    assert len(first) == 1
    assert second == []
    assert case.plan.revision == 2


def test_dedupes_against_existing_ledger_entry(make_case, config):
    reg = make_registry(FakeChecker("link.rdap", consumes=frozenset({"url"}), run=_noop))
    planner = RulePlanner(reg, config)
    case = make_case()
    entity = make_entity("url", id="e1")
    case.entities = [entity]
    case.ledger.append(
        Evidence(id="ev1", step_id="s0", checker_id="link.rdap", family="link", entity_ids=["e1"], status="clear",
                 source=SourceRef())
    )

    steps = planner.plan(case, "check", _budget())

    assert steps == []
    assert entity.planned is True


def test_privacy_filter_excludes_disallowed_checkers(make_case, config):
    # "check" mode allows local + public_only only (config/modes.yaml); identifier must be excluded.
    local_checker = FakeChecker("a.local", consumes=frozenset({"url"}), privacy="local", run=_noop)
    identifier_checker = FakeChecker("b.identifier", consumes=frozenset({"url"}), privacy="identifier", run=_noop)
    reg = make_registry(local_checker, identifier_checker)
    planner = RulePlanner(reg, config)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]

    steps = planner.plan(case, "check", _budget())

    assert [s.checker_id for s in steps] == ["a.local"]


def test_should_run_false_skips_the_step(make_case, config):
    reg = make_registry(FakeChecker("a", consumes=frozenset({"url"}), run=_noop, should_run_fn=lambda e, c: False))
    planner = RulePlanner(reg, config)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]

    steps = planner.plan(case, "check", _budget())

    assert steps == []


def test_budget_cut_keeps_decisive_checker_first(make_case, config):
    # decisive checkers sort first within consumers_of, so a budget of 1 keeps the decisive one.
    decisive = FakeChecker("d.decisive", consumes=frozenset({"url"}), decisive=True, cost=1, run=_noop)
    cheap = FakeChecker("z.cheap", consumes=frozenset({"url"}), decisive=False, cost=1, run=_noop)
    reg = make_registry(cheap, decisive)
    planner = RulePlanner(reg, config)
    case = make_case()
    case.entities = [make_entity("url", id="e1")]

    steps = planner.plan(case, "check", _budget(tool_calls=1))

    assert [s.checker_id for s in steps] == ["d.decisive"]


def test_budget_cut_across_multiple_entities(make_case, config):
    reg = make_registry(FakeChecker("a", consumes=frozenset({"url"}), run=_noop))
    planner = RulePlanner(reg, config)
    case = make_case()
    case.entities = [make_entity("url", id="e1"), make_entity("url", id="e2", value="b.test")]

    steps = planner.plan(case, "check", _budget(tool_calls=1))

    assert len(steps) == 1
    assert steps[0].entity_ids == ["e1"]
    # both entities are still marked planned even though only one step survived the cut
    assert all(e.planned for e in case.entities)
