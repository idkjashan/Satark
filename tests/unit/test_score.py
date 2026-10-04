"""Scorer: table-driven cases from LLD §6.1 / config/scoring.yaml."""

from __future__ import annotations

from satark.harness.score import Scorer, verdict_event
from satark.harness.state import Evidence, SignalHit, SourceRef


def _ev(code: str, status: str = "hit", basis: str = "rule", *, entity_ids=None, checker_id="c1", stale=False,
        flags=None, facts=None, source=None) -> Evidence:
    signals = [SignalHit(code=code, basis=basis, entity_ids=entity_ids or ["e1"])] if code else []
    return Evidence(
        id=f"ev-{code}-{checker_id}-{status}", step_id="s1", checker_id=checker_id, family="link",
        entity_ids=entity_ids or ["e1"], status=status, signals=signals, flags=flags or set(),
        facts=facts or {}, source=source or SourceRef(), stale=stale,
    )


def test_critical_alone_is_high_risk_and_sure(config):
    scorer = Scorer(config)
    case_ledger = [_ev("DEBARRED_ENTITY", basis="registry")]
    v = scorer.score(_case(case_ledger))
    assert v.level == "HIGH_RISK"
    assert v.confidence == "SURE"
    assert [r.code for r in v.reasons] == ["DEBARRED_ENTITY"]


def test_two_high_is_high_risk(config):
    scorer = Scorer(config)
    ledger = [_ev("REG_NOT_FOUND", basis="rule", checker_id="c1"), _ev("DOMAIN_LOOKALIKE", basis="rule", checker_id="c2")]
    v = scorer.score(_case(ledger))
    assert v.level == "HIGH_RISK"
    assert v.confidence == "FAIRLY_SURE"  # 2 deciding signals, both basis=rule


def test_one_high_is_suspicious(config):
    scorer = Scorer(config)
    v = scorer.score(_case([_ev("REG_NOT_FOUND", basis="rule")]))
    assert v.level == "SUSPICIOUS"
    assert v.confidence == "NOT_SURE"  # only 1 deciding signal, basis=rule


def test_two_medium_is_suspicious(config):
    scorer = Scorer(config)
    ledger = [_ev("DOMAIN_YOUNG", checker_id="c1"), _ev("QR_MCC_NOT_SECURITIES", checker_id="c2")]
    v = scorer.score(_case(ledger))
    assert v.level == "SUSPICIOUS"


def test_one_medium_is_no_signs_and_worth_noting(config):
    scorer = Scorer(config)
    v = scorer.score(_case([_ev("DOMAIN_YOUNG")]))
    assert v.level == "NO_SIGNS"
    assert v.reasons == []  # not a deciding signal for NO_SIGNS (completed_checks only)
    assert v.worth_noting == ["DOMAIN_YOUNG"]


def test_nothing_completed_is_unknown(config):
    scorer = Scorer(config)
    v = scorer.score(_case([]))
    assert v.level == "UNKNOWN"
    assert v.confidence == "NOT_SURE"


def test_domain_young_suppressed_by_domain_official(config):
    scorer = Scorer(config)
    ledger = [_ev("DOMAIN_YOUNG", checker_id="c1"), _ev("DOMAIN_OFFICIAL", status="clear", checker_id="c2")]
    v = scorer.score(_case(ledger))
    assert "DOMAIN_YOUNG" not in v.worth_noting
    assert v.worth_noting == []
    assert v.level == "NO_SIGNS"  # the suppressed risk code no longer counts towards any level


def test_stale_deciding_source_downgrades_sure_to_fairly_sure(config):
    scorer = Scorer(config)
    v = scorer.score(_case([_ev("DEBARRED_ENTITY", basis="registry", stale=True)]))
    assert v.confidence == "FAIRLY_SURE"


def test_assurances_never_lower_the_level(config):
    scorer = Scorer(config)
    ledger = [
        _ev("DEBARRED_ENTITY", basis="registry", checker_id="c1"),
        _ev("REG_FOUND", status="clear", checker_id="c2"),
    ]
    v = scorer.score(_case(ledger))
    assert v.level == "HIGH_RISK"
    assert v.assurances == ["REG_FOUND"]


def test_same_code_from_two_entities_counts_once(config):
    scorer = Scorer(config)
    ledger = [
        _ev("REG_NOT_FOUND", basis="rule", entity_ids=["e1"], checker_id="c1"),
        _ev("REG_NOT_FOUND", basis="rule", entity_ids=["e2"], checker_id="c1"),
    ]
    v = scorer.score(_case(ledger))
    assert v.level == "SUSPICIOUS"
    assert len(v.reasons) == 1
    assert sorted(v.reasons[0].entity_ids) == ["e1", "e2"]


def test_checked_families_done_skipped_unknown(config, make_case):
    from satark.harness.state import PlanStep

    scorer = Scorer(config)
    case = make_case()
    case.plan.steps = [
        PlanStep(id="s1", checker_id="c1", entity_ids=["e1"], family="registry"),
        PlanStep(id="s2", checker_id="c2", entity_ids=["e1"], family="payment"),
        PlanStep(id="s3", checker_id="c3", entity_ids=["e1"], family="link"),
    ]
    case.ledger = [
        Evidence(id="ev1", step_id="s1", checker_id="c1", family="registry", entity_ids=["e1"], status="hit",
                 signals=[SignalHit(code="REG_NOT_FOUND", basis="rule", entity_ids=["e1"])], source=SourceRef()),
        Evidence(id="ev2", step_id="s2", checker_id="c2", family="payment", entity_ids=["e1"], status="skipped",
                 source=SourceRef()),
        Evidence(id="ev3", step_id="s3", checker_id="c3", family="link", entity_ids=["e1"], status="unknown",
                 source=SourceRef()),
    ]
    v = scorer.score(case)
    by_family = {c.family: c.status for c in v.checked}
    assert by_family == {"registry": "done", "payment": "skipped", "link": "unknown"}


def test_scam_type_and_lesson_and_actions(config):
    scorer = Scorer(config)
    v = scorer.score(_case([_ev("DEBARRED_ENTITY", basis="registry")]))  # scam_types: [T5]
    assert v.scam_type == "T5"
    assert v.lesson == config.scoring["lesson_by_scam_type"]["T5"]
    assert "verify_sebi_register" in v.actions  # DEBARRED_ENTITY's action, inserted after the first 2 defaults
    assert v.actions[:2] == config.scoring["default_actions"]["HIGH_RISK"][:2]


def test_revision_increments_on_each_score(config, make_case):
    scorer = Scorer(config)
    case = make_case()
    case.ledger = [_ev("DEBARRED_ENTITY", basis="registry")]
    v1 = scorer.score(case)
    assert v1.revision == 1
    case.verdict = v1
    v2 = scorer.score(case)
    assert v2.revision == 2


def test_verdict_event_shape(config, make_case):
    scorer = Scorer(config)
    case = make_case()
    case.ledger = [_ev("DEBARRED_ENTITY", basis="registry")]
    case.verdict = scorer.score(case)
    payload = verdict_event(case, config)
    assert payload["level"] == "HIGH_RISK"
    assert payload["reasons"][0]["code"] == "DEBARRED_ENTITY"
    assert payload["reasons"][0]["title"] == config.t(case.lang, "signal.DEBARRED_ENTITY")
    assert payload["scoring_version"] == config.scoring["version"]


def _case(ledger: list[Evidence]):
    from datetime import timedelta

    from satark.harness.state import CaseState, utcnow

    return CaseState(case_id="c1", lang="en", ledger=ledger, expires_at=utcnow() + timedelta(minutes=30))


def test_grounded_ai_risk_pattern_alone_is_suspicious_never_high(config):
    """A model-only risk the catalogue does not name counts as high: SUSPICIOUS alone; two of anything model-only stay capped."""
    scorer = Scorer(config)
    v = scorer.score(_case([_ev("AI_RISK_PATTERN", checker_id="ai.assessment", basis="llm_claim")]))
    assert v.level == "SUSPICIOUS"
    v = scorer.score(_case([_ev("AI_RISK_PATTERN", checker_id="ai.assessment", basis="llm_claim"),
                            _ev("FEE_TO_WITHDRAW", checker_id="ai.assessment", basis="llm_claim")]))
    assert v.level == "SUSPICIOUS"  # ai_only_max_level caps what the model finds alone
