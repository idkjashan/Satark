"""Explainer: LLM path with retry-then-template, template fallback, no model (LLD §6.2).

Uses `FakeGuards` (monkeypatched over `explain._guards`) rather than the real `guards.check_output`:
a content bug found during development (`no_tips.en` had two `(?i)` inline flags joined by `|`,
which Python 3.11+ rejects with `re.error` on every call - since fixed upstream) made that obvious,
but the real reason to fake it is isolation: this file proves D's retry/fallback wiring, not
whatever A's lexicon currently contains.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import satark.harness.explain as explain_mod
from satark.harness.explain import Explainer, _sentences
from satark.harness.models import ModelRouter
from satark.harness.skills import SkillStore
from satark.harness.state import (
    CaseState,
    Evidence,
    FamilyStatus,
    Reason,
    SignalHit,
    SourceRef,
    Verdict,
    utcnow,
)
from tests.unit.harness_fakes import FakeGuards


def _router(model=None) -> ModelRouter:
    r = ModelRouter({}, {})
    if model is not None:
        r.override("explain", model)
    return r


def _case_with_verdict(lang: str = "en") -> CaseState:
    case = CaseState(case_id="c1", lang=lang, expires_at=utcnow() + timedelta(minutes=30))
    case.ledger = [
        Evidence(
            id="ev1", step_id="s1", checker_id="sebi.reg.lookup", family="registry", entity_ids=["e1"], status="hit",
            signals=[SignalHit(code="REG_NOT_FOUND", basis="registry", entity_ids=["e1"])],
            source=SourceRef(id="sebi_registers", as_on="2026-10-02"),
        )
    ]
    case.verdict = Verdict(
        revision=1, level="HIGH_RISK", confidence="SURE",
        reasons=[Reason(code="REG_NOT_FOUND", weight="high", basis="registry", entity_ids=["e1"],
                         source=SourceRef(id="sebi_registers", as_on="2026-10-02"))],
        checked=[], scoring_version="test",
    )
    return case


def _tool_response(info: AgentInfo, **fields) -> ModelResponse:
    args = {"summary": "", "reasons": [], "chips": [], "fallback_used": False, "lang": "en", **fields}
    return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])


def _ungrounded_if_contains_ina(text: str) -> list[str]:
    return ["grounding"] if "INA000099999" in text else []


async def test_valid_output_passes(config, monkeypatch):
    monkeypatch.setattr(explain_mod, "_guards", lambda: FakeGuards())

    def fn(messages, info):
        return _tool_response(
            info, summary="SEBI could not find this registration number.",
            reasons=[{"code": "REG_NOT_FOUND", "text": "Not found in SEBI's register."}],
        )

    explainer = Explainer(_router(FunctionModel(fn)), config, SkillStore(config.root / "skills"))
    explanation = await explainer.explain(_case_with_verdict())

    assert explanation.fallback_used is False
    assert [r.code for r in explanation.reasons] == ["REG_NOT_FOUND"]
    assert explanation.lang == "en"


async def test_ungrounded_number_retries_then_succeeds(config, monkeypatch):
    monkeypatch.setattr(explain_mod, "_guards", lambda: FakeGuards(_ungrounded_if_contains_ina))
    calls = {"n": 0}

    def fn(messages, info):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_response(
                info, summary="INA000099999 is not registered with SEBI.",
                reasons=[{"code": "REG_NOT_FOUND", "text": "INA000099999 is not registered."}],
            )
        return _tool_response(
            info, summary="This registration number is not in SEBI's register.",
            reasons=[{"code": "REG_NOT_FOUND", "text": "Not found in SEBI's register."}],
        )

    explainer = Explainer(_router(FunctionModel(fn)), config, SkillStore(config.root / "skills"))
    explanation = await explainer.explain(_case_with_verdict())

    assert calls["n"] == 2
    assert "INA000099999" not in explanation.summary
    assert explanation.fallback_used is False


async def test_always_ungrounded_falls_back_to_template(config, monkeypatch):
    monkeypatch.setattr(explain_mod, "_guards", lambda: FakeGuards(_ungrounded_if_contains_ina))

    def fn(messages, info):
        return _tool_response(
            info, summary="INA000099999 looks suspicious too.",
            reasons=[{"code": "REG_NOT_FOUND", "text": "INA000099999 is bad."}],
        )

    explainer = Explainer(_router(FunctionModel(fn)), config, SkillStore(config.root / "skills"))
    explanation = await explainer.explain(_case_with_verdict())

    assert explanation.fallback_used is True
    assert [r.code for r in explanation.reasons] == ["REG_NOT_FOUND"]
    expected = _sentences([
        config.t("en", "level.HIGH_RISK.headline"),
        config.t("en", "signal.REG_NOT_FOUND"),
        config.t("en", "explain.uncertainty"),
    ], "en")
    assert explanation.summary == expected


async def test_no_model_uses_template_with_fallback_used_false(config, monkeypatch):
    monkeypatch.setattr(explain_mod, "_guards", lambda: FakeGuards())
    explainer = Explainer(_router(None), config, SkillStore(config.root / "skills"))
    explanation = await explainer.explain(_case_with_verdict())

    assert explanation.fallback_used is False
    assert [r.code for r in explanation.reasons] == ["REG_NOT_FOUND"]


async def test_could_not_check_families_are_named(config, monkeypatch):
    monkeypatch.setattr(explain_mod, "_guards", lambda: FakeGuards())
    explainer = Explainer(_router(None), config, SkillStore(config.root / "skills"))
    case = _case_with_verdict()
    case.verdict.checked = [FamilyStatus(family="link", status="unknown")]
    explanation = await explainer.explain(case)

    assert config.t("en", "family.link") in explanation.summary
