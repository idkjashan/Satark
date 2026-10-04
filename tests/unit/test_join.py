"""Joiner: the decision table (LLD §4.3, no LLM re-plan row per CONTRACTS)."""

from __future__ import annotations

from satark.harness.budget import Budget
from satark.harness.join import Joiner
from satark.harness.score import Scorer
from satark.harness.state import Evidence, SourceRef
from tests.unit.harness_fakes import FakeChecker, make_entity, make_registry


def _joiner(config, *checkers) -> Joiner:
    reg = make_registry(*checkers)
    return Joiner(reg, Scorer(config, reg), config)


def _budget(verdict_s=9, run_s=12) -> Budget:
    return Budget(verdict_deadline_s=verdict_s, run_deadline_s=run_s, tool_calls=10)


def _hit_evidence(code: str, basis: str = "registry", **kw) -> Evidence:
    from satark.harness.state import SignalHit

    return Evidence(
        id=kw.pop("id", "ev1"), step_id="s1", checker_id=kw.pop("checker_id", "c1"), family="registry",
        entity_ids=["e1"], status="hit", signals=[SignalHit(code=code, basis=basis, entity_ids=["e1"])],
        source=SourceRef(), **kw,
    )


def test_deadline_hit_finishes(make_case, config):
    j = _joiner(config)
    case = make_case()
    budget = Budget(verdict_deadline_s=0, run_deadline_s=0, tool_calls=10)
    assert j.decide(case, budget, False, 1, 0, 3) == "FINISH"


def test_max_waves_finishes(make_case, config):
    j = _joiner(config)
    case = make_case()
    assert j.decide(case, _budget(), False, 1, 3, 3) == "FINISH"


def test_high_risk_sure_three_reasons_finishes_early(make_case, config):
    j = _joiner(config)
    case = make_case()
    case.ledger = [
        _hit_evidence("DEBARRED_ENTITY", basis="registry", id="ev1"),
        _hit_evidence("ON_CAUTION_LIST", basis="official_list", id="ev2"),
        _hit_evidence("REG_NAME_MISMATCH", basis="registry", id="ev3"),
    ]
    assert j.decide(case, _budget(), False, 1, 0, 3) == "FINISH"


def test_unplanned_entity_means_next_wave(make_case, config):
    j = _joiner(config)
    case = make_case()
    case.entities = [make_entity("url", id="e1", planned=False)]
    assert j.decide(case, _budget(), False, 1, 0, 3) == "NEXT_WAVE"


def test_extraction_pending_waits(make_case, config):
    j = _joiner(config)
    case = make_case()
    case.entities = [make_entity("url", id="e1", planned=True)]
    assert j.decide(case, _budget(), True, 1, 0, 3) == "WAIT_EXTRACTION"


def test_decisive_timeout_with_time_left_retries(make_case, config):
    decisive = FakeChecker("d1", decisive=True, timeout_s=1.0, run=None)
    j = _joiner(config, decisive)
    case = make_case()
    case.entities = [make_entity("url", id="e1", planned=True)]
    case.ledger = [
        Evidence(id="ev1", step_id="s1", checker_id="d1", family="link", entity_ids=["e1"], status="unknown",
                 reason="timeout", source=SourceRef())
    ]
    assert j.decide(case, _budget(verdict_s=9, run_s=9), False, 1, 0, 3) == "NEXT_WAVE"


def test_decisive_timeout_with_no_time_left_does_not_retry(make_case, config):
    decisive = FakeChecker("d1", decisive=True, timeout_s=5.0, run=None)
    j = _joiner(config, decisive)
    case = make_case()
    case.entities = [make_entity("url", id="e1", planned=True)]
    case.ledger = [
        Evidence(id="ev1", step_id="s1", checker_id="d1", family="link", entity_ids=["e1"], status="unknown",
                 reason="timeout", source=SourceRef())
    ]
    assert j.decide(case, _budget(verdict_s=0.01, run_s=0.01), False, 1, 0, 3) == "FINISH"


def test_ambiguous_match_asks_user(make_case, config):
    j = _joiner(config)
    case = make_case()
    case.entities = [make_entity("url", id="e1", planned=True)]
    case.ledger = [
        Evidence(id="ev1", step_id="s1", checker_id="c1", family="registry", entity_ids=["e1"], status="hit",
                 flags={"AMBIGUOUS_MATCH"}, source=SourceRef(),
                 facts={"candidates": [{"reg_no": "INH000000005", "name": "Rajesh Sharma Research"},
                                        {"reg_no": "INH000000006", "name": "Sharma Rajesh Analytics"}]})
    ]
    decision = j.decide(case, _budget(), False, 1, 0, 3)
    assert decision == "ASK_USER"
    assert case.question is not None
    assert case.question.text == config.t(case.lang, "ask.which_candidate")
    assert [o.id for o in case.question.options] == ["INH000000005", "INH000000006"]
    assert case.question.options[0].label == "Rajesh Sharma Research (INH000000005)"


def test_nothing_left_finishes(make_case, config):
    j = _joiner(config)
    case = make_case()
    case.entities = [make_entity("url", id="e1", planned=True)]
    assert j.decide(case, _budget(), False, 0, 0, 3) == "FINISH"
